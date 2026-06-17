"""Company impact scoring API endpoints.

Three routers exported from this module:
  - router          → /companies/*
  - bills_exposure_router → /bills/{bill_id}/company-exposure
  - queue_router    → /entity-match-queue
"""
import uuid
from datetime import date, datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import AuthedUser, require_admin
from app.config import settings
from app.database import get_db
from app.models import (
    Bill,
    Company,
    CompanyAlias,
    ComplianceDeadline,
    EntityMatchQueue,
    ExposureBrief,
    ImpactScore,
)
from app.schemas import (
    CompanyDetail,
    CompanyObligation,
    CompanyObligationDeadline,
    CompanyObligationsResponse,
    CompanySummary,
    EntityMatchQueueItem,
    ExposureBriefResponse,
    ExposureRanking,
    FinancialStakes,
    ImpactScoreResponse,
)
from app.scoring.materials import canonical_material_category, canonical_set
from app.scoring.stakes import compute_stakes

ENACTED_STATUSES = ("enacted", "signed")

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# /companies router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/exposure-ranking", response_model=list[ExposureRanking])
async def get_exposure_ranking(
    bill_id: int,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[ExposureRanking]:
    """Top companies ranked by composite impact score for a given bill.

    NOTE: This route MUST be declared before /{company_id} to prevent
    FastAPI from trying to parse 'exposure-ranking' as a UUID.
    """
    result = await db.execute(
        select(ImpactScore)
        .where(ImpactScore.bill_id == bill_id)
        .options(selectinload(ImpactScore.company))
        .order_by(desc(ImpactScore.composite_score))
        .limit(limit)
    )
    scores = result.scalars().all()

    return [
        ExposureRanking(
            company=CompanySummary.model_validate(s.company),
            impact_score=ImpactScoreResponse.model_validate(s),
        )
        for s in scores
        if s.company is not None
    ]


@router.get("/{company_id}/exposure-brief", response_model=ExposureBriefResponse)
async def get_or_generate_exposure_brief(
    company_id: uuid.UUID,
    bill_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AuthedUser = Depends(require_admin),
) -> ExposureBriefResponse:
    """Return a cached Exposure Brief for a (company, bill) pair, generating one if needed.

    Admin-gated: a cache miss triggers a Claude Sonnet generation, so on a public service an
    unauthenticated caller could iterate (company, bill) pairs to run up unbounded LLM cost. The
    Portfolio Exposure tool this backs is itself admin-only (a Bespoke engagement), so require_admin
    matches the product and closes the abuse vector. See docs/SECURITY_ASSESSMENT.md C-3.

    Returns 503 if interpretation is disabled via ENABLE_INTERPRETATION=false.
    Returns 404 if no impact score exists for the pair (can't generate a meaningful brief).
    """
    # 1. Cache hit — return existing non-expired brief
    now = datetime.now(timezone.utc)
    cached_result = await db.execute(
        select(ExposureBrief).where(
            ExposureBrief.company_id == company_id,
            ExposureBrief.bill_id == bill_id,
        )
    )
    cached = cached_result.scalar_one_or_none()
    if cached is not None:
        if cached.ttl_expires_at is None or cached.ttl_expires_at > now:
            return cached  # type: ignore[return-value]
        # Expired — fall through to regenerate

    # 2. Gate on feature flag
    if not settings.enable_interpretation:
        raise HTTPException(
            status_code=503,
            detail="Exposure brief generation is disabled. Set ENABLE_INTERPRETATION=true.",
        )

    # 3. Load required data
    company_result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.materials),
            selectinload(Company.state_presences),
        )
    )
    company = company_result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    bill_result = await db.execute(select(Bill).where(Bill.id == bill_id))
    bill = bill_result.scalar_one_or_none()
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")

    score_result = await db.execute(
        select(ImpactScore).where(
            ImpactScore.company_id == company_id,
            ImpactScore.bill_id == bill_id,
        )
    )
    impact_score = score_result.scalar_one_or_none()
    if impact_score is None:
        raise HTTPException(
            status_code=404,
            detail="No impact score found for this company/bill pair. Run the scoring pipeline first.",
        )

    # 4. Get peer ranking context
    peer_rank: int | None = None
    peer_total: int | None = None
    try:
        count_result = await db.execute(
            select(ImpactScore).where(ImpactScore.bill_id == bill_id)
        )
        all_scores = count_result.scalars().all()
        peer_total = len(all_scores)
        sorted_scores = sorted(all_scores, key=lambda s: s.composite_score, reverse=True)
        for i, s in enumerate(sorted_scores, 1):
            if s.company_id == company_id:
                peer_rank = i
                break
    except Exception:
        pass

    # 5. Generate brief
    from app.scoring.interpreter import ExposureBriefGenerator

    generator = ExposureBriefGenerator()
    brief_json = await generator.generate(
        company_name=company.name,
        hq_state=company.hq_state,
        materials=[
            {
                "material_category": m.material_category,
                "annual_volume_tonnes": m.annual_volume_tonnes,
                "volume_confidence": m.volume_confidence,
            }
            for m in company.materials
        ],
        state_presences=[
            {
                "state": p.state,
                "presence_type": p.presence_type,
                "is_primary": p.is_primary,
            }
            for p in company.state_presences
        ],
        bill_title=bill.title,
        bill_state=bill.state,
        bill_number=bill.bill_number,
        bill_status=bill.status,
        compliance_details=bill.compliance_details,
        composite_score=impact_score.composite_score,
        estimated_annual_cost=impact_score.estimated_annual_cost,
        peer_rank=peer_rank,
        peer_total=peer_total,
    )

    # 6. Upsert: delete stale entry (expired or missing), insert fresh one
    await db.execute(
        delete(ExposureBrief).where(
            ExposureBrief.company_id == company_id,
            ExposureBrief.bill_id == bill_id,
        )
    )
    ttl = generator.ttl_timestamp()
    brief = ExposureBrief(
        company_id=company_id,
        bill_id=bill_id,
        brief_json=brief_json,
        ttl_expires_at=ttl,
    )
    db.add(brief)
    await db.commit()
    await db.refresh(brief)

    log.info(
        "exposure_brief_generated",
        company_id=str(company_id),
        bill_id=bill_id,
        ttl_expires_at=ttl.isoformat(),
    )
    return brief  # type: ignore[return-value]


