"""
CourtListener API client — judicial monitoring for EPR litigation.

Tracks federal court challenges to state EPR laws via CourtListener's REST API
and webhook system. Follows the same async context manager pattern as other
SignalScout ingestion clients.

Rate limits: use retry_with_backoff; avoid pagination past page 100 (use date filters).
Maintenance window: CourtListener is offline Thu 21:00–23:59 PT.
"""
import json
import re
from datetime import date

import anthropic
import httpx
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

SONNET_MODEL = "claude-sonnet-4-6"

# EPR seed queries for initial case discovery (Section 10 of spec)
EPR_LITIGATION_QUERIES = [
    ("EPR packaging litigation", '"extended producer responsibility" packaging'),
    ("EPR commerce clause", '"producer responsibility" "commerce clause"'),
    ("PACK Act preemption", '"PACK Act" OR "Packaging Act" preemption'),
    ("e-waste EPR challenge", '"e-waste" OR "electronics" "EPR" challenge'),
    ("battery EPR challenge", '"battery" "extended producer responsibility"'),
    ("recycling dormant commerce", '"dormant commerce clause" "recycling"'),
]

COURT_NAMES = {
    "cacd": "C.D. California",
    "cand": "N.D. California",
    "caed": "E.D. California",
    "casd": "S.D. California",
    "ord": "D. Oregon",
    "wawd": "W.D. Washington",
    "wad": "W.D. Washington",
    "dcd": "D.D.C.",
    "nyd": "S.D. New York",
    "nynd": "N.D. New York",
    "mnd": "D. Minnesota",
    "cod": "D. Colorado",
    "med": "D. Maine",
}


