import json
from dataclasses import dataclass

import anthropic
import structlog

from app.config import settings

log = structlog.get_logger()

SONNET_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are a compliance specialist analyzing US EPR legislation. \
Extract all compliance-relevant details that would matter to a producer, manufacturer, brand owner, or importer. \
Be precise about dates, thresholds, and obligations. If a detail is not specified in the bill, omit that key.\
"""

USER_TEMPLATE = """\
Extract compliance details from this bill. Respond with ONLY valid JSON — no prose, no markdown.

State: {state}
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
    ) -> SonnetResult:
        prompt = USER_TEMPLATE.format(
            state=state,
            bill_number=bill_number or "Unknown",
            title=title or "",
            full_text=full_text[:12000],  # ~3K tokens of text
        )
        resp = await self._client.messages.create(
            model=SONNET_MODEL,
            max_tokens=3000,  # compliance JSON for large bills overflows a smaller budget
            temperature=0,
            system=SYSTEM_PROMPT,
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
