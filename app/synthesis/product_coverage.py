"""Covered-product extraction: turn a bill's full text into cited per-product coverage rows.

The sibling of app/synthesis/design_levers.py, with the same chain-of-custody guarantee — every
coverage row carries a VERBATIM `source_excerpt` and `validate_coverages` drops any row whose
excerpt is not a substring of the bill text, so a product can never be marked "covered" on a clause
that isn't really in the bill. Unlike design_levers (which reads the already-stored
compliance_details), Phase 0 found only 7/270 electronics bills had that JSON, so this reads the
bill's FULL TEXT (fetched via OpenStatesClient.get_text_from_source) and appends any compliance
prose as extra evidence.

The product vocabulary is the controlled taxonomy in app/synthesis/product_taxonomy.py. The bill's
obligation (`relationship_type`) is decided by the script from the bill's instrument_type — EPR →
stewarded, right-to-repair → repairable, deposit_return → deposit_return — NOT by the model; the
model only decides which products are covered/exempt/conditional and quotes the supporting clause.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import anthropic
import structlog

from app.config import settings
from app.synthesis.product_taxonomy import (
    BY_SLUG,
    STATUSES,
    is_valid,
    products_for,
    vocab_block,
)
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MODELS = {"sonnet": SONNET_MODEL, "haiku": HAIKU_MODEL}

# Which obligation each instrument_type implies. Bills outside this map are pre-filtered out by the
# backfill script (other / budget / preemption / recycled_content don't enumerate covered products).
RELATIONSHIP_BY_INSTRUMENT = {
    "epr": "stewarded",
    "right_to_repair": "repairable",
    "deposit_return": "deposit_return",
}

# compliance_details keys appended to the bill text as extra quotable evidence (when present).
_PROSE_FIELDS = ("covered_products", "exemptions", "producer_definition")

SYSTEM_PROMPT = """\
You are an EPR compliance analyst mapping a US circular-economy bill onto a fixed catalog of \
products. Decide, for EACH catalog product, whether THIS bill covers it, exempts it, or covers it \
only conditionally (e.g. above a size/energy threshold). Quote the bill verbatim for every call. \
Precision beats recall: if the bill does not actually reach a product, omit it. Do NOT invent \
products that aren't in the catalog.\
"""

USER_TEMPLATE = """\
Bill: {state} {bill_number} - {title}
This bill's obligation is: {relationship} ({relationship_desc}).

Product catalog (use these exact slugs; ignore everything not in this list):
{catalog}

Bill text (your ONLY source — quote from it verbatim):
\"\"\"
{text}
\"\"\"

Call report_coverage. Rules:
- source_excerpt MUST be copied exactly from the bill text above; it is verified as a substring and
  fabricated or paraphrased quotes are discarded.
- "products": one entry per catalog product the bill names or thresholds INDIVIDUALLY. status:
  "covered"=named in scope; "exempt"=explicitly carved out (quote the carve-out clause);
  "conditional"=covered only past a stated threshold (fill threshold_value/unit from the clause).
- "blanket": MANY laws (esp. right-to-repair) define their reach as an ENTIRE class — e.g. "any
  digital electronic equipment", "all covered electronic devices" — without listing device types.
  When the bill does this, set blanket.is_blanket=true and put the verbatim class-definition clause
  in blanket.scope_excerpt; the system expands it to cover every applicable product. Then list each
  explicitly carved-out product as an "exempt" entry in "products" (quoting its carve-out clause).
  Do NOT hand-enumerate the covered devices for a blanket law — that's what blanket does.
  CRITICAL: if this bill's obligation is "repairable" and it defines a broad equipment class (e.g.
  "digital electronic equipment means any product..."), it IS blanket — set is_blanket=true and
  quote that definition. Returning is_blanket=false with no covered products for such a bill is wrong.
- defined_by_reference=true when a product is covered only by pointing at an existing statute
  ("as defined under ORS Chapter 459A") rather than naming it here.
- Precision beats recall. If the bill is neither blanket nor names any catalog product, return
  empty products and blanket.is_blanket=false.
"""

