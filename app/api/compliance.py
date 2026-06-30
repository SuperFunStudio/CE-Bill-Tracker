"""Compliance-action API — the "now what do I do" layer surfaced per state.

GET /compliance/pathways?state=XX returns one pathway per enacted EPR law in the state,
each carrying its next action (join_pro / file_individual_plan / register_with_state / …),
the administering entity (PRO or agency) inlined, the soonest deadline, and a fee flag.
Empty list => the state has no enacted EPR law; the frontend renders the "no law" message.
See app/models.py CompliancePathway/ComplianceEntity and scripts/build_compliance_pathways.py.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bill, ComplianceEntity, CompliancePathway
from app.schemas import ComplianceEntityRef, CompliancePathwaySummary

router = APIRouter(prefix="/compliance", tags=["compliance"])


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