@router.get("", response_model=list[CompanySummary])
async def list_companies(
    search: str | None = None,
    hq_state: str | None = None,
    naics_code: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[CompanySummary]:
    """List companies with optional filters.

    `search` matches the company name OR any of its aliases (case-insensitive
    substring), so a user typing "Pepsi" or "Frito-Lay" both resolve to PepsiCo.
    """
    stmt = select(Company)

    if search:
        term = f"%{search.strip()}%"
        alias_match = (
            select(CompanyAlias.company_id)
            .where(CompanyAlias.alias_name.ilike(term))
            .scalar_subquery()
        )
        stmt = stmt.where(
            or_(Company.name.ilike(term), Company.id.in_(alias_match))
        )
    if hq_state:
        stmt = stmt.where(Company.hq_state == hq_state.upper())
    if naics_code:
        stmt = stmt.where(Company.naics_codes.contains([naics_code]))

    stmt = stmt.order_by(Company.name).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()  # type: ignore[return-value]


@router.get("/{company_id}", response_model=CompanyDetail)
async def get_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CompanyDetail:
    """Full company detail including materials and state presences."""
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.materials),
            selectinload(Company.state_presences),
        )
    )
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company  # type: ignore[return-value]


@router.get("/{company_id}/impact-scores", response_model=list[ImpactScoreResponse])
async def get_company_impact_scores(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ImpactScoreResponse]:
    """All impact scores for a company, ordered by composite score descending."""
    result = await db.execute(
        select(ImpactScore)
        .where(ImpactScore.company_id == company_id)
        .order_by(desc(ImpactScore.composite_score))
    )
    return result.scalars().all()  # type: ignore[return-value]