# Forced-tool schema: guarantees structured output (Sonnet 4.6 rejects assistant prefill, and on raw
# bill text it otherwise preambles with prose and exhausts the token budget before emitting JSON).
COVERAGE_TOOL = {
    "name": "report_coverage",
    "description": "Report which catalog products this bill covers, exempts, or conditionally covers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "products": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "an exact catalog slug"},
                        "status": {"type": "string", "enum": list(STATUSES)},
                        "source_excerpt": {
                            "type": "string",
                            "description": "verbatim substring copied from the bill text",
                        },
                        "defined_by_reference": {"type": "boolean"},
                        "threshold_value": {"type": ["number", "null"]},
                        "threshold_unit": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                    },
                    "required": ["slug", "status", "source_excerpt", "confidence"],
                },
            },
            "blanket": {
                "type": "object",
                "description": "Set when the bill covers an entire product class without enumerating.",
                "properties": {
                    "is_blanket": {"type": "boolean"},
                    "scope_excerpt": {
                        "type": "string",
                        "description": "verbatim class-definition clause from the bill text",
                    },
                },
                "required": ["is_blanket"],
            },
        },
        "required": ["products"],
    },
}

_REL_DESC = {
    "stewarded": "producer must fund/run end-of-life stewardship",
    "repairable": "product must be made serviceable / repairable",
    "deposit_return": "a deposit/refund value attaches to the product",
}


@dataclass
class ProductCoverage:
    bill_id: int
    state: str
    bill_number: str | None
    category: str
    product_slug: str
    relationship_type: str
    status: str
    defined_by_reference: bool
    source_excerpt: str
    threshold_value: float | None
    threshold_unit: str | None
    confidence: float

    def to_dict(self) -> dict:
        return {
            "bill_id": self.bill_id,
            "state": self.state,
            "bill_number": self.bill_number,
            "category": self.category,
            "product_slug": self.product_slug,
            "relationship_type": self.relationship_type,
            "status": self.status,
            "defined_by_reference": self.defined_by_reference,
            "source_excerpt": self.source_excerpt,
            "threshold_value": self.threshold_value,
            "threshold_unit": self.threshold_unit,
            "confidence": self.confidence,
        }


# Unicode punctuation the model silently "cleans" when quoting PDF/HTML bill text — folding these
# before the substring check prevents false provenance drops (smart quotes, dashes, nbsp).
_PUNCT_FOLD = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
})


def _norm(text: str) -> str:
    """Whitespace-collapsed, lowercased, punctuation-folded — for substring provenance checks."""
    return re.sub(r"\s+", " ", text.translate(_PUNCT_FOLD)).strip().lower()


def _grounded(excerpt: str, corpus_norm: str) -> bool:
    """Provenance check: the excerpt must be verbatim in the bill text. Long quotes (e.g. a 350-char
    statutory definition) are reproduced imperfectly mid-string by the model — one cleaned character
    anywhere breaks an exact full match — so we require a verbatim PREFIX. 40 chars of exact match is
    strong evidence the quote is real (a fabricated quote can't reproduce the bill's opening words),
    while staying robust to mid-quote drift. Short excerpts (<40) are matched in full."""
    e = _norm(excerpt)
    if len(e) < 12:
        return False
    return e[:40] in corpus_norm


def build_corpus(full_text: str, details: dict | None) -> str:
    """Bill text plus any compliance prose, as one quotable block the excerpt must come from."""
    parts: list[str] = []
    if full_text and full_text.strip():
        parts.append(full_text.strip())
    if details:
        for f in _PROSE_FIELDS:
            val = details.get(f)
            if not val:
                continue
            if isinstance(val, list):
                parts.extend(str(x).strip() for x in val if str(x).strip())
            else:
                parts.append(str(val).strip())
    return "\n".join(parts)


