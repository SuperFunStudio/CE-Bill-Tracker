import json
from dataclasses import dataclass, field

import anthropic
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Instruments that are circular-economy policy by definition. A bill the classifier tags with
# one of these is in scope on its own, independent of the narrow "is_ce_relevant" judgment:
# right-to-repair, deposit-return, etc. are tracked policy instruments even though they aren't
# EPR in the strict sense (e.g. CA SB-244 "Right to Repair Act").
TRACKED_INSTRUMENTS = frozenset({
    "epr", "right_to_repair", "recycled_content", "deposit_return",
})
# The biological cycle of the circular economy — bio-based / biomanufactured materials,
# regenerative agriculture & soil health, organics recycling / composting — is in scope too,
# but it's modeled on the MATERIAL axis (material_categories: "biobased", "agriculture",
# "organics"), not as instruments. Those bills use ordinary policy levers (grants, incentives,
# standards, disposal bans), so their instrument_type is whatever mechanism applies (often
# "other"). They ride into scope via is_ce_relevant=True — the system prompt explicitly names
# the biological cycle as relevant — rather than a tracked-instrument tag. (We don't auto-track
# on material because material_categories is a loose multi-value tag and would over-capture,
# e.g. a pesticide bill tagged "agriculture".)
# "labeling" and "preemption" are deliberately NOT here. Both are generic instruments that apply
# far outside circular-economy policy — ingredient/nutrition/country-of-origin labeling, or
# preemption of tobacco, firearm, employment, and tax rules. Counting them in scope on the tag
# alone forced obvious non-EPR bills into the tracker (WV HB-4985 foreign-ownership preemption,
# WI AB-1213 menstrual-product labeling, OK firearm preemption) whose own reasoning said "not
# product stewardship, EPR, or circular economy policy". So a labeling/preemption bill now
# counts as in scope only when the classifier independently set is_ce_relevant=True (recycling-
# label mandates, preemption of bottle-bill / EPR laws). scripts/hide_negated_labeling_preemption.py
# applies the same correction to existing rows.
# "chemical_restriction", "budget" (generic appropriations), and "other" are excluded for the
# same reason: not circular-economy instruments. chemical_restriction surfaced chemical-safety
# bills like CA SB-236 (hair relaxer ingredients). The classifier may still tag a bill with any
# of these; it just won't count as in-scope on that basis alone.
# "incentives" — the FINANCIAL lever (tax credits/deductions/rebates, appropriations/grants/
# funding programs, procurement/tenders) — is also NOT tracked: it rides into scope via
# is_ce_relevant, like the biological cycle, because money only counts when it funds a
# circular-economy outcome (a recycling grant or compost tax credit — yes; a generic
# appropriation — no). It supersedes the in-scope use of "budget", which now means only
# circularity-unrelated appropriations. See scripts/reclassify_incentives.py.

# Region code -> human label injected into the prompts. The taxonomy (instruments, materials) is
# region-neutral; only the framing changes so the same classifier works on EU/UK text. See
# plan serene-munching-brook (EU lean spike).
REGION_LABELS = {
    "US": "United States",
    "EU": "European Union",
    "UK": "United Kingdom",
    "JP": "Japan",
    "FR": "France",
    "DE": "Germany",
    "NL": "Netherlands",
    "ES": "Spain",
    "CL": "Chile",
    "SE": "Sweden",
    "IE": "Ireland",
    "AT": "Austria",
    "BR": "Brazil",
    "CH": "Switzerland",
    "PL": "Poland",
    "KR": "South Korea",
    "ZA": "South Africa",
    "KE": "Kenya",
    "DK": "Denmark",
    "FI": "Finland",
    "LU": "Luxembourg",
    "EE": "Estonia",
    "LV": "Latvia",
    "SK": "Slovakia",
    "LT": "Lithuania",
    "SI": "Slovenia",
    "CZ": "Czechia",
}


def region_label(region: str | None) -> str:
    return REGION_LABELS.get((region or "US").upper(), region or "United States")


