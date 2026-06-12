"""Design-lever synthesis: turn already-extracted compliance_details into cited, per-bill
design signals — the atoms a "Design-for-EPR" principle is aggregated from.

Chain of custody is enforced mechanically, not by trust: the LLM is told to copy each
`source_excerpt` verbatim from the bill's stored compliance_details, and `validate_signals`
drops any signal whose excerpt is NOT a substring of that text. A principle therefore can
never cite a clause that isn't actually in the source bill.

No bill text is re-fetched and no Sonnet re-extraction runs — this reads the JSON the
pipeline already stored on bills.compliance_details (see app/classification/sonnet_extractor.py).
Cost/fee exposure is deliberately NOT computed here: eco-modulation rates come from the
Circular Action Alliance schedules (per state) and plug in later via a separate rate table.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import anthropic
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Controlled lever vocabulary (must stay in sync with scripts/inspect_design_levers.py and,
# later, the eco_mod_rate reference table so CAA fee schedules join cleanly).
LEVERS = (
    "design_for_recycling",
    "recycled_content",
    "reuse_refill",
    "repairability_durability",
    "toxics_elimination",
    "source_reduction",
    "labeling_marking",
    "compostability",
    "material_restriction",
)
OBLIGATIONS = ("required", "rewarded", "penalized", "banned", "exempted", "named")

# Human-readable principle phrasing, keyed by lever. Combined with the obligation framing
# below to render a canonical principle statement at aggregation time.
PRINCIPLE_STATEMENTS = {
    "design_for_recycling": "Design packaging to be recyclable in available systems",
    "recycled_content": "Incorporate post-consumer recycled content",
    "reuse_refill": "Shift to reusable / refillable formats",
    "repairability_durability": "Design for repairability, spare-parts access, and longevity",
    "toxics_elimination": "Eliminate restricted substances (PFAS, heavy metals, etc.)",
    "source_reduction": "Reduce packaging material per unit (lightweight, right-size)",
    "labeling_marking": "Apply required recyclability / disposal labeling",
    "compostability": "Use certified-compostable materials where specified",
    "material_restriction": "Avoid banned / restricted materials and formats",
}
OBLIGATION_FRAMING = {
    "required": "Required",
    "rewarded": "Fee-advantaged",
    "penalized": "Fee-penalized",
    "banned": "Prohibited",
    "exempted": "Exemption available",
    "named": "Referenced",
}

# compliance_details keys folded into the evidence corpus the model may quote from.
_EVIDENCE_FIELDS = (
    "covered_products",
    "producer_obligations",
    "exemptions",
    "reporting_requirements",
    "producer_definition",
    "pro_requirements",
)

SYSTEM_PROMPT = """\
You are a packaging-design compliance analyst. Given structured compliance details already \
extracted from a US EPR / circular-economy bill, identify concrete PACKAGING OR PRODUCT DESIGN \
implications for a producer — design ATTRIBUTES a producer can change to change their obligations, \
fees, bans, or exemptions under this bill.

A design lever is something the producer CONTROLS at the drawing board: material choice, \
recyclability, recycled content, reusability, repairability, toxics, packaging amount, labeling. \

It is NOT a regulatory scope boundary. A product's total weight, energy (watt-hour) rating, or \
physical size that merely DETERMINES WHETHER it is a 'covered product' is a coverage threshold, \
not a design lever — ignore it. Likewise deposit/refund-value mechanics, fee-payment amounts, \
registration, and reporting are administrative, not design. When in doubt, omit. Precision beats \
recall: returning fewer, certain signals is better than many weak ones.\
"""