def validate_coverages(
    raw: list[dict], corpus: str, bill: dict, relationship: str
) -> tuple[list[ProductCoverage], int]:
    """Keep only well-formed rows whose excerpt is verbatim-present and whose product accepts
    this bill's relationship. Returns (valid, n_dropped). Dropping is the chain of custody."""
    corpus_norm = _norm(corpus)
    valid: list[ProductCoverage] = []
    dropped = 0
    seen: set[str] = set()
    for r in raw:
        slug = str(r.get("slug", "")).strip()
        status = str(r.get("status", "")).strip()
        excerpt = str(r.get("source_excerpt", "")).strip()
        # Unknown product, status, or a product that can't carry this obligation (e.g. an
        # EV battery returned as "repairable") — drop.
        if not is_valid(slug, relationship) or status not in STATUSES or slug in seen:
            dropped += 1
            continue
        # Excerpt must be verbatim-grounded in the bill text (prefix-match for long quotes).
        if not _grounded(excerpt, corpus_norm):
            dropped += 1
            continue
        tv = r.get("threshold_value")
        try:
            tv = float(tv) if tv is not None else None
        except (TypeError, ValueError):
            tv = None
        seen.add(slug)
        valid.append(ProductCoverage(
            bill_id=bill["id"],
            state=bill["state"],
            bill_number=bill.get("bill_number"),
            category=BY_SLUG[slug].category,
            product_slug=slug,
            relationship_type=relationship,
            status=status,
            defined_by_reference=bool(r.get("defined_by_reference", False)),
            source_excerpt=excerpt[:400],
            threshold_value=tv,
            threshold_unit=(str(r.get("threshold_unit")).strip()[:40] if r.get("threshold_unit") else None),
            confidence=max(0.0, min(1.0, float(r.get("confidence", 0.0) or 0.0))),
        ))
    return valid, dropped


class ProductCoverageExtractor:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None, model: str = SONNET_MODEL):
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=60.0, max_retries=0
        )
        self.model = model

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    async def _call(self, prompt: str) -> dict:
        resp = await self._client.messages.create(
            model=self.model,
            max_tokens=2500,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            tools=[COVERAGE_TOOL],
            tool_choice={"type": "tool", "name": "report_coverage"},
        )
        for block in resp.content:
            if block.type == "tool_use":
                return block.input or {}
        return {}

    async def extract(self, bill: dict, max_chars: int = 14000) -> tuple[list[ProductCoverage], int]:
        """bill: {id, state, bill_number, title, instrument_type, categories[list], full_text,
        compliance_details(dict|None)}. Returns (validated coverages, n_dropped_for_provenance).

        max_chars caps the bill-text window sent to the model (~4 chars/token). The default suits
        most bills; raise it for long bills whose product definitions sit far in (e.g. OLIS pages
        carry ~18K of nav chrome before the bill text)."""
        relationship = RELATIONSHIP_BY_INSTRUMENT.get(bill.get("instrument_type") or "")
        if relationship is None:
            return [], 0

        corpus = build_corpus(bill.get("full_text") or "", bill.get("compliance_details"))
        if len(corpus.strip()) < 40:  # nothing to quote from
            return [], 0

        # Catalog = the union of the bill's tagged categories' products.
        cats = [c for c in (bill.get("categories") or []) if products_for(c)]
        if not cats:
            return [], 0
        catalog = "\n".join(vocab_block(c) for c in cats)

        prompt = USER_TEMPLATE.format(
            state=bill["state"],
            bill_number=bill.get("bill_number") or "?",
            title=(bill.get("title") or "")[:200],
            relationship=relationship,
            relationship_desc=_REL_DESC.get(relationship, relationship),
            catalog=catalog,
            text=corpus[:max_chars],
        )
        data = await self._call(prompt)
        coverages, dropped = validate_coverages(data.get("products", []), corpus, bill, relationship)

        # Blanket laws ("any digital electronic equipment") cover the whole class: the model flags
        # is_blanket + the verbatim scope clause, and we expand it deterministically rather than
        # trusting the model to hand-enumerate (which it does unreliably). Explicit per-product
        # entries above win — blanket only fills the products the model didn't already address.
        blanket = data.get("blanket") or {}
        if blanket.get("is_blanket"):
            excerpt = str(blanket.get("scope_excerpt", "")).strip()
            if _grounded(excerpt, _norm(corpus)):
                seen = {c.product_slug for c in coverages}
                for cat in cats:
                    for p in products_for(cat):
                        if (p.blanket_expand and p.slug not in seen
                                and relationship in p.relationships):
                            seen.add(p.slug)
                            coverages.append(ProductCoverage(
                                bill_id=bill["id"], state=bill["state"],
                                bill_number=bill.get("bill_number"), category=p.category,
                                product_slug=p.slug, relationship_type=relationship,
                                status="covered", defined_by_reference=True,
                                source_excerpt=excerpt[:400], threshold_value=None,
                                threshold_unit=None, confidence=0.7,
                            ))
        return coverages, dropped