SYSTEM_PROMPT_TEMPLATE = """\
You are an expert in {region} environmental policy and Extended Producer Responsibility (EPR) legislation. \
Analyze legislative and regulatory measures and classify their relevance to EPR, product stewardship, \
circular economy policy, right-to-repair, recycled content mandates, deposit return schemes, or measures \
that preempt or override such laws. \
Circular economy scope includes both the technical cycle (the above) and the biological cycle: \
bio-based / biomanufactured materials (biopolymers, bioplastics, compostable materials), regenerative \
agriculture & soil health (healthy soils, cover crops, carbon farming, biochar), and organics recycling / \
composting infrastructure (source-separated organics, anaerobic digestion, compost market development).\
"""

USER_TEMPLATE = """\
Analyze this {region} legislative or regulatory measure and respond with ONLY valid JSON — no prose, no markdown.

Jurisdiction: {state}
Bill: {bill_number}
Title: {title}
Description: {description}
Text excerpt (first 2000 chars):
{text_excerpt}

Return this exact JSON structure:
{{
  "is_ce_relevant": <true or false>,
  "confidence": <float 0.0-1.0>,
  "material_categories": <list from: ["plastic_packaging","paper_packaging","glass","metals","electronics","batteries","paint","carpet","mattresses","tires","vehicles","construction","furniture","used_oil","pharmaceuticals","solar_panels","textiles","organics","biobased","agriculture","hazardous_materials","other"]>,
  "instrument_types": <list of one or more from: "epr","right_to_repair","recycled_content","deposit_return","incentives","labeling","chemical_restriction","preemption","budget","other"; put the primary/most-central instrument FIRST. A law is often several at once (e.g. an EPR law with recycled-content + labeling mandates)>,
  "stance": <one of: "advances","weakens","neutral">,
  "urgency": <one of: "high","medium","low">,
  "reasoning": "<1 sentence max>"
}}

Stance = the bill's direction relative to its instrument, NOT whether you favor it:
  - "advances": establishes, strengthens, broadens, or funds the policy (e.g. creates a
    repair mandate or EPR program), OR repeals/limits a preemption that blocked it.
  - "weakens": exempts or carves out products/entities from the policy, narrows its scope,
    repeals it, or newly preempts local authority to enact it. A small-producer carve-out
    inside an otherwise-establishing bill is still "advances" — judge the bill's net effect.
  - "neutral": study/task-force/appropriations-only/administrative, or genuinely unclear.

Urgency guide: high = enrolled/passed/enacted or imminent deadline; medium = passed committee or floor vote scheduled; low = introduced/early committee.

Missing text: if no text excerpt (and little/no description) is provided, classify from the TITLE.
A title that is itself an unambiguous in-scope signal — it names extended producer responsibility or
"producer responsibility", packaging/plastic reduction, recycled content, right to repair, a deposit
return / bottle bill, single-use plastic restrictions, organics/compost diversion, or circular
economy — is sufficient to set is_ce_relevant=true with confidence >= 0.6. Do NOT set
is_ce_relevant=false or report low confidence MERELY because the full text is unavailable; only do so
when the title/description themselves indicate the bill is out of scope.

Biological cycle: bills on bio-based / biomanufactured materials (biopolymers, bioplastics,
compostable materials), regenerative agriculture & soil health (healthy soils, cover crops,
carbon farming, biochar), or organics recycling / composting (source-separated organics,
anaerobic digestion, compost market development) ARE circular-economy relevant — set
is_ce_relevant=true. Tag their material as "biobased", "agriculture", or "organics"; include the
actual policy lever in instrument_types (a standard/ban → its type; a financial lever →
"incentives"; else "other").

Incentives: when the bill's PRIMARY lever is financial — a tax credit / deduction / rebate, an
appropriation / grant / funding program, or a public procurement / tender — and it funds a
circular-economy or biological-cycle outcome (recycling, reuse, repair, composting, soil
health, bio-based materials, an EPR/stewardship program), include "incentives" in instrument_types
and set is_ce_relevant=true. A generic appropriation NOT tied to a circular-economy outcome is "budget".

Material notes: "vehicles" = end-of-life vehicles / automotive recycling (ELV). "construction" =
construction & demolition materials (concrete, aggregate, lumber, gypsum). "furniture" = furniture
and mattresses-adjacent furnishings EPR. "used_oil" = used lubricating/motor oil stewardship.
"""


