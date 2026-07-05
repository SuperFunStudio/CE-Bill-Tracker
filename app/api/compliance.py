"""Compliance-action API — the "now what do I do" layer surfaced per state.

GET /compliance/pathways?state=XX returns one pathway per enacted EPR law in the state,
each carrying its next action (join_pro / file_individual_plan / register_with_state / …),
the administering entity (PRO or agency) inlined, the soonest deadline, and a fee flag.
Empty list => the state has no enacted EPR law; the frontend renders the "no law" message.
See app/models.py CompliancePathway/ComplianceEntity and scripts/build_compliance_pathways.py.

GET /compliance/fee-schedule returns the CA SB 54 (2027 draft) producer fee schedule —
pure in-code reference data (app/scoring/ca_sb54_fees.py, the same grounded anchor the
company-obligations scoring uses), no DB. Public/free, like /pathways.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bill, ComplianceEntity, CompliancePathway
from app.schemas import (
    ComplianceEntityRef,
    CompliancePathwaySummary,
    FeeScheduleCategory,
    FeeSchedulePlasticAdder,
    FeeScheduleRate,
    FeeScheduleResponse,
)
from app.scoring.ca_sb54_fees import (
    _PLASTIC_PPMF_ADDER,
    _PLASTIC_REUSE_ADDER,
    CA_SB54_2027_SCHEDULE,
    HIGH_SCENARIO_MULTIPLIER,
    LB_PER_TONNE,
    SCHEDULE_CITATION,
    SCHEDULE_SOURCE_URL,
    _cents_lb_to_per_tonne,
)
from app.scoring.materials import _CANONICAL_ALIASES

router = APIRouter(prefix="/compliance", tags=["compliance"])

# Final 2027 rates land October 2026 (see ca_sb54_fees.py module docstring); until then
# these are the published draft ranges.
RATES_FINAL_EXPECTED = "October 2026"


def _fee_rate(tier: str, name: str | None, base_cents: float, adder_cents: float,
              with_high: bool = False) -> FeeScheduleRate:
    total = base_cents + adder_cents
    per_tonne = _cents_lb_to_per_tonne(total)
    return FeeScheduleRate(
        tier=tier,
        format_name=name,
        base_cents_per_lb=base_cents,
        plastic_adder_cents_per_lb=adder_cents,
        total_cents_per_lb=total,
        usd_per_tonne=per_tonne,
        usd_per_tonne_high=round(per_tonne * HIGH_SCENARIO_MULTIPLIER) if with_high else None,
    )


@router.get("/fee-schedule", response_model=FeeScheduleResponse)
async def fee_schedule():
    """CA SB 54 (2027 draft) per-material-format producer fee schedule. Public reference data."""
    categories: list[FeeScheduleCategory] = []
    for category, spec in CA_SB54_2027_SCHEDULE.items():
        adder = spec["plastic_adder_cents_lb"]
        categories.append(
            FeeScheduleCategory(
                material_category=category,
                aliases=sorted(k for k, v in _CANONICAL_ALIASES.items() if v == category),
                includes_plastic_adder=adder > 0,
                note=spec.get("note"),
                rates=[
                    _fee_rate("best", spec["best_format"]["name"],
                              spec["best_format"]["base_cents_lb"], adder),
                    _fee_rate("representative", None,
                              spec["representative_base_cents_lb"], adder, with_high=True),
                    _fee_rate("worst", spec["worst_format"]["name"],
                              spec["worst_format"]["base_cents_lb"], adder),
                ],
            )
        )
    return FeeScheduleResponse(
        program="CA SB-54",
        basis=SCHEDULE_CITATION,
        source_url=SCHEDULE_SOURCE_URL,
        rates_final_expected=RATES_FINAL_EXPECTED,
        lb_per_tonne=LB_PER_TONNE,
        high_scenario_multiplier=HIGH_SCENARIO_MULTIPLIER,
        plastic_adder=FeeSchedulePlasticAdder(
            reuse_cents_per_lb=_PLASTIC_REUSE_ADDER,
            ppmf_cents_per_lb=_PLASTIC_PPMF_ADDER,
            total_cents_per_lb=_PLASTIC_REUSE_ADDER + _PLASTIC_PPMF_ADDER,
        ),
        categories=categories,
    )


@router.get("/pathways", response_model=list[CompliancePathwaySummary])
async def list_pathways(
    state: str | None = Query(default=None, description="Sub-jurisdiction code (e.g. CA, EU)"),
    region: str | None = Query(default=None, description="Jurisdiction family: US (default), EU, or all"),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(CompliancePathway, Bill, ComplianceEntity)
        .join(Bill, Bill.id == CompliancePathway.bill_id)
        .outerjoin(ComplianceEntity, ComplianceEntity.id == CompliancePathway.entity_id)
        .order_by(
            CompliancePathway.next_deadline_date.is_(None),
            CompliancePathway.next_deadline_date,
            Bill.bill_number,
        )
    )
    # Default to US so the existing state pages are unaffected; region="all" spans every region.
    if region is None:
        q = q.where(Bill.region == "US")
    elif region.lower() != "all":
        q = q.where(Bill.region == region.upper())
    if state:
        q = q.where(Bill.state == state.upper())
    rows = (await db.execute(q)).all()
    out: list[CompliancePathwaySummary] = []
    for p, bill, entity in rows:
        out.append(
            CompliancePathwaySummary(
                bill_id=p.bill_id,
                bill_number=bill.bill_number,
                bill_title=bill.title,
                material_categories=bill.material_categories,
                management_model=p.management_model,
                action_type=p.action_type,
                action_summary=p.action_summary,
                registration_url=p.registration_url,
                next_deadline_date=p.next_deadline_date,
                has_fee=p.has_fee,
                entity=ComplianceEntityRef.model_validate(entity) if entity else None,
            )
        )
    return out