USER_TEMPLATE = """\
Bill: {state} {bill_number} — {title}

Compliance details (your ONLY source; quote from it verbatim):
{evidence}

Return ONLY valid JSON, no prose:
{{
  "signals": [
    {{
      "lever": <one of: {levers}>,
      "obligation_type": <one of: required|rewarded|penalized|banned|exempted|named>,
      "design_action": "<imperative guidance to a producer, <=12 words>",
      "source_excerpt": "<VERBATIM substring copied from the compliance details above>",
      "threshold_value": <number or null>,
      "threshold_unit": "<e.g. percent_pcr, year, pounds, or null>",
      "confidence": <float 0.0-1.0>
    }}
  ]
}}

Lever definitions (pick the most specific):
- design_for_recycling: make the packaging/product recyclable in available systems (mono-material,
  recyclable-by-design, easy separation of components for recycling).
- recycled_content: incorporate post-consumer recycled (PCR) content; meet a recycled-content %.
- reuse_refill: reusable / refillable formats and the systems that enable them.
- repairability_durability: repairability, spare-parts availability, no parts-pairing, longer product
  life / durability (right-to-repair). Route ALL repair/parts/longevity items here, NOT to recycling.
- toxics_elimination: remove or avoid restricted substances (PFAS, mercury, heavy metals, free-liquid
  electrolyte, chemicals of concern).
- source_reduction: reduce the AMOUNT of packaging/material PER UNIT (lightweighting, eliminating
  unnecessary components, concentrates). NOT a product's total weight crossing a coverage threshold.
- labeling_marking: required recyclability / disposal / chemistry / resin-identification labeling.
- compostability: certified-compostable materials where the bill specifies them.
- material_restriction: banned or restricted materials/formats (EPS/polystyrene, single-use plastic
  bags, PVC, intentionally-added substances).

Rules:
- source_excerpt MUST be copied exactly from the compliance details text above (it will be
  verified as a substring; fabricated quotes are discarded).
- obligation_type: "required"=mandated design; "banned"=prohibited material/format;
  "rewarded"/"penalized"=eco-modulated fee bonus/malus; "exempted"=this DESIGN choice escapes the
  obligation; "named"=design topic referenced but no clear directive.
- DO NOT emit a signal for: coverage/scope thresholds (a product's weight, watt-hour rating, or size
  that only define whether it is covered); deposit/refund-value mechanics; fee-payment amounts;
  registration, reporting, or PRO-governance administrivia. Omit rather than force a weak match.
- Emit at most one signal per (lever, obligation_type). Omit levers that don't apply.
- If the bill has no real design implication, return {{"signals": []}}.
"""


@dataclass
class DesignSignal:
    bill_id: int
    state: str
    bill_number: str | None
    lever: str
    obligation_type: str
    design_action: str
    source_excerpt: str
    threshold_value: float | None
    threshold_unit: str | None
    confidence: float

    def to_dict(self) -> dict:
        return {
            "bill_id": self.bill_id,
            "state": self.state,
            "bill_number": self.bill_number,
            "lever": self.lever,
            "obligation_type": self.obligation_type,
            "design_action": self.design_action,
            "source_excerpt": self.source_excerpt,
            "threshold_value": self.threshold_value,
            "threshold_unit": self.threshold_unit,
            "confidence": self.confidence,
        }


def _norm(text: str) -> str:
    """Whitespace-collapsed, lowercased — for substring provenance checks."""
    return re.sub(r"\s+", " ", text).strip().lower()


def build_evidence_corpus(details: dict) -> str:
    """Flatten the design-relevant compliance_details fields into one quotable block."""
    parts: list[str] = []
    for f in _EVIDENCE_FIELDS:
        val = details.get(f)
        if not val:
            continue
        if isinstance(val, list):
            parts.extend(f"- {str(x).strip()}" for x in val if str(x).strip())
        else:
            parts.append(f"- {str(val).strip()}")
    fees = details.get("fees")
    if isinstance(fees, dict):
        struct = fees.get("structure")
        if struct:
            parts.append(f"- fee structure: {struct}")
        if fees.get("details"):
            parts.append(f"- fee details: {str(fees['details']).strip()}")
    return "\n".join(parts)