_VALID_STANCES = frozenset({"advances", "weakens", "neutral"})


@dataclass
class HaikuResult:
    is_ce_relevant: bool
    confidence: float
    material_categories: list[str]
    instrument_type: str  # representative "primary" (first of instrument_types)
    urgency: str
    reasoning: str
    stance: str = "neutral"
    instrument_types: list[str] = field(default_factory=list)  # full set, primary first
    raw_response: str = ""


def _parse_instruments(data: dict) -> list[str]:
    """Read instrument_types (list) with back-compat for the old single instrument_type. Cleans
    blanks, dedups (order-preserving), defaults to ['other']."""
    raw = data.get("instrument_types")
    if not isinstance(raw, list):
        one = data.get("instrument_type")
        raw = [one] if one else []
    out: list[str] = []
    for i in raw:
        if isinstance(i, str) and i and i not in out:
            out.append(i)
    return out or ["other"]


class HaikuClassifier:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        # 60s per-request timeout so a hung call fails fast and the retry wrapper handles it,
        # rather than the SDK's long default timeout freezing a whole classification batch.
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=60.0, max_retries=0
        )

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    async def classify(
        self,
        state: str,
        bill_number: str,
        title: str,
        description: str = "",
        text_excerpt: str = "",
        region: str = "US",
    ) -> HaikuResult:
        label = region_label(region)
        prompt = USER_TEMPLATE.format(
            region=label,
            state=state,
            bill_number=bill_number or "Unknown",
            title=title or "",
            description=(description or "")[:500],
            text_excerpt=text_excerpt[:2000],
        )
        resp = await self._client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=400,
            temperature=0,
            system=SYSTEM_PROMPT_TEMPLATE.format(region=label),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try extracting JSON from response
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                log.warning("haiku_json_parse_failed", raw=raw[:200])
                return HaikuResult(
                    is_ce_relevant=False,
                    confidence=0.0,
                    material_categories=[],
                    instrument_type="other",
                    instrument_types=["other"],
                    urgency="low",
                    reasoning="parse_error",
                    raw_response=raw,
                )
        stance = str(data.get("stance", "neutral")).lower()
        if stance not in _VALID_STANCES:
            stance = "neutral"
        instruments = _parse_instruments(data)
        return HaikuResult(
            is_ce_relevant=data.get("is_ce_relevant", False),
            confidence=float(data.get("confidence", 0.0)),
            material_categories=data.get("material_categories", []),
            instrument_type=instruments[0],
            instrument_types=instruments,
            urgency=data.get("urgency", "low"),
            reasoning=data.get("reasoning", ""),
            stance=stance,
            raw_response=raw,
        )

    async def classify_batch(
        self,
        bills: list[dict],
        max_calls: int = 100,
    ) -> list[tuple[dict, HaikuResult]]:
        """Classify up to max_calls bills. Each bill dict needs: state, bill_number, title, description."""
        results = []
        for bill in bills[:max_calls]:
            try:
                result = await self.classify(
                    state=bill.get("state", ""),
                    bill_number=bill.get("bill_number", ""),
                    title=bill.get("title", ""),
                    description=bill.get("description", ""),
                    text_excerpt=bill.get("text_excerpt", ""),
                    region=bill.get("region", "US"),
                )
                results.append((bill, result))
            except Exception as e:
                log.error("haiku_classify_failed", bill_number=bill.get("bill_number"), error=str(e), error_type=type(e).__name__)
        return results
