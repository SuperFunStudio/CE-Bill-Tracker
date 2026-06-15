import json
from dataclasses import dataclass

import anthropic
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Instruments that are circular-economy policy by definition. A bill the classifier tags with
# one of these is in scope on its own, independent of the narrow "is_epr_relevant" judgment:
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
# "other"). They ride into scope via is_epr_relevant=True — the system prompt explicitly names
# the biological cycle as relevant — rather than a tracked-instrument tag. (We don't auto-track
# on material because material_categories is a loose multi-value tag and would over-capture,
# e.g. a pesticide bill tagged "agriculture".)
# "labeling" and "preemption" are deliberately NOT here. Both are generic instruments that apply
# far outside circular-economy policy — ingredient/nutrition/country-of-origin labeling, or
# preemption of tobacco, firearm, employment, and tax rules. Counting them in scope on the tag
# alone forced obvious non-EPR bills into the tracker (WV HB-4985 foreign-ownership preemption,
# WI AB-1213 menstrual-product labeling, OK firearm preemption) whose own reasoning said "not
# product stewardship, EPR, or circular economy policy". So a labeling/preemption bill now
# counts as in scope only when the classifier independently set is_epr_relevant=True (recycling-
# label mandates, preemption of bottle-bill / EPR laws). scripts/hide_negated_labeling_preemption.py
# applies the same correction to existing rows.
# "chemical_restriction", "budget" (generic appropriations), and "other" are excluded for the
# same reason: not circular-economy instruments. chemical_restriction surfaced chemical-safety
# bills like CA SB-236 (hair relaxer ingredients). The classifier may still tag a bill with any
# of these; it just won't count as in-scope on that basis alone.
# "incentives" — the FINANCIAL lever (tax credits/deductions/rebates, appropriations/grants/
# funding programs, procurement/tenders) — is also NOT tracked: it rides into scope via
# is_epr_relevant, like the biological cycle, because money only counts when it funds a
# circular-economy outcome (a recycling grant or compost tax credit — yes; a generic
# appropriation — no). It supersedes the in-scope use of "budget", which now means only
# circularity-unrelated appropriations. See scripts/reclassify_incentives.py.

SYSTEM_PROMPT = """\
You are an expert in US environmental policy and Extended Producer Responsibility (EPR) legislation. \
Analyze legislative bills and classify their relevance to EPR, product stewardship, circular economy policy, \
right-to-repair, recycled content mandates, deposit return schemes, or federal preemption of such laws. \
Circular economy scope includes both the technical cycle (the above) and the biological cycle: \
bio-based / biomanufactured materials (biopolymers, bioplastics, compostable materials), regenerative \
agriculture & soil health (healthy soils, cover crops, carbon farming, biochar), and organics recycling / \
composting infrastructure (source-separated organics, anaerobic digestion, compost market development).\
"""

USER_TEMPLATE = """\
Analyze this US legislative bill and respond with ONLY valid JSON — no prose, no markdown.

State: {state}
Bill: {bill_number}
Title: {title}
Description: {description}
Text excerpt (first 2000 chars):
{text_excerpt}

Return this exact JSON structure:
{{
  "is_epr_relevant": <true or false>,
  "confidence": <float 0.0-1.0>,
  "material_categories": <list from: ["plastic_packaging","paper_packaging","glass","metals","electronics","batteries","paint","carpet","mattresses","tires","pharmaceuticals","solar_panels","textiles","organics","biobased","agriculture","other"]>,
  "instrument_type": <one of: "epr","right_to_repair","recycled_content","deposit_return","incentives","labeling","chemical_restriction","preemption","budget","other">,
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

Biological cycle: bills on bio-based / biomanufactured materials (biopolymers, bioplastics,
compostable materials), regenerative agriculture & soil health (healthy soils, cover crops,
carbon farming, biochar), or organics recycling / composting (source-separated organics,
anaerobic digestion, compost market development) ARE circular-economy relevant — set
is_epr_relevant=true. Tag their material as "biobased", "agriculture", or "organics"; set
instrument_type to the actual policy lever (a standard/ban → its type; a financial lever →
"incentives"; else "other").

Incentives: when the bill's PRIMARY lever is financial — a tax credit / deduction / rebate, an
appropriation / grant / funding program, or a public procurement / tender — and it funds a
circular-economy or biological-cycle outcome (recycling, reuse, repair, composting, soil
health, bio-based materials, an EPR/stewardship program), set instrument_type="incentives" and
is_epr_relevant=true. A generic appropriation NOT tied to a circular-economy outcome is "budget".
"""


_VALID_STANCES = frozenset({"advances", "weakens", "neutral"})


@dataclass
class HaikuResult:
    is_epr_relevant: bool
    confidence: float
    material_categories: list[str]
    instrument_type: str
    urgency: str
    reasoning: str
    stance: str = "neutral"
    raw_response: str = ""


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
    ) -> HaikuResult:
        prompt = USER_TEMPLATE.format(
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
            system=SYSTEM_PROMPT,
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
                    is_epr_relevant=False,
                    confidence=0.0,
                    material_categories=[],
                    instrument_type="other",
                    urgency="low",
                    reasoning="parse_error",
                    raw_response=raw,
                )
        stance = str(data.get("stance", "neutral")).lower()
        if stance not in _VALID_STANCES:
            stance = "neutral"
        return HaikuResult(
            is_epr_relevant=data.get("is_epr_relevant", False),
            confidence=float(data.get("confidence", 0.0)),
            material_categories=data.get("material_categories", []),
            instrument_type=data.get("instrument_type", "other"),
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
                )
                results.append((bill, result))
            except Exception as e:
                log.error("haiku_classify_failed", bill_number=bill.get("bill_number"), error=str(e), error_type=type(e).__name__)
        return results
