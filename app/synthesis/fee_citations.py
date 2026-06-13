"""Fee / threshold citation extraction: ground the numbers behind a cost or severity estimate
in either the enacted bill text or a published agency schedule — never an unsourced guess.

This is the fee analogue of app/synthesis/design_levers.py and enforces the SAME chain of custody:
for a value the model claims is stated in the bill, the LLM must copy the `source_excerpt` verbatim
from the bill's stored compliance_details, and `validate_citations` drops any citation whose excerpt
is NOT a substring of that text (and, when a number is claimed, whose number does not appear in the
quoted clause). A cost estimate can therefore never cite a fee clause that isn't actually in the bill.

Reality check baked into the design: an EPR bill's per-ton fee is usually NOT written into the statute —
it is set afterward by the PRO / agency via rulemaking (CalRecycle, PaintCare, MRC schedules). So the
LLM path only ever emits `basis="enacted_text"` citations (thresholds, registration fees, eco-modulation
language that the bill really does state). The published $/ton numbers live in a separate, equally
auditable path — `citations_from_curated_fees` — which turns the curated `compliance_details.fees`
block (scripts/enrich_bill_fees.py) into `published_schedule` / `benchmark` citations. Together the two
paths cover "where every number came from".

No bill text is re-fetched and no Sonnet re-extraction runs — this reads the JSON the pipeline already
stored on bills.compliance_details (see app/classification/sonnet_extractor.py).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import anthropic
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Controlled fact vocabulary — one numeric fact per row. Kept aligned with the keys the cost
# estimator consumes (app/scoring/cost_estimator.py) plus the coverage thresholds that determine
# WHO is a producer (deliberately excluded from design_levers, grounded here instead).
FACT_TYPES = (
    "fee_per_ton",                 # $/tonne producer fee
    "fee_per_unit_usd",            # $/unit producer fee (per-unit schemes)
    "registration_fee_usd",        # flat registration / membership fee
    "producer_revenue_threshold",  # de-minimis: revenue floor to be a covered producer
    "producer_tonnage_threshold",  # de-minimis: tonnage/volume floor to be covered
    "eco_modulation",              # bonus/malus tied to design (value optional)
)

# How a cited value is sourced. The LLM extractor emits only "enacted_text"; the other two are
# produced by citations_from_curated_fees from the curated fees block.
BASES = ("enacted_text", "published_schedule", "benchmark")
GROUNDED_BASES = ("enacted_text", "published_schedule")

# Dollar-denominated facts: a value carrying a percent unit is a mis-tag (a procurement price-preference
# or rate target slipping into a fee/threshold slot), so it's dropped regardless of the prompt.
_DOLLAR_FACTS = frozenset(
    {"fee_per_ton", "fee_per_unit_usd", "registration_fee_usd", "producer_revenue_threshold"}
)

# fee_structure_source (compliance_details.fees) -> citation basis. Anything mapping to
# "published_schedule" is a real agency/PRO schedule; benchmarks are estimates, not grounded.
_SOURCE_TO_BASIS: dict[str, str] = {
    "calrecycle_published": "published_schedule",
    "paintcare_published": "published_schedule",
    "mrc_published": "published_schedule",
    "published_range_midpoint": "published_schedule",
    "industry_benchmark": "benchmark",
    "category_benchmark": "benchmark",
}

# compliance_details keys folded into the corpus the model may quote from. Fee/threshold language
# lives in the producer definition, obligations, exemptions, and the fees free-text — NOT in the
# numeric fee fields themselves (those are the curated overlay, which is what we're trying to ground).
_EVIDENCE_FIELDS = (
    "producer_definition",
    "producer_obligations",
    "exemptions",
    "reporting_requirements",
    "covered_products",
    "pro_requirements",
)

SYSTEM_PROMPT = """\
You are an EPR compliance analyst. Given structured compliance details already extracted from a US \
extended-producer-responsibility / circular-economy bill, find the MONETARY FEES A PRODUCER PAYS and the \
COVERAGE THRESHOLDS that define which producers are covered — but ONLY where the bill text states them — \
and cite each one to the exact clause.

Direction of money matters: report only amounts a PRODUCER PAYS to comply (registration/membership fees, \
per-unit or per-ton producer fees, dues). Money flowing the other way — consumer deposits, refunds, \
rebates, collection incentives or bounties paid TO consumers/retailers/technicians — is NOT a producer \
fee. Ignore it.

A coverage threshold is a de-minimis FLOOR (a dollar of annual gross revenue, or a tonnage/volume) below \
which a producer is exempt. A percentage is almost never a coverage threshold: procurement price- \
preference percentages, recycling-rate targets, and recycled-content percentages are NOT revenue/tonnage \
thresholds. Ignore them.

EPR per-ton fees are usually NOT in the statute — they are set later by the PRO or agency — so most bills \
will only state a flat registration fee, a de-minimis revenue/tonnage threshold, or that fees are eco- \
modulated. If a number is not in the text, DO NOT report it. Never infer an amount from comparable \
programs. Precision beats recall: fewer, certain citations are better — when in doubt, omit.\
"""

USER_TEMPLATE = """\
Bill: {state} {bill_number} — {title}

