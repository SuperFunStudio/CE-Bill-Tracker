"""Is this federal case actually about circular-economy law?

Every CourtListener ingest path used to answer "yes" by construction: whatever the search returned
was written into `litigation_cases` and alerted on, with a subject line that hardcoded "EPR
Litigation Update". The result on production was 34 tracked cases of which exactly one — NAWD v. Ryan,
the challenge to Colorado's packaging EPR program — was real litigation about our subject. Subscribers
got "EPR Litigation Update: United States v. State of Maryland" about a DOJ constitutional suit with
no connection to packaging at all.

Tightening the queries (see EPR_LITIGATION_QUERIES) removes the worst of the input, but it cannot be
the whole answer, because **the true positives are indistinguishable from noise in docket metadata**:

    NAWD v. Ryan          cause "42:1983 Civil Rights Act"   nature of suit "440 Civil Rights: Other"
    Lollicup USA v. Feldon cause "42:1983 Civil Rights Act"  nature of suit "950 Constitutional - State Statute"

Both are EPR challenges. Neither says so anywhere except inside the complaint. So the gate reads the
complaint: CourtListener's RECAP full text is the evidence, and metadata is only a fallback for
dockets whose documents aren't available.

Three-tier decision, cheapest first, biased toward *not* alerting:

  1. a strong phrase in the evidence ("extended producer responsibility", "bottle bill", …)  -> relevant
  2. no circular-economy vocabulary at all                                                    -> out of scope, no LLM spend
  3. anything in between                                                                      -> Haiku yes/no, default deny

Tier 2 is what kills the Pfizer/DraftKings/motorcycle-club rows without a single API call. Tier 3 is
what stops the gate from silently discarding a genuine case that phrases things unusually — those
land as out-of-scope but carry `needs_review`, so a miss is visible rather than lost.

The verdict is persisted on the case (ce_relevant / relevance_reason / relevance_source), so a
disputed call can be audited and reversed without re-fetching anything.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import anthropic
import structlog

from app.config import settings

log = structlog.get_logger()

# A phrase here is dispositive on its own: no case says "extended producer responsibility" or
# "container deposit" in passing. Multi-word by design — single tokens ("packaging", "battery") are
# exactly what produced the false positives and belong in the weak list below.
CE_STRONG_PHRASES = (
    "extended producer responsibility",
    "producer responsibility organization",
    "product stewardship program",
    "packaging stewardship",
    "paint stewardship",
    "carpet stewardship",
    "mattress stewardship",
    "battery stewardship",
    "bottle bill",
    "container deposit",
    "beverage container redemption",
    "deposit return scheme",
    "electronic waste recycling",
    "e-waste recycling",
    "right to repair",
    "recycled content standard",
    "recycled content mandate",
    "post-consumer recycled content",
    "single-use plastic",
    "plastic bag ban",
    "polystyrene ban",
    "circular economy",
    "recycling refund",
    "advance disposal fee",
    "eco-modulation",
    "take-back program",
    "takeback program",
)

# Vocabulary that *could* indicate a circular-economy dispute but routinely appears in unrelated
# suits (a products-liability complaint mentions "packaging"; a landfill contract dispute mentions
# "recycling"). Presence here only buys a look from the classifier — never a pass on its own.
CE_WEAK_TERMS = (
    "recycling",
    "recyclable",
    "recycled",
    "packaging",
    "solid waste",
    "landfill",
    "compostable",
    "reusable",
    "producer responsibility",
    "stewardship",
    "e-waste",
    "electronic waste",
    "deposit refund",
    "waste diversion",
    "extended producer",
)

_STRONG_RE = re.compile(
    "|".join(rf"\b{re.escape(p)}\b" for p in CE_STRONG_PHRASES), re.IGNORECASE
)
_WEAK_RE = re.compile("|".join(rf"\b{re.escape(t)}\b" for t in CE_WEAK_TERMS), re.IGNORECASE)

# How many times a weak term must appear before the classifier is worth paying for. A complaint that
# is *about* recycling says so repeatedly; one stray "packaging" in an exhibit index is not a case.
_WEAK_HIT_FLOOR = 3

SOURCE_KEYWORD = "keyword"
SOURCE_NO_SIGNAL = "no_signal"
SOURCE_LLM = "llm"
SOURCE_LLM_UNAVAILABLE = "llm_unavailable"
SOURCE_MANUAL = "manual"


@dataclass
class RelevanceVerdict:
    """The gate's answer, in a shape that can be written straight onto a LitigationCase row."""

    relevant: bool
    reason: str
    source: str
    # True when the gate excluded something it wasn't confident about — a human should look, and the
    # case is queryable by this flag rather than being indistinguishable from a clear rejection.
    needs_review: bool = False


