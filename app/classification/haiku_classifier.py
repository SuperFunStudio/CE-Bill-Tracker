import json
from dataclasses import dataclass

import anthropic
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

HAIKU_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """\
You are an expert in US environmental policy and Extended Producer Responsibility (EPR) legislation. \
Analyze legislative bills and classify their relevance to EPR, product stewardship, circular economy policy, \
right-to-repair, recycled content mandates, deposit return schemes, or federal preemption of such laws.\
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
  "material_categories": <list from: ["plastic_packaging","paper_packaging","glass","metals","electronics","batteries","paint","carpet","mattresses","tires","pharmaceuticals","solar_panels","textiles","organics","other"]>,
  "instrument_type": <one of: "epr","right_to_repair","recycled_content","deposit_return","labeling","chemical_restriction","preemption","budget","other">,
  "urgency": <one of: "high","medium","low">,
  "reasoning": "<1 sentence max>"
}}

Urgency guide: high = enrolled/passed/enacted or imminent deadline; medium = passed committee or floor vote scheduled; low = introduced/early committee.
"""


@dataclass
class HaikuResult:
    is_epr_relevant: bool
    confidence: float
    material_categories: list[str]
    instrument_type: str
    urgency: str
    reasoning: str
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
        return HaikuResult(
            is_epr_relevant=data.get("is_epr_relevant", False),
            confidence=float(data.get("confidence", 0.0)),
            material_categories=data.get("material_categories", []),
            instrument_type=data.get("instrument_type", "other"),
            urgency=data.get("urgency", "low"),
            reasoning=data.get("reasoning", ""),
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