Compliance details (your ONLY source; quote from it verbatim):
{evidence}

Return ONLY valid JSON, no prose:
{{
  "citations": [
    {{
      "fact_type": <one of: {fact_types}>,
      "extracted_value": <number stated in the text, or null if the bill names the fact without a number>,
      "value_unit": "<e.g. usd_per_tonne, usd_per_unit, usd, usd_revenue, tonnes, percent, or null>",
      "source_excerpt": "<SHORT verbatim substring (<=30 words) copied from the text that states this fact>",
      "confidence": <float 0.0-1.0>
    }}
  ]
}}

Fact definitions (a PRODUCER-PAID amount, unless noted):
- fee_per_ton: a per-tonne producer fee amount the producer pays, stated in the bill (rare). unit usd_per_tonne.
- fee_per_unit_usd: a per-unit producer fee the producer pays, stated in the bill. unit usd_per_unit.
  NOT a deposit/refund/incentive paid to a consumer or technician for returning an item.
- registration_fee_usd: a flat fee an INDIVIDUAL producer pays to register / join / renew. unit usd.
  NOT an aggregate or program-wide total, and NOT an agency oversight-cost cap.
- producer_revenue_threshold: the annual-gross-revenue FLOOR (in dollars) below which a producer is exempt
  (de-minimis). unit usd_revenue. A percentage is NOT a revenue threshold.
- producer_tonnage_threshold: the tonnage/volume FLOOR below which a producer is exempt. unit tonnes.
- eco_modulation: the bill states fees are adjusted up/down by product design (value optional).

DO NOT report (these are the common false positives — omit them):
- consumer deposits, refunds, rebates, or collection incentives/bounties paid TO consumers/retailers/technicians;
- government procurement price-preference percentages (e.g. "recycled product within 10% of the price");
- recycling-rate, recycled-content, or diversion-rate percentage targets;
- aggregate / program-wide funding totals, or agency oversight-cost caps (not a per-producer fee).

Rules:
- source_excerpt MUST be copied exactly from the compliance details text above (it is verified as a
  substring; fabricated or paraphrased quotes are discarded) and MUST be short (at most ~30 words) —
  quote just the clause that states the fact, not a whole paragraph.
- If you give an extracted_value, the number MUST appear in your source_excerpt, and the excerpt must
  show the producer PAYS it (or, for thresholds, that it sets who is exempt/covered).
- Report a fact only if the text states it. If the text gives no producer fee or coverage threshold,
  return {{"citations": []}}.
- Emit at most one citation per fact_type.
"""


@dataclass
class FeeCitation:
    bill_id: int
    state: str
    bill_number: str | None
    fact_type: str
    basis: str
    extracted_value: float | None
    value_unit: str | None
    source_excerpt: str | None
    source_url: str | None
    notes: str | None
    confidence: float | None

    @property
    def grounded(self) -> bool:
        return self.basis in GROUNDED_BASES

    def to_dict(self) -> dict:
        return {
            "bill_id": self.bill_id,
            "state": self.state,
            "bill_number": self.bill_number,
            "fact_type": self.fact_type,
            "basis": self.basis,
            "extracted_value": self.extracted_value,
            "value_unit": self.value_unit,
            "source_excerpt": self.source_excerpt,
            "source_url": self.source_url,
            "notes": self.notes,
            "confidence": self.confidence,
            "grounded": self.grounded,
        }


def _norm(text: str) -> str:
    """Whitespace-collapsed, lowercased — for substring provenance checks."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _value_digits_present(value: float, excerpt: str) -> bool:
    """True if the value's integer-part digit run appears in the excerpt.

    Catches a model attaching a (plausible) number to a clause that doesn't contain it. Lenient on
    formatting: matches digit runs with thousands separators stripped, so "1,500" and "1500" both pass.
    """
    digits = str(int(abs(value)))
    excerpt_digits = re.sub(r"[,\s]", "", excerpt)
    return digits in excerpt_digits


def build_fee_evidence_corpus(details: dict) -> str:
    """Flatten the fee/threshold-relevant compliance_details fields into one quotable block."""
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
        if fees.get("details"):
            parts.append(f"- fee details: {str(fees['details']).strip()}")
        if fees.get("fee_notes"):
            parts.append(f"- fee notes: {str(fees['fee_notes']).strip()}")
    return "\n".join(parts)


