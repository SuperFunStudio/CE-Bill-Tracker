"""Company impact scoring API endpoints.

Three routers exported from this module:
  - router          → /companies/*
  - bills_exposure_router → /bills/{bill_id}/company-exposure
  - queue_router    → /entity-match-queue
"""
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import Bill, Company, EntityMatchQueue, ExposureBrief, ImpactScore
from app.schemas import (
    CompanyDetail,
    CompanySummary,
    EntityMatchQueueItem,
    ExposureBriefResponse,
    ExposureRanking,
    ImpactScoreResponse,
)

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
) -> ExposureBriefResponse:
    """Return a cached Exposure Brief for a (company, bill) pair, generating one if needed.

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
    hq_state: str | None = None,
    naics_code: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[CompanySummary]:
    """List companies with optional filters."""
    stmt = select(Company)

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

queue_router = APIRouter(prefix="/entity-match-queue", tags=["companies"])


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
