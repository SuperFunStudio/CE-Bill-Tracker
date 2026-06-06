"""
Exposure Brief Generator — Interpretation Engine (v2.0)

Generates a structured Exposure Brief for a (company, bill) pair using Claude Sonnet.
Briefs explain why a company is exposed, estimate costs, provide peer context,
and recommend circular economy interventions.
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import anthropic
import structlog

from app.config import settings

log = structlog.get_logger()

SONNET_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are a circular economy compliance expert specializing in Extended Producer Responsibility (EPR) \
legislation. You advise sustainability managers at consumer goods and packaging companies on \
regulatory exposure and circular economy redesign strategies.

Your analysis is grounded in the Ellen MacArthur Foundation framework. When recommending redesign \
opportunities, you prioritize material substitution, post-consumer recycled (PCR) content targets, \
and take-back programs as primary levers.

You will be given data about a specific company and an EPR bill. Respond ONLY with a valid JSON \
object matching this exact schema — no markdown fences, no preamble:

{
  "exposure_summary": "<2-3 sentences explaining why this company is exposed to this bill, referencing specific facilities, materials, and volume data>",
  "cost_breakdown": {
    "registration_fee": <number or null>,
    "per_ton_fee": <number or null>,
    "estimated_tonnage": <number or null>,
    "estimated_annual_obligation": <number or null>,
    "penalty_risk_estimate": <number or null>,
    "total_estimated_annual_cost": <number or null>,
    "confidence": "<low|medium|high>",
    "notes": "<brief explanation of assumptions>"
  },
  "peer_context": "<1 sentence placing this company among registered producers or peers>",
  "redesign_opportunities": [
    "<specific circular economy intervention that reduces this company's exposure>",
    "<second intervention>",
    "<third intervention>"
  ],
  "next_step_cta": "<call to action linking exposure to consulting engagement>"
}
"""


def _build_user_prompt(
    company_name: str,
    hq_state: str | None,
    materials: list[dict],
    state_presences: list[dict],
    bill_title: str | None,
    bill_state: str,
    bill_number: str | None,
    bill_status: str | None,
    compliance_details: dict | None,
    composite_score: float,
    estimated_annual_cost: float | None,
    peer_rank: int | None,
    peer_total: int | None,
) -> str:
    mat_lines = "\n".join(
        f"  - {m.get('material_category', 'unknown')}: "
        f"{m.get('annual_volume_tonnes', 'unknown'):,.0f} tonnes "
        f"(confidence: {int((m.get('volume_confidence') or 0) * 100)}%)"
        if isinstance(m.get("annual_volume_tonnes"), (int, float))
        else f"  - {m.get('material_category', 'unknown')}: volume unknown"
        for m in materials
    )

    presence_lines = "\n".join(
        f"  - {p.get('state', '?')}: {p.get('presence_type', 'unknown')}"
        + (" (primary)" if p.get("is_primary") else "")
        for p in state_presences
    )

    cd = compliance_details or {}
    fee_per_ton = cd.get("fee_per_ton")
    registration_fee = cd.get("registration_fee")
    covered_materials = cd.get("covered_materials") or []
    effective_date = cd.get("effective_date") or "unknown"
    penalty_provisions = cd.get("penalty_provisions") or "not specified"

    cost_str = (
        f"${estimated_annual_cost:,.0f}" if isinstance(estimated_annual_cost, (int, float)) else "unknown"
    )
    peer_str = (
        f"#{peer_rank} of {peer_total} companies" if peer_rank and peer_total else "ranking unavailable"
    )

    return f"""\
COMPANY: {company_name}
HQ State: {hq_state or "unknown"}

MATERIAL STREAMS:
{mat_lines or "  (no material data available)"}

STATE PRESENCES:
{presence_lines or "  (no presence data available)"}

BILL: {bill_state} {bill_number or ""} — {bill_title or "Untitled"}
Status: {bill_status or "unknown"}
Effective date: {effective_date}
Fee per ton: {"${:,.4f}".format(fee_per_ton) if isinstance(fee_per_ton, (int, float)) else "not specified"}
Registration fee: {"${:,.0f}".format(registration_fee) if isinstance(registration_fee, (int, float)) else "not specified"}
Covered materials: {", ".join(covered_materials) if covered_materials else "all packaging"}
Penalty provisions: {penalty_provisions}

SCORING:
Composite exposure score: {composite_score:.1f} / 100
Estimated annual compliance cost: {cost_str}
Peer ranking: {peer_str}

Generate the Exposure Brief JSON now."""


class ExposureBriefGenerator:
    """Generates structured Exposure Briefs using Claude Sonnet."""

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate(
        self,
        company_name: str,
        hq_state: str | None,
        materials: list[dict],
        state_presences: list[dict],
        bill_title: str | None,
        bill_state: str,
        bill_number: str | None,
        bill_status: str | None,
        compliance_details: dict | None,
        composite_score: float,
        estimated_annual_cost: float | None,
        peer_rank: int | None = None,
        peer_total: int | None = None,
    ) -> dict:
        """Generate a structured Exposure Brief. Returns a dict (brief_json)."""
        prompt = _build_user_prompt(
            company_name=company_name,
            hq_state=hq_state,
            materials=materials,
            state_presences=state_presences,
            bill_title=bill_title,
            bill_state=bill_state,
            bill_number=bill_number,
            bill_status=bill_status,
            compliance_details=compliance_details,
            composite_score=composite_score,
            estimated_annual_cost=estimated_annual_cost,
            peer_rank=peer_rank,
            peer_total=peer_total,
        )

        log.info(
            "interpreter_generate_start",
            company=company_name,
            bill=f"{bill_state} {bill_number}",
        )

        try:
            resp = await self._client.messages.create(
                model=SONNET_MODEL,
                max_tokens=1200,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
        except Exception as exc:
            log.error("interpreter_api_error", error=str(exc))
            return {"error": "api_error", "detail": str(exc)}

        # Strip markdown fences if model wraps in ```json ... ```
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()

        try:
            brief = json.loads(cleaned)
        except json.JSONDecodeError:
            log.warning("interpreter_parse_failed", raw_length=len(raw))
            return {"error": "parse_failed", "raw": raw}

        log.info("interpreter_generate_complete", company=company_name)
        return brief

    def ttl_timestamp(self) -> datetime:
        """Return the TTL expiry timestamp for a newly generated brief."""
        return datetime.now(timezone.utc) + timedelta(days=settings.interpretation_brief_ttl_days)