@router.get("/{company_id}/obligations", response_model=CompanyObligationsResponse)
async def get_company_obligations(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CompanyObligationsResponse:
    """'Are you affected, and what's your next deadline' for one company.

    A company is *affected* by an enacted law when it has a material in the
    bill's `material_categories` AND an operational presence in the bill's
    state. This is the high-confidence half of exposure — it relies only on the
    company's own materials/footprint and the bill's enacted status, NOT on the
    proxy-derived volumes or synthetic cost estimates. Each affected law is
    returned with its next upcoming compliance deadline (from the PDF-extracted
    `compliance_deadlines`), so the lead is an obligation, not a dollar guess.
    """
    company_result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.materials),
            selectinload(Company.state_presences),
        )
    )
    company = company_result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    # Normalize company materials to the canonical vocabulary so glass/metal exposure
    # matches bills that carry "glass"/"metals" (see app/scoring/materials.py).
    material_categories = {
        canonical_material_category(m.material_category) for m in company.materials
    }
    # canonical category -> tonnage (summed across raw materials that map together;
    # None only when every contributing material's volume is unknown).
    tonnes_by_category: dict[str, float | None] = {}
    for m in company.materials:
        c = canonical_material_category(m.material_category)
        if m.annual_volume_tonnes is not None:
            tonnes_by_category[c] = (tonnes_by_category.get(c) or 0.0) + m.annual_volume_tonnes
        else:
            tonnes_by_category.setdefault(c, None)
    # state -> set of presence types (manufacturing, headquarters, …)
    presence_by_state: dict[str, set[str]] = {}
    for p in company.state_presences:
        presence_by_state.setdefault(p.state, set()).add(p.presence_type)

    # No footprint or no materials → nothing to be affected by.
    if not material_categories or not presence_by_state:
        return CompanyObligationsResponse(
            company_id=company.id,
            company_name=company.name,
            affected_bill_count=0,
            affected_states=[],
            upcoming_deadline_count=0,
            next_deadline_date=None,
            obligations=[],
        )

    # Enacted EPR-relevant bills in any state the company operates in.
    # Material filtering happens in Python — the candidate set is tiny (only
    # enacted laws in the company's states), so a JSONB overlap operator buys
    # nothing and is easy to get subtly wrong.
    bills_result = await db.execute(
        select(Bill).where(
            Bill.status.in_(ENACTED_STATUSES),
            Bill.epr_relevant.is_(True),
            Bill.state.in_(list(presence_by_state.keys())),
        )
    )
    candidate_bills = bills_result.scalars().all()

    affected: list[tuple[Bill, list[str]]] = []
    for bill in candidate_bills:
        bill_cats = canonical_set(bill.material_categories)
        matched = material_categories & bill_cats
        if matched:
            affected.append((bill, sorted(matched)))

    if not affected:
        return CompanyObligationsResponse(
            company_id=company.id,
            company_name=company.name,
            affected_bill_count=0,
            affected_states=sorted(presence_by_state.keys()),
            upcoming_deadline_count=0,
            next_deadline_date=None,
            obligations=[],
        )

    # Pull every deadline for the affected bills in one query, grouped by bill.
    bill_ids = [b.id for b, _ in affected]
    deadlines_result = await db.execute(
        select(ComplianceDeadline)
        .where(ComplianceDeadline.bill_id.in_(bill_ids))
        .order_by(ComplianceDeadline.deadline_date)
    )
    deadlines_by_bill: dict[int, list[ComplianceDeadline]] = {}
    for d in deadlines_result.scalars().all():
        if d.bill_id is not None:
            deadlines_by_bill.setdefault(d.bill_id, []).append(d)

    today = date.today()
    obligations: list[CompanyObligation] = []
    total_upcoming = 0
    for bill, matched in affected:
        bill_deadlines = deadlines_by_bill.get(bill.id, [])
        upcoming = [d for d in bill_deadlines if d.deadline_date >= today]
        total_upcoming += len(upcoming)
        next_dl = (
            CompanyObligationDeadline(
                deadline_date=upcoming[0].deadline_date,
                deadline_type=upcoming[0].deadline_type,
                description=upcoming[0].description,
                who_affected=upcoming[0].who_affected,
                source_url=upcoming[0].source_url,
            )
            if upcoming
            else None
        )
        # Financial stakes: penalty (grounded in statute) + annual fee range + PRO fee +
        # eco-modulation lever. Computed from this bill's matched materials and tonnage.
        stakes_dict = compute_stakes(
            bill_state=bill.state,
            compliance_details=bill.compliance_details,
            matched_materials=[
                {"category": c, "tonnes": tonnes_by_category.get(c)} for c in matched
            ],
            bill_number=bill.bill_number,
        )
        stakes = FinancialStakes.model_validate(stakes_dict) if stakes_dict["has_any"] else None
        obligations.append(
            CompanyObligation(
                bill_id=bill.id,
                state=bill.state,
                bill_number=bill.bill_number,
                bill_title=bill.title,
                status=bill.status,
                source_url=bill.source_url,
                matched_materials=matched,
                presence_types=sorted(presence_by_state.get(bill.state, set())),
                next_deadline=next_dl,
                upcoming_deadline_count=len(upcoming),
                total_deadline_count=len(bill_deadlines),
                stakes=stakes,
            )
        )

    # Sort: laws with an upcoming deadline first (soonest first), then the rest
    # (enacted but no future deadline) by state / bill number.
    obligations.sort(
        key=lambda o: (
            o.next_deadline is None,
            o.next_deadline.deadline_date if o.next_deadline else date.max,
            o.state,
            o.bill_number or "",
        )
    )

    next_overall = next(
        (o.next_deadline.deadline_date for o in obligations if o.next_deadline), None
    )

    # Portfolio financial rollup.
    # Penalty is a MAX (your single largest daily exposure — you wouldn't be in default on
    # every law at once). Fees are aggregated BY STATE, not summed per law: a producer pays
    # packaging program fees once per state (to that state's PRO), so summing every matching
    # law would double-count the same physical packaging. We take the largest fee per state
    # (its dominant program) and sum across states.
    penalties = [o.stakes.penalty for o in obligations if o.stakes and o.stakes.penalty]
    day_penalties = [p.amount_usd for p in penalties if p.unit == "day"]

    fee_low_by_state: dict[str, float] = {}
    fee_high_by_state: dict[str, float] = {}
    swing_by_state: dict[str, float] = {}
    any_grounded = False
    for o in obligations:
        f = o.stakes.fee if o.stakes else None
        if f is None:
            continue
        any_grounded = any_grounded or f.annual_fee_grounded
        if f.annual_fee_low_usd > fee_low_by_state.get(o.state, -1):
            fee_low_by_state[o.state] = f.annual_fee_low_usd
            fee_high_by_state[o.state] = f.annual_fee_high_usd
            swing_by_state[o.state] = f.eco_modulation_swing_usd or 0.0
    fee_low = round(sum(fee_low_by_state.values())) if fee_low_by_state else None
    fee_high = round(sum(fee_high_by_state.values())) if fee_high_by_state else None
    eco_total = sum(swing_by_state.values())
    eco_swing = round(eco_total) if eco_total else None

    return CompanyObligationsResponse(
        company_id=company.id,
        company_name=company.name,
        affected_bill_count=len(obligations),
        affected_states=sorted({o.state for o in obligations}),
        upcoming_deadline_count=total_upcoming,
        next_deadline_date=next_overall,
        obligations=obligations,
        max_penalty_per_day_usd=max(day_penalties) if day_penalties else None,
        portfolio_annual_fee_low_usd=fee_low,
        portfolio_annual_fee_high_usd=fee_high,
        portfolio_eco_modulation_swing_usd=eco_swing,
        any_fee_grounded=any_grounded,
    )


