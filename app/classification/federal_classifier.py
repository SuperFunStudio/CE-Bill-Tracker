"""Federal-action classifier — turns the noisy Federal Register feed into a friction signal.

The Federal Register term search (app/ingestion/federal_register.py) is a blunt full-text
match: a query like "deposit return scheme" or "dormant commerce clause packaging" drags in
antidumping notices, antitrust judgments, and trade determinations that have nothing to do with
EPR. This classifier is the filter. For each federal action it decides:

  - is_relevant: does this actually touch EPR / product stewardship / packaging / recycling /
    right-to-repair / recycled-content / a federal preemption of such laws?
  - preemption_risk ("none"/"low"/"medium"/"high"): the friction score — how much this federal
    action threatens, preempts, or burdens state EPR programs. This is the number that answers
    "where is the federal government adding friction?"

It mirrors HaikuClassifier's conventions (Haiku model, 60s timeout, retry wrapper, JSON-with-
fallback parsing) so behavior is consistent across the codebase.
"""
import json
import re
from dataclasses import dataclass

import anthropic
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

HAIKU_MODEL = "claude-haiku-4-5-20251001"

_VALID_RISK = ("none", "low", "medium", "high")

SYSTEM_PROMPT = """\
You are an expert in US environmental policy, Extended Producer Responsibility (EPR), and the \
federal preemption of state environmental laws. You analyze Federal Register documents and judge \
(a) whether they are relevant to EPR / product stewardship / packaging / recycling / \
right-to-repair / recycled-content mandates / deposit-return / a federal preemption of such laws, \
and (b) how much friction the action creates for STATE EPR programs.\
"""

USER_TEMPLATE = """\
Analyze this US Federal Register document and respond with ONLY valid JSON — no prose, no markdown.

Agency: {agency}
Document type: {action_type}
Title: {title}
Abstract: {abstract}

Return this exact JSON structure:
{{
  "is_relevant": <true or false>,
  "confidence": <float 0.0-1.0>,
  "preemption_risk": <one of: "none","low","medium","high">,
  "friction_type": <one of: "preemption","federal_mandate","compliance_burden","comment_opportunity","funding","study","none">,
  "material_categories": <list from: ["plastic_packaging","paper_packaging","glass","metals","electronics","batteries","paint","carpet","mattresses","tires","pharmaceuticals","solar_panels","textiles","organics","other"]>,
  "summary": "<1-2 sentence plain-English summary for a compliance professional: what the action is and why it matters>"
}}

Relevance: mark is_relevant=false for antidumping/countervailing-duty notices, antitrust
judgments, trade determinations, tariff actions, and anything not touching the policy areas above —
these dominate the raw feed and are noise.

preemption_risk = how much this federal action adds friction to STATE EPR programs:
  - "high": preempts/overrides state EPR or packaging laws, or imposes a binding federal mandate
    that conflicts with or supersedes state programs.
  - "medium": a proposed rule / ANPRM / petition that could lead to preemption or impose
    significant new federal compliance obligations on producers.
  - "low": relevant to the space but little direct friction — guidance, a study, a comment
    request, or funding.
  - "none": not relevant (is_relevant=false) or no plausible effect on state EPR programs.
If is_relevant is false, preemption_risk MUST be "none".
"""


@dataclass
class FederalResult:
    is_relevant: bool
    confidence: float
    preemption_risk: str  # none | low | medium | high
    friction_type: str
    material_categories: list[str]
    summary: str
    raw_response: str = ""


class FederalClassifier:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        # 60s per-request timeout so a hung call fails fast and the retry wrapper handles it,
        # matching HaikuClassifier.
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=60.0, max_retries=0
        )

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    async def classify(
        self,
        title: str,
        agency: str = "",
        action_type: str = "",
        abstract: str = "",
    ) -> FederalResult:
        prompt = USER_TEMPLATE.format(
            agency=agency or "Unknown",
            action_type=action_type or "Unknown",
            title=title or "",
            abstract=(abstract or "")[:2000],
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
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                log.warning("federal_json_parse_failed", raw=raw[:200])
                return FederalResult(
                    is_relevant=False,
                    confidence=0.0,
                    preemption_risk="none",
                    friction_type="none",
                    material_categories=[],
                    summary="parse_error",
                    raw_response=raw,
                )

        risk = str(data.get("preemption_risk", "none")).lower()
        if risk not in _VALID_RISK:
            risk = "none"
        is_relevant = bool(data.get("is_relevant", False))
        # Enforce the invariant the prompt asks for: irrelevant => no friction.
        if not is_relevant:
            risk = "none"
        return FederalResult(
            is_relevant=is_relevant,
            confidence=float(data.get("confidence", 0.0)),
            preemption_risk=risk,
            friction_type=str(data.get("friction_type", "none")),
            material_categories=data.get("material_categories", []) or [],
            summary=data.get("summary", ""),
            raw_response=raw,
        )