def validate_signals(raw: list[dict], corpus: str, bill: dict) -> tuple[list[DesignSignal], int]:
    """Keep only well-formed signals whose excerpt is verbatim-present in the corpus.

    Returns (valid_signals, n_dropped). Dropping is the chain-of-custody guarantee: a signal
    with a hallucinated or paraphrased citation cannot enter the dataset.
    """
    corpus_norm = _norm(corpus)
    valid: list[DesignSignal] = []
    dropped = 0
    for s in raw:
        lever = str(s.get("lever", "")).strip()
        oblig = str(s.get("obligation_type", "")).strip()
        excerpt = str(s.get("source_excerpt", "")).strip()
        if lever not in LEVERS or oblig not in OBLIGATIONS:
            dropped += 1
            continue
        # Excerpt must be a real, non-trivial substring of the source text.
        if len(_norm(excerpt)) < 12 or _norm(excerpt) not in corpus_norm:
            dropped += 1
            continue
        tv = s.get("threshold_value")
        try:
            tv = float(tv) if tv is not None else None
        except (TypeError, ValueError):
            tv = None
        valid.append(DesignSignal(
            bill_id=bill["id"],
            state=bill["state"],
            bill_number=bill.get("bill_number"),
            lever=lever,
            obligation_type=oblig,
            design_action=str(s.get("design_action", "")).strip()[:120],
            source_excerpt=excerpt[:400],
            threshold_value=tv,
            threshold_unit=(str(s.get("threshold_unit")).strip() if s.get("threshold_unit") else None),
            confidence=max(0.0, min(1.0, float(s.get("confidence", 0.0) or 0.0))),
        ))
    return valid, dropped


class DesignLeverExtractor:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=60.0, max_retries=0
        )

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    async def _call(self, prompt: str) -> str:
        resp = await self._client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1200,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    async def extract(self, bill: dict) -> tuple[list[DesignSignal], int]:
        """bill: {id, state, bill_number, title, compliance_details(dict)}.

        Returns (validated signals, n_dropped_for_provenance).
        """
        details = bill.get("compliance_details") or {}
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                return [], 0
        corpus = build_evidence_corpus(details)
        if not corpus.strip():
            return [], 0

        prompt = USER_TEMPLATE.format(
            state=bill["state"],
            bill_number=bill.get("bill_number") or "?",
            title=(bill.get("title") or "")[:200],
            evidence=corpus[:8000],
            levers="|".join(LEVERS),
        )
        raw_text = await self._call(prompt)
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw_text, re.DOTALL)
            try:
                data = json.loads(m.group()) if m else {}
            except json.JSONDecodeError:
                log.warning("design_signal_parse_failed", bill_id=bill.get("id"), raw=raw_text[:200])
                return [], 0
        return validate_signals(data.get("signals", []), corpus, bill)


# ---------------------------------------------------------------------------
# Aggregation: signals -> canonical principles (with full evidence list).
# ---------------------------------------------------------------------------

@dataclass
class Principle:
    lever: str
    obligation_type: str
    statement: str
    bill_count: int
    states: list[str]
    evidence: list[dict] = field(default_factory=list)


def aggregate_principles(signals: list[DesignSignal]) -> list[Principle]:
    """Group cited signals into (lever, obligation_type) principles, evidence preserved."""
    groups: dict[tuple[str, str], list[DesignSignal]] = {}
    for s in signals:
        groups.setdefault((s.lever, s.obligation_type), []).append(s)

    principles: list[Principle] = []
    for (lever, oblig), sigs in groups.items():
        bills = {s.bill_id for s in sigs}
        states = sorted({s.state for s in sigs})
        statement = f"{OBLIGATION_FRAMING.get(oblig, oblig)}: {PRINCIPLE_STATEMENTS.get(lever, lever)}"
        evidence = sorted(
            ({
                "state": s.state,
                "bill_number": s.bill_number,
                "bill_id": s.bill_id,
                "design_action": s.design_action,
                "source_excerpt": s.source_excerpt,
                "threshold_value": s.threshold_value,
                "threshold_unit": s.threshold_unit,
                "confidence": s.confidence,
            } for s in sigs),
            key=lambda e: (e["state"], e["bill_number"] or ""),
        )
        principles.append(Principle(
            lever=lever, obligation_type=oblig, statement=statement,
            bill_count=len(bills), states=states, evidence=evidence,
        ))
    principles.sort(key=lambda p: (-p.bill_count, p.lever))
    return principles