# ---------------------------------------------------------------------------
# /bills/{bill_id}/company-exposure router
# ---------------------------------------------------------------------------

bills_exposure_router = APIRouter(prefix="/bills", tags=["companies"])


@bills_exposure_router.get("/{bill_id}/company-exposure", response_model=list[ExposureRanking])
async def get_bill_company_exposure(
    bill_id: int,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[ExposureRanking]:
    """Companies most exposed to a specific bill, ranked by composite score."""
    result = await db.execute(
        select(ImpactScore)
        .where(ImpactScore.bill_id == bill_id)
        .options(selectinload(ImpactScore.company))
        .order_by(desc(ImpactScore.composite_score))
        .limit(limit)
    )
    scores = result.scalars().all()

    return [
        ExposureRanking(
            company=CompanySummary.model_validate(s.company),
            impact_score=ImpactScoreResponse.model_validate(s),
        )
        for s in scores
        if s.company is not None
    ]


# ---------------------------------------------------------------------------
# /entity-match-queue router
# ---------------------------------------------------------------------------

# Admin-only: these read/mutate the entity-resolution review queue. The PATCH lets a caller resolve
# items and bind them to arbitrary companies, corrupting resolution and hiding items from human
# review, so the whole router requires an admin token. See docs/SECURITY_ASSESSMENT.md H-3.
queue_router = APIRouter(
    prefix="/entity-match-queue", tags=["companies"], dependencies=[Depends(require_admin)]
)


@queue_router.get("", response_model=list[EntityMatchQueueItem])
async def list_match_queue(
    resolved: bool = False,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[EntityMatchQueueItem]:
    """List entity match queue entries pending manual review."""
    result = await db.execute(
        select(EntityMatchQueue)
        .where(EntityMatchQueue.resolved == resolved)
        .order_by(EntityMatchQueue.confidence.desc())
        .limit(limit)
    )
    return result.scalars().all()  # type: ignore[return-value]


@queue_router.patch("/{queue_id}/resolve", response_model=EntityMatchQueueItem)
async def resolve_queue_entry(
    queue_id: uuid.UUID,
    company_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> EntityMatchQueueItem:
    """Mark a queue entry as resolved, optionally linking to a company."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(EntityMatchQueue).where(EntityMatchQueue.id == queue_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    entry.resolved = True
    entry.resolved_at = datetime.now(timezone.utc)
    if company_id is not None:
        entry.suggested_company_id = company_id

    await db.commit()
    await db.refresh(entry)
    return entry  # type: ignore[return-value]
