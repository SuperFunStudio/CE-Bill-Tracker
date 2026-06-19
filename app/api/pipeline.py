import httpx
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.config import settings
from app.database import get_db
from app.models import Bill

# Operator-only surface: every route triggers ingestion/classification jobs (LLM + external-API cost)
# or destructive DB ops (purge/reset). The service is public (--allow-unauthenticated), so the router
# itself must require an admin token — there's no frontend caller. See docs/SECURITY_ASSESSMENT.md C-2.
router = APIRouter(prefix="/pipeline", tags=["pipeline"], dependencies=[Depends(require_admin)])
log = structlog.get_logger()

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
_JOBS_API_BASE = "https://run.googleapis.com/v2"


async def _trigger_cloud_run_job(job_name: str, state_filter: str | None = None) -> dict:
    """Trigger a Cloud Run Job execution via the Jobs API.

    Falls back to a background task runner when running outside GCP (e.g. local dev),
    detected by the metadata server being unreachable.
    """
    project = settings.google_cloud_project
    region = settings.cloud_run_region
    url = f"{_JOBS_API_BASE}/projects/{project}/locations/{region}/jobs/{job_name}:run"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.get(
                _METADATA_TOKEN_URL,
                headers={"Metadata-Flavor": "Google"},
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

        body: dict = {}
        if state_filter:
            body["overrides"] = {
                "containerOverrides": [
                    {"env": [{"name": "STATE_FILTER", "value": state_filter.upper()}]}
                ]
            }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    except httpx.ConnectError:
        # Not running on GCP — metadata server unreachable. Fall back to local execution.
        log.warning("cloud_run_job_metadata_unavailable", job=job_name, fallback="background_task")
        return {"_fallback": "local"}
    except httpx.HTTPStatusError as e:
        log.error("cloud_run_job_trigger_failed", job=job_name, status=e.response.status_code,
                  body=e.response.text)
        raise HTTPException(status_code=502, detail=f"Failed to trigger Cloud Run Job: {e.response.text}")


@router.get("/status")
async def pipeline_status(db: AsyncSession = Depends(get_db)):
    """Return classification coverage stats for all bills in the database."""
    # Aggregate counts in a single query
    row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count()
                .filter(Bill.confidence_score.isnot(None), Bill.confidence_score >= 0)
                .label("classified"),
                func.count()
                .filter(Bill.confidence_score.is_(None))
                .label("unclassified"),
                func.count()
                .filter(Bill.confidence_score == -1.0)
                .label("awaiting_llm"),
                func.count()
                .filter(Bill.ce_relevant.is_(True))
                .label("ce_relevant"),
                func.count()
                .filter(
                    Bill.ce_relevant.is_(False),
                    Bill.confidence_score.isnot(None),
                    Bill.confidence_score >= 0,
                )
                .label("not_relevant"),
                func.count()
                .filter(Bill.compliance_details.isnot(None))
                .label("sonnet_extracted"),
                func.max(Bill.updated_at)
                .filter(Bill.confidence_score.isnot(None), Bill.confidence_score >= 0)
                .label("last_classified_at"),
            ).select_from(Bill)
        )
    ).one()

    # Status breakdown
    status_rows = (
        await db.execute(
            select(Bill.status, func.count())
            .group_by(Bill.status)
        )
    ).all()
    by_status = {s or "unknown": c for s, c in status_rows}

    # Source breakdown
    source_row = (
        await db.execute(
            select(
                func.count().filter(Bill.legiscan_bill_id.isnot(None)).label("legiscan"),
                func.count().filter(Bill.openstates_id.isnot(None)).label("openstates"),
                func.count()
                .filter(Bill.legiscan_bill_id.is_(None), Bill.openstates_id.is_(None))
                .label("seed"),
            ).select_from(Bill)
        )
    ).one()

    # State coverage: total LegiScan bills per state (excludes stubs)
    state_rows = (
        await db.execute(
            select(Bill.state, func.count().label("bill_count"))
            .where(Bill.legiscan_bill_id.isnot(None))
            .group_by(Bill.state)
            .order_by(Bill.state)
        )
    ).all()
    by_state_legiscan = {state: count for state, count in state_rows if state}

    return {
        "total_bills": row.total,
        "classified": row.classified,
        "unclassified": row.unclassified,
        "awaiting_llm": row.awaiting_llm,
        "ce_relevant": row.ce_relevant,
        "not_relevant": row.not_relevant,
        "sonnet_extracted": row.sonnet_extracted,
        "last_classified_at": row.last_classified_at.isoformat() if row.last_classified_at else None,
        "by_status": by_status,
        "by_source": {
            "legiscan": source_row.legiscan,
            "openstates": source_row.openstates,
            "seed": source_row.seed,
        },
        "by_state_legiscan": by_state_legiscan,
    }