class CourtListenerClient:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        headers = {}
        if settings.courtlistener_api_token:
            headers["Authorization"] = f"Token {settings.courtlistener_api_token}"
        self._client = httpx.AsyncClient(
            base_url=settings.courtlistener_base_url,
            headers=headers,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _check_client(self):
        if self._client is None:
            raise RuntimeError("Use as async context manager")

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def search_epr_cases(
        self,
        query: str,
        court: str | None = None,
        filed_after: date | None = None,
        page: int = 1,
    ) -> list[dict]:
        """Full-text search for RECAP/PACER dockets matching query.

        Uses type=r (RECAP dockets). Avoids deep pagination — use filed_after
        to narrow result sets rather than paginating past page 100.
        """
        self._check_client()
        params: dict = {
            "q": query,
            "type": "r",
            "order_by": "score desc",
            "page": page,
        }
        if court:
            params["court"] = court
        if filed_after:
            params["filed_after"] = filed_after.isoformat()

        resp = await self._client.get("/search/", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def get_docket_details(self, docket_id: int) -> dict:
        """Get full docket metadata including parties, judge, filing dates."""
        self._check_client()
        resp = await self._client.get(f"/dockets/{docket_id}/")
        resp.raise_for_status()
        return resp.json()

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def get_docket_entries(
        self, docket_id: int, after_date: date | None = None
    ) -> list[dict]:
        """Get docket entries (individual filings) for a case."""
        self._check_client()
        params: dict = {
            "docket": docket_id,
            "order_by": "-date_filed",
        }
        if after_date:
            params["date_filed__gte"] = after_date.isoformat()

        resp = await self._client.get("/docket-entries/", params=params)
        resp.raise_for_status()
        return resp.json().get("results", [])

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def get_parties(self, docket_id: int) -> list[dict]:
        """Get parties for a docket. Used to identify industry group plaintiffs."""
        self._check_client()
        resp = await self._client.get("/parties/", params={"docket": docket_id})
        resp.raise_for_status()
        return resp.json().get("results", [])

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def create_search_alert(
        self, name: str, query: str, rate: str = "dly"
    ) -> dict:
        """Create a standing search alert. CourtListener POSTs to webhook when new results appear.

        rate: rt=real-time, dly=daily, wly=weekly, mly=monthly
        Returns the alert object including its ID.
        """
        self._check_client()
        resp = await self._client.post(
            "/alerts/",
            json={"name": name, "query": query, "rate": rate},
        )
        resp.raise_for_status()
        return resp.json()

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def create_docket_alert(self, docket_id: int) -> dict:
        """Subscribe to push notifications for a specific known case."""
        self._check_client()
        docket_url = f"{settings.courtlistener_base_url}/dockets/{docket_id}/"
        resp = await self._client.post(
            "/docket-alerts/",
            json={"docket": docket_url},
        )
        resp.raise_for_status()
        return resp.json()

    async def search_all_epr_cases(
        self, filed_after: date | None = None
    ) -> list[dict]:
        """Search all EPR seed queries and deduplicate by docket ID."""
        seen: set[int] = set()
        results: list[dict] = []
        for name, query in EPR_LITIGATION_QUERIES:
            try:
                cases = await self.search_epr_cases(query, filed_after=filed_after)
                for case in cases:
                    docket_id = case.get("docket_id") or case.get("id")
                    if docket_id and docket_id not in seen:
                        seen.add(docket_id)
                        results.append(case)
            except Exception as e:
                log.warning("cl_search_failed", query=query, error=str(e))
        return results


# ---------------------------------------------------------------------------
# LLM classification for litigation events
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM = """\
You are a legal analyst specializing in US constitutional challenges to state environmental laws. \
Analyze federal court docket entries related to Extended Producer Responsibility (EPR) legislation \
and classify the filing. Respond ONLY with valid JSON — no prose, no markdown.\
"""

_CLASSIFY_TEMPLATE = """\
Analyze this federal court docket entry and return ONLY valid JSON.

Case: {case_name}
Court: {court}
Entry description: {description}

Return this exact JSON structure:
{{
  "event_type": <one of: "filing","order","injunction_motion","injunction_ruling","appeal","settlement","other">,
  "significance": <one of: "low","medium","high","critical">,
  "summary": "<1-2 sentence plain-English summary for compliance professionals>"
}}

Significance guide:
- critical: injunction granted/denied, final judgment, case dismissed
- high: preliminary injunction motion filed, summary judgment, major order
- medium: briefing, opposition filed, hearing scheduled
- low: administrative filings, scheduling orders, routine motions
"""


async def classify_litigation_event(entry: dict, case_name: str = "", court_id: str = "") -> dict:
    """Classify a docket entry using Claude Haiku, with fallback to pattern matching.

    Returns dict with: event_type, significance, summary.
    """
    description = entry.get("description", "") or ""

    # Fast path: pattern-based classification for common entry types
    desc_lower = description.lower()
    if any(kw in desc_lower for kw in ("preliminary injunction", "temporary restraining order", "tro")):
        fast_type = "injunction_motion"
        fast_sig = "high"
    elif any(kw in desc_lower for kw in ("injunction granted", "injunction denied", "dismissed", "judgment")):
        fast_type = "injunction_ruling"
        fast_sig = "critical"
    elif "appeal" in desc_lower or "notice of appeal" in desc_lower:
        fast_type = "appeal"
        fast_sig = "high"
    elif "settlement" in desc_lower or "consent decree" in desc_lower:
        fast_type = "settlement"
        fast_sig = "high"
    elif any(kw in desc_lower for kw in ("order", "ruling", "opinion")):
        fast_type = "order"
        fast_sig = "medium"
    else:
        fast_type = None
        fast_sig = None

    if not settings.enable_llm_classification or not settings.anthropic_api_key:
        return {
            "event_type": fast_type or "filing",
            "significance": fast_sig or "low",
            "summary": description[:300] if description else "No description available.",
        }

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        prompt = _CLASSIFY_TEMPLATE.format(
            case_name=case_name or "Unknown",
            court=COURT_NAMES.get(court_id, court_id) if court_id else "Federal District Court",
            description=description[:1000],
        )
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            temperature=0,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}

        return {
            "event_type": data.get("event_type", fast_type or "filing"),
            "significance": data.get("significance", fast_sig or "low"),
            "summary": data.get("summary", description[:300]),
        }
    except Exception as e:
        log.warning("cl_classify_event_failed", error=str(e))
        return {
            "event_type": fast_type or "filing",
            "significance": fast_sig or "low",
            "summary": description[:300] if description else "Classification unavailable.",
        }


_RISK_SYSTEM = """\
You are a constitutional law expert specializing in Dormant Commerce Clause and federal preemption \
challenges to state environmental laws. Assess the litigation risk that this case poses to the \
continued enforcement of the related state EPR law. Respond ONLY with valid JSON.\
"""

_RISK_TEMPLATE = """\
Assess the preemption/enforcement risk for this federal court challenge to a state EPR law.

Case: {case_name}
Court: {court}
Challenge type: {challenge_type}
Plaintiffs: {plaintiffs}
Date filed: {date_filed}
Recent filings:
{events_text}

Return this exact JSON:
{{
  "preemption_risk": <integer 0-100>,
  "reasoning": "<2-3 sentences explaining the risk score>"
}}

Score guide:
- 0-20: Low risk — early filing, weak legal theory, no credible plaintiff
- 21-40: Moderate-low — plausible claim but significant legal hurdles
- 41-60: Moderate — credible claim, uncertain outcome
- 61-80: Moderate-high — strong legal theory, well-resourced plaintiff
- 81-100: High — injunction granted or imminent, strong precedent
"""


async def score_preemption_risk(case: dict, events: list[dict]) -> int:
    """Use Claude Sonnet to score 0-100 preemption risk for a litigation case.

    Falls back to 25 (moderate-low) if LLM unavailable.
    """
    if not settings.enable_courtlistener or not settings.anthropic_api_key:
        return 25

    events_text = "\n".join(
        f"- [{e.get('date_filed', '?')}] {e.get('description', '')[:200]}"
        for e in events[:10]
    ) or "No events yet."

    plaintiffs = case.get("key_plaintiffs") or []
    if isinstance(plaintiffs, list):
        plaintiffs_str = ", ".join(plaintiffs[:5]) or "Unknown"
    else:
        plaintiffs_str = str(plaintiffs)

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        prompt = _RISK_TEMPLATE.format(
            case_name=case.get("case_name", "Unknown"),
            court=COURT_NAMES.get(case.get("court_id", ""), case.get("court_id", "Unknown")),
            challenge_type=case.get("challenge_type", "unknown"),
            plaintiffs=plaintiffs_str,
            date_filed=case.get("date_filed", "unknown"),
            events_text=events_text,
        )
        resp = await client.messages.create(
            model=SONNET_MODEL,
            max_tokens=300,
            temperature=0,
            system=_RISK_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}

        score = int(data.get("preemption_risk", 25))
        return max(0, min(100, score))
    except Exception as e:
        log.warning("cl_score_risk_failed", case=case.get("case_name"), error=str(e))
        return 25


def extract_docket_id_from_url(url: str) -> int | None:
    """Extract numeric docket ID from a CourtListener docket URL."""
    if not url:
        return None
    match = re.search(r"/dockets/(\d+)/", url)
    return int(match.group(1)) if match else None


def infer_challenge_type(case_name: str, description: str) -> str:
    """Heuristic challenge type detection from case text."""
    text = f"{case_name} {description}".lower()
    if "dormant commerce" in text or "commerce clause" in text:
        return "dormant_commerce_clause"
    if "preempt" in text or "supremacy" in text:
        return "preemption"
    if "due process" in text or "equal protection" in text:
        return "due_process"
    return "other"


def infer_plaintiff_type(parties: list[dict]) -> tuple[str, list[str]]:
    """Infer plaintiff type and extract key plaintiff names from parties list."""
    plaintiff_names: list[str] = []
    industry_keywords = (
        "association", "council", "institute", "alliance", "federation",
        "chamber", "coalition", "industry", "manufacturers", "wholesaler",
        "retailers", "plastics", "packaging", "chemical",
    )
    for party in parties:
        role = (party.get("party_types") or [{}])[0].get("docket_entry_types", "") if party.get("party_types") else ""
        name = party.get("name", "")
        # Plaintiffs typically appear as "Plaintiff" in party_types
        is_plaintiff = any(
            "plaintiff" in str(pt).lower()
            for pt in (party.get("party_types") or [])
        )
        if is_plaintiff and name:
            plaintiff_names.append(name)

    if not plaintiff_names:
        # Fallback: take first 3 parties as likely plaintiffs
        plaintiff_names = [p.get("name", "") for p in parties[:3] if p.get("name")]

    # Determine plaintiff type
    names_lower = " ".join(plaintiff_names).lower()
    if any(kw in names_lower for kw in industry_keywords):
        plaintiff_type = "industry_group"
    elif plaintiff_names:
        plaintiff_type = "company"
    else:
        plaintiff_type = "unknown"

    return plaintiff_type, plaintiff_names[:10]
