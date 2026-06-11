from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.access_emails import send_access_request_emails
from app.database import get_db
from app.models import AccessRequest
from app.schemas import AccessRequestCreate, AccessRequestResponse

router = APIRouter(prefix="/access-requests", tags=["access"])

# Tiers a visitor can express interest in — the willingness-to-pay experiment. Kept permissive
# (validated, not enumerated in the DB) so we can add tiers without a migration.
_VALID_PLANS = {"pro", "team", "enterprise", "api", "company_impact"}


@router.post("", response_model=AccessRequestResponse, status_code=201)
async def create_access_request(
    payload: AccessRequestCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if not payload.email or "@" not in payload.email:
        raise HTTPException(status_code=422, detail="a valid email is required")
    if payload.plan_interest not in _VALID_PLANS:
        raise HTTPException(
            status_code=422,
            detail=f"plan_interest must be one of {sorted(_VALID_PLANS)}",
        )
    req = AccessRequest(**payload.model_dump())
    db.add(req)
    await db.commit()
    await db.refresh(req)
    # Auto-reply to the requester + notify the team, after the response (best-effort).
    background_tasks.add_task(
        send_access_request_emails,
        req.email,
        req.name,
        req.organization,
        req.plan_interest,
        req.message,
        req.source,
    )
    return req