def build_evidence(
    *,
    case_name: str = "",
    cause: str = "",
    nature_of_suit: str = "",
    party_names: list[str] | None = None,
    entry_descriptions: list[str] | None = None,
    document_text: str = "",
) -> str:
    """Flatten everything we know about a case into one block for the gate to read.

    Order matters only for the LLM's benefit (identity first, then the substance). The complaint text
    goes last because it is the longest and the most truncatable.
    """
    parts = [
        f"Case name: {case_name}" if case_name else "",
        f"Cause: {cause}" if cause else "",
        f"Nature of suit: {nature_of_suit}" if nature_of_suit else "",
        f"Parties: {', '.join(party_names)}" if party_names else "",
    ]
    if entry_descriptions:
        parts.append("Docket entries:\n" + "\n".join(d for d in entry_descriptions if d))
    if document_text:
        parts.append("Filing text:\n" + document_text)
    return "\n".join(p for p in parts if p)


def pick_primary_document_id(search_result: dict | None, entries: list[dict] | None) -> int | None:
    """Which RECAP document to read: the complaint if we can find it, else the earliest available.

    The complaint is where a case states what law it is challenging. Later filings (appearances,
    scheduling orders) are subject-matter silent, which is exactly why metadata-only classification
    failed on this source.
    """
    candidates: list[dict] = []
    for doc in (search_result or {}).get("recap_documents") or []:
        if isinstance(doc, dict):
            candidates.append(doc)
    for entry in entries or []:
        for doc in entry.get("recap_documents") or []:
            if isinstance(doc, dict):
                candidates.append(doc)

    available = [d for d in candidates if d.get("is_available") and d.get("id")]
    if not available:
        return None

    def _is_complaint(doc: dict) -> bool:
        text = f"{doc.get('short_description', '')} {doc.get('description', '')}".lower()
        return "complaint" in text or "petition" in text

    complaints = [d for d in available if _is_complaint(d)]
    pool = complaints or available
    # entry_number ascending — document 1 is the initiating filing.
    pool.sort(key=lambda d: (d.get("entry_number") or d.get("document_number") or 10**6))
    return pool[0]["id"]


_GATE_SYSTEM = """\
You screen federal court dockets for a circular-economy policy tracker. The tracker covers \
litigation about extended producer responsibility, packaging and product stewardship, recycling and \
waste-diversion mandates, deposit-return systems, recycled-content requirements, right-to-repair, \
single-use restrictions, and e-waste programs — including constitutional challenges to such laws. \
It does NOT cover general environmental, products-liability, patent, contract, employment, or \
criminal cases that merely mention packaging, waste, or recycling in passing. Respond ONLY with \
valid JSON.\
"""

_GATE_TEMPLATE = """\
Decide whether this federal case belongs in a circular-economy litigation tracker.

{evidence}

Return this exact JSON:
{{
  "relevant": <true or false>,
  "reason": "<one sentence naming the specific law or subject matter that decided it>"
}}

Answer true only if the case challenges, enforces, or directly concerns a circular-economy law of \
the kind described. A passing mention of packaging, waste, or recycling is not enough. When the \
evidence is too thin to tell, answer false.
"""


