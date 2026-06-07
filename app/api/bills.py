from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bill, ComplianceDeadline, LitigationCase, LitigationEvent
from app.schemas import BillDetail, BillSummary, DeadlineSummary, LitigationCaseSummary, StateMapSummary

router = APIRouter(prefix="/bills", tags=["bills"])


def _lit_subquery():
    return (
        select(
            LitigationCase.related_law_id,
            func.count(LitigationCase.id).label("case_count"),
            func.max(LitigationCase.preemption_risk).label("max_risk"),
        )
        .where(LitigationCase.case_status == "active")
        .group_by(LitigationCase.related_law_id)
        .subquery()
    )


@router.get("", response_model=list[BillSummary])
async def list_bills(
    state: str | None = None,
    status: str | None = None,
    material_category: str | None = None,
    epr_relevant: bool | None = None,
    min_confidence: float = 0.0,
    urgency: str | None = None,
    instrument_type: str | None = None,
    limit: int = Query(default=100, le=5000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    lit_sub = _lit_subquery()
    q = (
        select(Bill, func.coalesce(lit_sub.c.case_count, 0).label("case_count"), lit_sub.c.max_risk)
        .outerjoin(lit_sub, Bill.id == lit_sub.c.related_law_id)
    )
    if state:
        q = q.where(Bill.state == state.upper())
    if status:
        q = q.where(Bill.status == status)
    if epr_relevant is not None:
        q = q.where(Bill.epr_relevant == epr_relevant)
    if min_confidence > 0:
        q = q.where(Bill.confidence_score >= min_confidence)
    if material_category:
        q = q.where(Bill.material_categories.contains([material_category]))
    if urgency:
        q = q.where(Bill.urgency == urgency)
    if instrument_type:
        q = q.where(Bill.instrument_type == instrument_type)
    q = q.order_by(Bill.last_action_date.desc().nullslast()).limit(limit).offset(offset)
    rows = (await db.execute(q)).all()
    results = []
    for row in rows:
        s = BillSummary.model_validate(row.Bill)
        s.litigation_case_count = row.case_count
        s.max_preemption_risk = row.max_risk
        results.append(s)
    return results


@router.get("/map-summary", response_model=list[StateMapSummary])
async def get_map_summary(db: AsyncSession = Depends(get_db)):
    q = (
        select(
            Bill.state,
            func.count().filter(Bill.status == "enacted").label("enacted_count"),
            func.count()
            .filter(Bill.status.in_(["introduced", "in_committee", "passed_chamber"]))
            .label("pending_count"),
            func.count().filter(Bill.epr_relevant).label("total_relevant"),
        )
        .where(Bill.epr_relevant == True)
        .group_by(Bill.state)
    )
    rows = (await db.execute(q)).all()
    return [
        StateMapSummary(
            state=row.state,
            enacted_count=row.enacted_count,
            pending_count=row.pending_count,
            total_relevant=row.total_relevant,
            material_categories=[],
        )
        for row in rows
    ]


@router.get("/{bill_id}", response_model=BillDetail)
async def get_bill(bill_id: int, db: AsyncSession = Depends(get_db)):
    lit_sub = _lit_subquery()
    q = (
        select(Bill, func.coalesce(lit_sub.c.case_count, 0).label("case_count"), lit_sub.c.max_risk)
        .outerjoin(lit_sub, Bill.id == lit_sub.c.related_law_id)
        .where(Bill.id == bill_id)
    )
    row = (await db.execute(q)).one()
    d = BillDetail.model_validate(row.Bill)
    d.litigation_case_count = row.case_count
    d.max_preemption_risk = row.max_risk
    return d


@router.get("/{bill_id}/litigation-cases", response_model=list[LitigationCaseSummary])
async def get_bill_litigation_cases(bill_id: int, db: AsyncSession = Depends(get_db)):
    event_count_sub = (
        select(LitigationEvent.case_id, func.count(LitigationEvent.id).label("event_count"))
        .group_by(LitigationEvent.case_id)
        .subquery()
    )
    q = (
        select(LitigationCase, func.coalesce(event_count_sub.c.event_count, 0).label("event_count"))
        .outerjoin(event_count_sub, LitigationCase.id == event_count_sub.c.case_id)
        .where(LitigationCase.related_law_id == bill_id)
        .order_by(LitigationCase.preemption_risk.desc().nullslast())
    )
    rows = (await db.execute(q)).all()
    results = []
    for row in rows:
        s = LitigationCaseSummary.model_validate(row.LitigationCase)
        s.event_count = row.event_count
        results.append(s)
    return results


@router.get("/deadlines/upcoming", response_model=list[DeadlineSummary])
async def list_upcoming_deadlines(
    days_ahead: int = 90,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() + timedelta(days=days_ahead)
    q = (
        select(ComplianceDeadline, Bill.bill_number, Bill.title)
        .outerjoin(Bill, ComplianceDeadline.bill_id == Bill.id)
        .where(ComplianceDeadline.deadline_date <= cutoff)
        .where(ComplianceDeadline.deadline_date >= date.today())
        .order_by(ComplianceDeadline.deadline_date)
    )
    if state:
        q = q.where(ComplianceDeadline.state == state.upper())
    rows = (await db.execute(q)).all()
    return [
        DeadlineSummary(
            id=row.ComplianceDeadline.id,
            state=row.ComplianceDeadline.state,
            deadline_type=row.ComplianceDeadline.deadline_type,
            deadline_date=row.ComplianceDeadline.deadline_date,
            description=row.ComplianceDeadline.description,
            who_affected=row.ComplianceDeadline.who_affected,
            bill_id=row.ComplianceDeadline.bill_id,
            bill_number=row.bill_number,
            bill_title=row.title,
        )
        for row in rows
    ]
