import json
import re
from dataclasses import dataclass

import anthropic
import structlog

from app.config import settings

log = structlog.get_logger()

SONNET_MODEL = "claude-sonnet-4-6"

# Region code -> human label injected into the prompts, so the extractor frames the measure for the
# right jurisdiction (member-state national law extracts richly even in its native language — German
# VerpackG, Swedish/Dutch/Polish ordinances — but only if it knows the country, not a bare code).
# Covers every jurisdiction currently ingested (see app/ingestion/foreign.py adapters). An unknown
# code falls back to the raw code rather than mislabeling foreign law "United States".
REGION_LABELS = {
    "US": "United States", "EU": "European Union", "UK": "United Kingdom",
    "FR": "France", "JP": "Japan", "PL": "Poland", "DE": "Germany", "SE": "Sweden",
    "NL": "Netherlands", "ES": "Spain", "FI": "Finland", "IE": "Ireland", "CL": "Chile",
    "DK": "Denmark", "CH": "Switzerland", "SI": "Slovenia", "BR": "Brazil", "AT": "Austria",
    "LU": "Luxembourg", "LV": "Latvia", "SK": "Slovakia", "LT": "Lithuania", "CZ": "Czechia",
    "EE": "Estonia", "KR": "South Korea", "NO": "Norway", "BE": "Belgium", "IT": "Italy",
    "PT": "Portugal", "CA": "Canada", "AU": "Australia", "CN": "China",
}


def region_label(region: str | None) -> str:
    code = (region or "US").upper()
    return REGION_LABELS.get(code, code)


# Anchors marking the EPR / circular-economy core of a large omnibus act. select_text_window uses
# these so a measure that exceeds the model's text budget is windowed around its compliance-relevant
# sections instead of blindly truncated from the top — which on the UK Environment Act 2021 (687K
# chars) captured only governance preamble and missed every EPR/DRS provision. See the foreign-corpus
# extraction post-mortem.
_ANCHOR_RE = re.compile(
    r"\b(producer responsibility|extended producer|product stewardship|packaging waste|"
    r"packaging|deposit return|deposit scheme|deposit and return|take[-\s]?back|"
    r"recycled content|right to repair|single[-\s]use plastic|eco[-\s]?modulat|"
    r"collection target|recycling target|stewardship)\b",
    re.IGNORECASE,
)


def select_text_window(full_text: str, max_chars: int = 40000, head_chars: int = 4000) -> str:
    """Pick the slice of bill text to send to the extractor.

    Small measures (<= max_chars) go whole. For larger ones, keep a head slice (title / scope /
    definitions — usually front-loaded) plus a window starting at the first EPR anchor, so omnibus
    acts surface their actual compliance provisions rather than just the preamble. If no anchor is
    found, fall back to the leading max_chars (pure EPR laws front-load obligations — e.g. German
    VerpackG extracted fully from its first 12K).
    """
    if len(full_text) <= max_chars:
        return full_text
    head = full_text[:head_chars]
    budget = max_chars - head_chars
    m = _ANCHOR_RE.search(full_text, head_chars)
    if not m:
        return full_text[:max_chars]
    start = max(head_chars, m.start() - 1000)
    body = full_text[start : start + budget]
    return f"{head}\n[...]\n{body}"


SYSTEM_PROMPT_TEMPLATE = """\
You are a compliance specialist analyzing {region} EPR / circular-economy legislation. \
Extract all compliance-relevant details that would matter to a producer, manufacturer, brand owner, or importer. \
Be precise about dates, thresholds, and obligations. If a detail is not specified in the measure, omit that key.\
"""

USER_TEMPLATE = """\
Extract compliance details from this measure. Respond with ONLY valid JSON — no prose, no markdown.

Jurisdiction: {state}
Bill: {bill_number}
Title: {title}

Full text:
{full_text}

Return this JSON structure (omit any keys where data is absent):
{{
  "covered_products": ["<description of covered products/materials>"],
  "producer_definition": "<who is a covered producer>",
  "producer_obligations": ["<each obligation as a string>"],
  "deadlines": [
    {{"type": "<registration|reporting|compliance|fee_payment|other>", "date": "<YYYY-MM-DD or null>", "description": "<what is due>"}}
  ],
  "fees": {{
    "structure": "<per_unit|per_ton|flat|eco_modulated|unknown>",
    "details": "<description of fee structure>"
  }},
  "exemptions": ["<each exemption>"],
  "pro_requirements": "<PRO/stewardship organization requirements>",
  "enforcement": {{
    "agency": "<enforcing agency>",
    "penalties": "<penalty description>"
  }},
  "effective_date": "<YYYY-MM-DD or null>",
  "reporting_requirements": "<annual/periodic reporting obligations>",
  "preemption_risk": "<Low|Medium|High>",
  "preemption_notes": "<any preemption-related provisions or risks>",
  "related_bills": ["<e.g. CA-SB-343>"],
  "implementation_phases": ["<phase descriptions with dates>"]
}}
"""


@dataclass
class SonnetResult:
    covered_products: list[str]
    producer_definition: str
    producer_obligations: list[str]
    deadlines: list[dict]
    fees: dict
    exemptions: list[str]
    pro_requirements: str
    enforcement: dict
    effective_date: str | None
    reporting_requirements: str
    preemption_risk: str
    preemption_notes: str
    related_bills: list[str]
    implementation_phases: list[str]
    raw_json: dict


class SonnetExtractor:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        # 120s timeout (extraction is heavier than Haiku classification, so longer than its 60s) so a
        # hung call fails fast instead of pinning the caller — critically, the classification cycle
        # holds a DB transaction across this call, and an unbounded hang there strands a connection
        # idle-in-transaction holding bills locks (see ClassificationPipeline.run Stage 3).
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=120.0, max_retries=1
        )

    async def extract(
        self,
        state: str,
        bill_number: str,
        title: str,
        full_text: str,
        region: str = "US",
    ) -> SonnetResult:
        prompt = USER_TEMPLATE.format(
            state=state,
            bill_number=bill_number or "Unknown",
            title=title or "",
            # ~10K tokens of text, keyword-windowed for large omnibus acts (see select_text_window).
            full_text=select_text_window(full_text),
        )
        resp = await self._client.messages.create(
            model=SONNET_MODEL,
            max_tokens=4000,  # compliance JSON for large bills overflows a smaller budget
            temperature=0,
            system=SYSTEM_PROMPT_TEMPLATE.format(region=region_label(region)),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            try:
                data = json.loads(match.group()) if match else {}
            except json.JSONDecodeError:
                # Truncated or malformed JSON (e.g. response cut off mid-object).
                log.warning("sonnet_json_parse_failed", bill_number=bill_number, raw=raw[:200])
                data = {}

        return SonnetResult(
            covered_products=data.get("covered_products", []),
            producer_definition=data.get("producer_definition", ""),
            producer_obligations=data.get("producer_obligations", []),
            deadlines=data.get("deadlines", []),
            fees=data.get("fees", {}),
            exemptions=data.get("exemptions", []),
            pro_requirements=data.get("pro_requirements", ""),
            enforcement=data.get("enforcement", {}),
            effective_date=data.get("effective_date"),
            reporting_requirements=data.get("reporting_requirements", ""),
            preemption_risk=data.get("preemption_risk", "Low"),
            preemption_notes=data.get("preemption_notes", ""),
            related_bills=data.get("related_bills", []),
            implementation_phases=data.get("implementation_phases", []),
            raw_json=data,
        )