async def assess_relevance(evidence: str, *, case_name: str = "") -> RelevanceVerdict:
    """Screen one case. Never raises — an unusable classifier degrades to a reviewable exclusion."""
    if not evidence.strip():
        return RelevanceVerdict(
            relevant=False,
            reason="No docket evidence available to assess.",
            source=SOURCE_NO_SIGNAL,
            needs_review=True,
        )

    strong = _STRONG_RE.search(evidence)
    if strong:
        return RelevanceVerdict(
            relevant=True,
            reason=f'Filing text uses the term "{strong.group(0).lower()}".',
            source=SOURCE_KEYWORD,
        )

    weak_hits = _WEAK_RE.findall(evidence)
    if len(weak_hits) < _WEAK_HIT_FLOOR:
        return RelevanceVerdict(
            relevant=False,
            reason="No circular-economy subject matter in the docket or filing text.",
            source=SOURCE_NO_SIGNAL,
        )

    if not settings.enable_llm_classification or not settings.anthropic_api_key:
        return RelevanceVerdict(
            relevant=False,
            reason=(
                "Ambiguous circular-economy vocabulary and no classifier available to adjudicate; "
                "excluded pending review."
            ),
            source=SOURCE_LLM_UNAVAILABLE,
            needs_review=True,
        )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            temperature=0,
            system=_GATE_SYSTEM,
            messages=[
                {"role": "user", "content": _GATE_TEMPLATE.format(evidence=evidence[:12000])}
            ],
        )
        raw = resp.content[0].text.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}
        relevant = bool(data.get("relevant"))
        reason = (data.get("reason") or "").strip() or "Classifier returned no reason."
        return RelevanceVerdict(relevant=relevant, reason=reason, source=SOURCE_LLM)
    except Exception as e:  # noqa: BLE001 — a screening failure must not abort ingestion
        log.warning("cl_relevance_gate_failed", case=case_name, error=str(e))
        return RelevanceVerdict(
            relevant=False,
            reason=f"Relevance classifier failed ({type(e).__name__}); excluded pending review.",
            source=SOURCE_LLM_UNAVAILABLE,
            needs_review=True,
        )


async def screen_docket(
    cl,
    *,
    docket: dict,
    parties: list[dict] | None = None,
    entries: list[dict] | None = None,
    search_result: dict | None = None,
) -> RelevanceVerdict:
    """Gather evidence for a docket (fetching the complaint text when available) and screen it.

    `cl` is an entered CourtListenerClient. Document fetching is best-effort: if RECAP has nothing
    available, the gate falls back to metadata + entry descriptions, which for this source almost
    always means an out-of-scope verdict with needs_review set — deliberately, since alerting on a
    case we cannot read is how this went wrong in the first place.
    """
    document_text = ""
    doc_id = pick_primary_document_id(search_result, entries)
    if doc_id:
        try:
            document_text = await cl.get_document_text(doc_id)
        except Exception as e:  # noqa: BLE001
            log.warning("cl_document_text_failed", document_id=doc_id, error=str(e))

    evidence = build_evidence(
        case_name=docket.get("case_name") or (search_result or {}).get("caseName", ""),
        cause=docket.get("cause") or "",
        nature_of_suit=docket.get("nature_of_suit") or "",
        party_names=[p.get("name", "") for p in (parties or []) if p.get("name")][:12],
        entry_descriptions=[(e.get("description") or "")[:400] for e in (entries or [])[:10]],
        document_text=document_text,
    )
    verdict = await assess_relevance(evidence, case_name=docket.get("case_name", ""))
    log.info(
        "cl_relevance_verdict",
        case=docket.get("case_name"),
        relevant=verdict.relevant,
        source=verdict.source,
        had_document=bool(document_text),
    )
    return verdict