def validate_citations(
    raw: list[dict], corpus: str, bill: dict
) -> tuple[list[FeeCitation], int]:
    """Keep only well-formed enacted_text citations whose excerpt — and number — are in the corpus.

    Returns (valid_citations, n_dropped). Dropping is the chain-of-custody guarantee: a citation with a
    hallucinated quote, or a number that isn't in the quoted clause, cannot enter the dataset.
    """
    corpus_norm = _norm(corpus)
    valid: list[FeeCitation] = []
    seen: set[str] = set()
    dropped = 0
    for c in raw:
        fact = str(c.get("fact_type", "")).strip()
        excerpt = str(c.get("source_excerpt", "")).strip()
        if fact not in FACT_TYPES or fact in seen:
            dropped += 1
            continue
        # Excerpt must be a real, non-trivial substring of the source text.
        if len(_norm(excerpt)) < 12 or _norm(excerpt) not in corpus_norm:
            dropped += 1
            continue
        unit = (str(c.get("value_unit")).strip().lower() if c.get("value_unit") else None)
        # A dollar fact tagged with a percent unit is a mis-tag (procurement %, rate target) — drop it.
        if fact in _DOLLAR_FACTS and unit and ("percent" in unit or "%" in unit):
            dropped += 1
            continue
        val = c.get("extracted_value")
        try:
            val = float(val) if val is not None else None
        except (TypeError, ValueError):
            val = None
        # Require a real number for every fact except eco_modulation (which is legitimately a
        # value-less "fees are design-modulated" flag). A value-less fee/threshold is almost always
        # the model surfacing program-funding or cost-recovery language it should have omitted.
        if val is None and fact != "eco_modulation":
            dropped += 1
            continue
        # If a number is claimed, it must appear in the quoted clause.
        if val is not None and not _value_digits_present(val, excerpt):
            dropped += 1
            continue
        seen.add(fact)
        valid.append(FeeCitation(
            bill_id=bill["id"],
            state=bill["state"],
            bill_number=bill.get("bill_number"),
            fact_type=fact,
            basis="enacted_text",
            extracted_value=val,
            value_unit=(str(c.get("value_unit")).strip() if c.get("value_unit") else None),
            source_excerpt=excerpt[:400],
            source_url=None,
            notes=None,
            confidence=max(0.0, min(1.0, float(c.get("confidence", 0.0) or 0.0))),
        ))
    return valid, dropped


def citations_from_curated_fees(bill: dict) -> list[FeeCitation]:
    """Turn a bill's curated compliance_details.fees block into published_schedule / benchmark
    citations — no LLM. This is the provenance record for fees set by agency/PRO rulemaking rather
    than the statute (the *_published and *_benchmark rows from scripts/enrich_bill_fees.py).

    Emits one citation per numeric fee field present, tagged by basis derived from
    fee_structure_source. `fee_notes` is carried into `notes` so the methodology travels with the row.
    `source_url`, when present in the fees block, anchors a published_schedule citation to its schedule.
    """
    details = bill.get("compliance_details") or {}
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            return []
    fees = details.get("fees")
    if not isinstance(fees, dict):
        return []

    source = str(fees.get("fee_structure_source") or "").strip()
    basis = _SOURCE_TO_BASIS.get(source)
    if basis is None:
        return []  # no_fee_data / no_monetary_fee / unknown — nothing curated to cite

    notes = str(fees.get("fee_notes")).strip() if fees.get("fee_notes") else None
    url = str(fees.get("source_url")).strip() if fees.get("source_url") else None
    out: list[FeeCitation] = []
    field_units = [
        ("fee_per_ton", "usd_per_tonne"),
        ("fee_per_unit_usd", "usd_per_unit"),
        ("registration_fee_usd", "usd"),
    ]
    for field, unit in field_units:
        val = fees.get(field)
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        out.append(FeeCitation(
            bill_id=bill["id"],
            state=bill["state"],
            bill_number=bill.get("bill_number"),
            fact_type=field,
            basis=basis,
            extracted_value=val,
            value_unit=unit,
            source_excerpt=None,
            source_url=url,
            notes=f"[{source}] {notes}" if notes else f"[{source}]",
            confidence=None,
        ))
    return out


class FeeCitationExtractor:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=60.0, max_retries=0
        )

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    async def _call(self, prompt: str) -> str:
        resp = await self._client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=2000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    async def extract(self, bill: dict) -> tuple[list[FeeCitation], int]:
        """bill: {id, state, bill_number, title, compliance_details(dict)}.

        Returns (validated enacted_text citations, n_dropped_for_provenance). Does NOT include the
        curated published_schedule/benchmark rows — combine with citations_from_curated_fees(bill).
        """
        details = bill.get("compliance_details") or {}
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                return [], 0
        corpus = build_fee_evidence_corpus(details)
        if not corpus.strip():
            return [], 0

        prompt = USER_TEMPLATE.format(
            state=bill["state"],
            bill_number=bill.get("bill_number") or "?",
            title=(bill.get("title") or "")[:200],
            evidence=corpus[:8000],
            fact_types="|".join(FACT_TYPES),
        )
        raw_text = await self._call(prompt)
        # Strip a leading ```json / ``` code fence the model sometimes adds before parsing.
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip())
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            try:
                data = json.loads(m.group()) if m else {}
            except json.JSONDecodeError:
                log.warning("fee_citation_parse_failed", bill_id=bill.get("id"), raw=raw_text[:200])
                return [], 0
        return validate_citations(data.get("citations", []), corpus, bill)
