"""Author a shareable Design-for-Circularity guide from persisted bill_design_signal rows.

Turns the raw cited signals (app/synthesis/design_levers.py) into a brief, comprehensive guide
for design/packaging teams at impacted companies. A Sonnet pass per lever collapses the many
near-duplicate per-bill design_actions into a few CANONICAL imperatives — grounded strictly in
the evidence passed in, citing only bills from that evidence (enacted-first). Verbatim quotes are
carried through unchanged so the guide keeps the same chain of custody as the underlying data.

No cost/fee numbers are asserted: eco-modulation rates come from the Circular Action Alliance
schedules and are not yet available (see [[design-principle-synthesis]]).
"""
from __future__ import annotations

import json
import re

import anthropic
import structlog

from app.config import settings
from app.synthesis.design_levers import PRINCIPLE_STATEMENTS
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

SONNET_MODEL = "claude-sonnet-4-6"

# Lever -> guide section. reuse_refill is kept with packaging; repairability is its own part.
PACKAGING_LEVERS = (
    "design_for_recycling",
    "recycled_content",
    "source_reduction",
    "reuse_refill",
    "toxics_elimination",
    "material_restriction",
    "labeling_marking",
    "compostability",
)
PRODUCT_LEVERS = ("repairability_durability",)

# Authority ranking — enacted law is stronger evidence than an introduced or dead bill.
_STATUS_RANK = {
    "enacted": 5, "passed": 4, "passed_chamber": 4, "in_committee": 2,
    "introduced": 1, "vetoed": 0, "failed": 0,
}


def status_rank(status: str | None) -> int:
    return _STATUS_RANK.get((status or "").lower(), 1)


OBLIGATION_LABEL = {
    "required": "Required",
    "rewarded": "Fee-advantaged",
    "penalized": "Fee-penalized",
    "banned": "Prohibited",
    "exempted": "Exemption available",
    "named": "Referenced",
}

SYSTEM_PROMPT = """\
You are a senior packaging/product sustainability strategist writing a concise design guide for \
corporate design teams. You translate enacted and proposed US circular-economy law into clear, \
actionable DESIGN guidance. You are rigorous about provenance: you only state guidance that is \
supported by the evidence provided, and you only cite bills that appear in that evidence. You \
never invent thresholds, obligations, or bills.\
"""

USER_TEMPLATE = """\
Write the guidance for ONE design lever: "{lever}" ({statement}).

Below are real, already-verified signals extracted from US bills (each with its source quote).
Bills marked [enacted] are law; others are proposed. Synthesize these into CANONICAL design
guidance — collapse duplicates, prefer what enacted laws require.

Evidence:
{evidence}

Return ONLY valid JSON:
{{
  "summary": "<2 sentences: what this lever is and why a design team should act on it>",
  "imperatives": [
    {{
      "action": "<imperative design instruction, <=14 words>",
      "detail": "<one sentence of practical specifics>",
      "obligation": "<required|fee-advantaged|prohibited|exemption>",
      "cite_bills": ["<e.g. CA SB-54>"]
    }}
  ],
  "targets": ["<concrete numeric target with its bill, e.g. '35% recycled glass (CA SB-38)'>"]
}}

Rules:
- 3 to 6 imperatives, ordered most-actionable first. Merge near-identical actions across bills.
- cite_bills MUST be bills present in the evidence above; prefer [enacted] ones.
- The evidence may span distinct product sectors (packaging, textiles/apparel, electronics,
  furniture, turf, etc.). Do NOT collapse a sector-specific obligation into a generic packaging
  one and drop its sector — when a bill applies the lever to a non-packaging sector, keep at least
  one imperative that names that sector and cites its bill (e.g. textiles via CA SB-707). Aim to
  represent every distinct sector present in the evidence at least once.
- "targets" only where a real number appears in the evidence; otherwise return [].
- Do not mention fee dollar amounts unless they appear verbatim in the evidence.
"""


class GuideAuthor:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=90.0, max_retries=0
        )

    @retry_with_backoff(max_attempts=3, base_delay=1.5)
    async def author(self, lever: str, evidence: list[dict]) -> dict:
        """evidence: list of {state, bill_number, status, obligation_type, design_action,
        source_excerpt, threshold_value, threshold_unit}. Returns the section JSON."""
        lines = []
        for e in evidence:
            tag = "[enacted]" if (e.get("status") or "").lower() == "enacted" else f"[{e.get('status')}]"
            thr = ""
            if e.get("threshold_value") is not None:
                thr = f" (={e['threshold_value']:g} {e.get('threshold_unit') or ''})".rstrip()
            lines.append(
                f"- {e['state']} {e.get('bill_number') or '?'} {tag} "
                f"[{OBLIGATION_LABEL.get(e['obligation_type'], e['obligation_type'])}]: "
                f"{e.get('design_action') or ''}{thr}\n    quote: \"{e.get('source_excerpt') or ''}\""
            )
        prompt = USER_TEMPLATE.format(
            lever=lever,
            statement=PRINCIPLE_STATEMENTS.get(lever, lever),
            evidence="\n".join(lines)[:14000],
        )
        resp = await self._client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1500,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
        log.warning("guide_author_parse_failed", lever=lever, raw=raw[:200])
        return {"summary": "", "imperatives": [], "targets": []}