@router.post("/run")
async def trigger_pipeline(
    background_tasks: BackgroundTasks,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger the ingestion + classification pipeline as a Cloud Run Job."""
    result = await _trigger_cloud_run_job("signalscout-pipeline", state_filter=state)

    if result.get("_fallback") == "local":
        from app.scheduler.jobs import run_ingestion_cycle
        background_tasks.add_task(run_ingestion_cycle, state_filter=state)
        return {"status": "triggered", "mode": "local_background", "state_filter": state}

    return {"status": "triggered", "job": "signalscout-pipeline", "state_filter": state}


@router.post("/run-classification")
async def trigger_classification(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Classify all unclassified bills already in the database via Cloud Run Job.

    Makes no LegiScan API calls — safe to run anytime, including when
    LegiScan quota is exhausted.
    """
    result = await _trigger_cloud_run_job("signalscout-classify")

    if result.get("_fallback") == "local":
        from app.scheduler.jobs import run_classification_cycle
        background_tasks.add_task(run_classification_cycle)
        return {"status": "triggered", "mode": "local_background"}

    return {"status": "triggered", "job": "signalscout-classify"}


@router.post("/run-openstates")
async def trigger_openstates(
    background_tasks: BackgroundTasks,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a full OpenStates historical sync (no updated_since filter)."""
    from app.scheduler.jobs import run_openstates_full_sync

    background_tasks.add_task(run_openstates_full_sync, state_filter=state)
    return {"status": "triggered", "state_filter": state}


@router.post("/run-federal")
async def trigger_federal(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger the Federal Register ingestion cycle."""
    from app.scheduler.jobs import run_federal_cycle

    background_tasks.add_task(run_federal_cycle)
    return {"status": "triggered"}




@router.post("/seed")
async def trigger_seed(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """DISABLED. The hand-curated seed was replaced by the OpenStates v3 sync; its rows were
    purged in migration 005. Use POST /pipeline/run-openstates for a full sync instead."""
    return {
        "status": "disabled",
        "reason": "seed replaced by OpenStates sync; see migration 005",
        "use_instead": "POST /pipeline/run-openstates",
    }


@router.get("/seed-coverage")
async def seed_coverage(db: AsyncSession = Depends(get_db)):
    """Read-only: check which previously-known enacted EPR laws are present after the
    OpenStates sync. Uses the old data/seed/known_epr_laws.json purely as a validation
    checklist (its rows were purged in migration 005). MISSING entries are OpenStates
    keyword-search coverage gaps — remediate by adding phrases to epr_keywords.json and
    re-syncing the relevant state, or via a targeted identifier/title backfill.
    """
    import json
    from pathlib import Path

    from app.ingestion.coordinator import _normalize_bill_number

    seed_path = Path(__file__).parent.parent.parent / "data" / "seed" / "known_epr_laws.json"
    with open(seed_path) as f:
        laws = json.load(f)

    matched: list[dict] = []
    missing: list[dict] = []
    for law in laws:
        state = law["state"]
        raw_number = law.get("bill_number") or ""
        normalized = _normalize_bill_number(raw_number)
        # Bills are stored with the normalized form (e.g. "LD-1541"); accept the raw form too.
        existing = (
            await db.execute(
                select(Bill.id, Bill.source_url, Bill.openstates_id).where(
                    Bill.state == state,
                    Bill.bill_number.in_([normalized, raw_number]),
                )
            )
        ).first()
        entry = {"state": state, "bill_number": raw_number, "normalized": normalized}
        if existing:
            matched.append({**entry, "bill_id": existing.id, "source_url": existing.source_url})
        else:
            missing.append(entry)

    return {
        "total_known_laws": len(laws),
        "matched_count": len(matched),
        "missing_count": len(missing),
        "missing": missing,
        "matched": matched,
    }


@router.post("/run-scoring")
async def trigger_scoring(background_tasks: BackgroundTasks):
    """Manually trigger the company impact scoring cycle."""
    from app.scheduler.jobs import run_scoring_cycle

    background_tasks.add_task(run_scoring_cycle)
    return {"status": "triggered"}


@router.post("/purge-legiscan")
async def purge_legiscan(db: AsyncSession = Depends(get_db)):
    """Delete all LegiScan-sourced bills and their dependent rows.

    The LegiScan free tier returns WV session 1 data for all state queries.
    Use this to clean up bills accidentally re-ingested via /pipeline/run.
    """
    from sqlalchemy import text

    subquery = "SELECT id FROM bills WHERE legiscan_bill_id IS NOT NULL"
    await db.execute(text(f"DELETE FROM impact_score WHERE bill_id IN ({subquery})"))
    await db.execute(text(f"DELETE FROM bill_changes WHERE bill_id IN ({subquery})"))
    await db.execute(text(f"DELETE FROM compliance_deadlines WHERE bill_id IN ({subquery})"))
    await db.execute(text(f"DELETE FROM exposure_brief WHERE bill_id IN ({subquery})"))
    await db.execute(text(f"UPDATE litigation_cases SET related_law_id = NULL WHERE related_law_id IN ({subquery})"))
    result = await db.execute(text("DELETE FROM bills WHERE legiscan_bill_id IS NOT NULL"))
    await db.commit()
    return {"status": "purged", "rows_deleted": result.rowcount}


@router.post("/reset-classification")
async def reset_classification(db: AsyncSession = Depends(get_db)):
    """Reset confidence_score to NULL on Open States bills that failed keyword filtering.

    Use this after updating epr_keywords.json and redeploying to re-evaluate
    previously-rejected bills with the new keyword set.
    Seed bills (no openstates_id) are never touched.
    """
    from sqlalchemy import update
    from app.models import Bill

    result = await db.execute(
        update(Bill)
        .where(
            Bill.openstates_id.isnot(None),
            Bill.confidence_score == 0.0,
        )
        .values(confidence_score=None, ce_relevant=False)
    )
    await db.commit()
    return {"status": "reset", "rows_reset": result.rowcount}

