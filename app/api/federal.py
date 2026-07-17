from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import FederalAction, LitigationCase, LitigationEvent
from app.schemas import FederalActionSummary, LitigationCaseDetail, LitigationCaseSummary

# Federal Actions + the litigation tracker are a Pro feature, gated on the FRONTEND (the /federal page
# shows a Pro lock). The data is served to the client via a static CDN snapshot for resilience, so
# these endpoints stay open — a backend gate would both break the unauthenticated snapshot build and be
# bypassed by the snapshot fallback. See dashboard-next/src/app/federal/page.tsx + useFederal.ts.
router = APIRouter(prefix="/federal-actions", tags=["federal"])


@router.get("", response_model=list[FederalActionSummary])
async def list_federal_actions(
    action_type: str | None = None,
    preemption_risk: str | None = None,
    instrument_type: str | None = None,
    material_category: str | None = None,
    friction_type: str | None = None,
    ce_relevant: bool | None = Query(
        default=True,
        description="Filter by EPR relevance. Defaults to true so the page only shows "
        "classified-relevant actions; pass false to inspect the rejected/noise rows.",
    ),
    days_back: int = Query(
        default=1825,
        description="How many days back to fetch. Defaults to ~5y: the federal feed is sparse "
        "and these actions (strategies, comment dockets, procurement rules) stay relevant for years.",
    ),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List federal actions from the Federal Register and other sources."""
    cutoff = date.today() - timedelta(days=days_back)
    q = (
        select(FederalAction)
        .where(FederalAction.published_date >= cutoff)
        .order_by(FederalAction.published_date.desc())
        .limit(limit)
    )
    if ce_relevant is not None:
        q = q.where(FederalAction.ce_relevant == ce_relevant)
    if action_type:
        q = q.where(FederalAction.action_type == action_type)
    if preemption_risk:
        q = q.where(FederalAction.preemption_risk == preemption_risk)
    if instrument_type:
        q = q.where(FederalAction.instrument_type == instrument_type)
    if friction_type:
        q = q.where(FederalAction.friction_type == friction_type)
    if material_category:
        q = q.where(FederalAction.material_categories.contains([material_category]))
    result = await db.execute(q)
    return result.scalars().all()


litigation_router = APIRouter(prefix="/litigation-cases", tags=["litigation"])


@litigation_router.get("", response_model=list[LitigationCaseSummary])
async def list_litigation_cases(
    status: str | None = None,
    state: str | None = None,
    min_risk: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List litigation cases tracked from CourtListener."""
    # Subquery: count events per case
    event_count_sub = (
        select(
            LitigationEvent.case_id,
            func.count(LitigationEvent.id).label("event_count"),
        )
        .group_by(LitigationEvent.case_id)
        .subquery()
    )

    q = (
        select(LitigationCase, func.coalesce(event_count_sub.c.event_count, 0).label("event_count"))
        .outerjoin(event_count_sub, LitigationCase.id == event_count_sub.c.case_id)
        .order_by(LitigationCase.preemption_risk.desc(), LitigationCase.last_activity_date.desc())
        .limit(limit)
    )
    if status:
        q = q.where(LitigationCase.case_status == status)
    if state:
        q = q.where(LitigationCase.related_state == state)
    if min_risk > 0:
        q = q.where(LitigationCase.preemption_risk >= min_risk)

    result = await db.execute(q)
    rows = result.all()

    summaries = []
    for case, event_count in rows:
        summary = LitigationCaseSummary.model_validate(case)
        summary.event_count = event_count
        summaries.append(summary)
    return summaries


@litigation_router.get("/{case_id}", response_model=LitigationCaseDetail)
async def get_litigation_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a litigation case with all events (timeline)."""
    result = await db.execute(
        select(LitigationCase)
        .options(selectinload(LitigationCase.events))
        .where(LitigationCase.id == case_id)
    )
    case = result.scalar_one_or_none()
    if not case:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Litigation case not found")

    detail = LitigationCaseDetail.model_validate(case)
    detail.events = sorted(case.events, key=lambda e: e.date_filed or date.min)
    detail.event_count = len(case.events)
    return detail
