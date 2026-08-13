from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CAP_FEDERAL, get_optional_capability, require_capability
from app.database import get_db
from app.models import FederalAction, LitigationCase, LitigationEvent
from app.schemas import (
    FederalActionStats,
    FederalActionSummary,
    LitigationCaseDetail,
    LitigationCaseSummary,
)

# Federal Actions + the litigation tracker are a Pro feature (CAP_FEDERAL), and until now that was
# enforced ONLY by the frontend lock on /federal. The old note here argued the routes had to stay open
# because the CDN snapshot builder is unauthenticated and would break — but that reasoning had the
# consequence backwards: it meant the snapshot was baking the full paid dataset to
# /data/federal-actions.json, a public static file. The gate wasn't merely bypassable, it was
# pre-bypassed for everyone.
#
# What the deadline calendar already does is the pattern (see C-1 and /bills/deadlines/summary): the
# ROWS are gated, and a separate public AGGREGATE serves the free surfaces. So:
#
#   GET /federal-actions          full list for CAP_FEDERAL; a short teaser for everyone else
#   GET /federal-actions/summary  public counts (total, high-preemption) — what the homepage banner
#                                 and the Standings board actually needed all along
#   GET /litigation-cases         CAP_FEDERAL, hard 403 — it has no free consumer. Per-BILL litigation
#                                 (/bills/{id}/litigation-cases) stays free, matching the standing rule
#                                 that a single record is free and the corpus-wide view is the product.
#
# The snapshot now bakes the summary instead of the list, so the CDN carries only free data.
FEDERAL_TEASER_LIMIT = 5

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
    has_federal: bool = Depends(get_optional_capability(CAP_FEDERAL)),
    db: AsyncSession = Depends(get_db),
):
    """List federal actions from the Federal Register and other sources.

    CAP_FEDERAL seats get the full list; everyone else gets the FEDERAL_TEASER_LIMIT most recent rows.
    Counts for the free surfaces come from /federal-actions/summary, which stays public.
    """
    if not has_federal:
        limit = min(limit, FEDERAL_TEASER_LIMIT)
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


@router.get("/summary", response_model=FederalActionStats)
async def federal_actions_summary(
    ce_relevant: bool | None = Query(default=True),
    days_back: int = Query(default=1825),
    db: AsyncSession = Depends(get_db),
):
    """Ungated counts over the same window the list uses: how many federal actions there are, and how
    many carry High preemption risk.

    This exists so the free surfaces never need the rows. The homepage's federal-watch banner only
    ever used `federal.filter(preemption_risk === 'High').length`, and the Standings board only used
    `federal.length` — both were pulling up to 500 gated records to compute one integer. Same
    correction as /bills/deadlines/summary: hand over the number, not the dataset.
    """
    cutoff = date.today() - timedelta(days=days_back)
    q = select(
        func.count(FederalAction.id),
        func.count(FederalAction.id).filter(FederalAction.preemption_risk == "High"),
    ).where(FederalAction.published_date >= cutoff)
    if ce_relevant is not None:
        q = q.where(FederalAction.ce_relevant == ce_relevant)
    total, high = (await db.execute(q)).one()
    return FederalActionStats(total=total or 0, high_preemption=high or 0)


# CAP_FEDERAL at the router level: unlike the actions list, the bulk litigation feed has no free
# consumer to keep working — the public bill panel reads per-bill litigation, not this. So it gets a
# straight 403 rather than a teaser, which is both simpler and a clearer answer to a caller.
litigation_router = APIRouter(
    prefix="/litigation-cases",
    tags=["litigation"],
    dependencies=[Depends(require_capability(CAP_FEDERAL))],
)


@litigation_router.get("", response_model=list[LitigationCaseSummary])
async def list_litigation_cases(
    status: str | None = None,
    state: str | None = None,
    min_risk: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, le=200),
    include_out_of_scope: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List litigation cases tracked from CourtListener.

    Only cases the relevance gate has cleared (`ce_relevant IS TRUE`) are public. Rows it rejected —
    and rows that predate it, which are the same 33-of-34 unrelated dockets that reached subscribers'
    inboxes — are kept for audit but hidden. `include_out_of_scope` is for reviewing that backlog.
    """
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
    if not include_out_of_scope:
        q = q.where(LitigationCase.ce_relevant.is_(True))
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
    if case.ce_relevant is not True:
        # 404, not 403: an out-of-scope docket isn't a restricted resource, it's one that should
        # never have had a page. Alert emails linked here by id, so the URLs are already in inboxes.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Litigation case not found")

    detail = LitigationCaseDetail.model_validate(case)
    detail.events = sorted(case.events, key=lambda e: e.date_filed or date.min)
    detail.event_count = len(case.events)
    return detail
