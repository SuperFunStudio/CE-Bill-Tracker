"""Hidden admin console API — behind the email allowlist (settings.admin_emails), not Pro.

Everything here is guarded by require_admin, so a non-admin (even a paying Pro) gets 403. The console
(dashboard-next /admin) drives sign-up management, complimentary Pro grants, an entitlements view, and
top-line stats including how fresh the bill data is. No route here is linked from the public nav — the
real gate is require_admin on every endpoint, not the missing link.

A complimentary ("comp") grant writes an Entitlement with plan="pro", status="active", comp=True and
NO Stripe subscription; current_period_end is the optional expiry (NULL = indefinite). See the comp
columns on Entitlement (migration 018) and is_pro() in app/api/auth.py for how expiry is enforced.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthedUser, is_pro, require_admin
from app.database import get_db
from app.models import AccessRequest, AlertSubscription, Bill, Entitlement, FederalAction

log = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"])

# Pagination ceiling for the list endpoints — keep payloads sane.
MAX_LIMIT = 200


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


@router.get("/me")
async def admin_me(user: AuthedUser = Depends(require_admin)):
    """Cheap admin probe for the frontend: 200 {is_admin: true} for an admin, 403 otherwise."""
    return {"is_admin": True, "email": user.email}


@router.get("/stats")
async def admin_stats(
    _: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Top-line counts + data-freshness markers for the console dashboard."""
    now = datetime.now(timezone.utc)

    # Free email sign-ups = public "filter"-scope subscriptions that carry an email.
    sub_q = select(func.count()).select_from(AlertSubscription).where(
        AlertSubscription.scope == "filter", AlertSubscription.email.isnot(None)
    )
    active_subs = (await db.execute(sub_q.where(AlertSubscription.active.is_(True)))).scalar() or 0
    total_subs = (await db.execute(sub_q)).scalar() or 0

    # Live Pro seats, split into paid vs complimentary. A comp seat past its expiry no longer counts.
    live = (Entitlement.plan == "pro", Entitlement.status.in_(("active", "trialing")))
    not_expired = or_(
        Entitlement.comp.is_(False),
        Entitlement.current_period_end.is_(None),
        Entitlement.current_period_end > now,
    )
    pro_total = (
        await db.execute(select(func.count()).select_from(Entitlement).where(*live, not_expired))
    ).scalar() or 0
    comp_total = (
        await db.execute(
            select(func.count())
            .select_from(Entitlement)
            .where(*live, not_expired, Entitlement.comp.is_(True))
        )
    ).scalar() or 0

    access_total = (
        await db.execute(select(func.count()).select_from(AccessRequest))
    ).scalar() or 0

    bills_total = (await db.execute(select(func.count()).select_from(Bill))).scalar() or 0
    bills_relevant = (
        await db.execute(
            select(func.count()).select_from(Bill).where(Bill.epr_relevant.is_(True))
        )
    ).scalar() or 0

    # Data freshness — when the bill corpus was last touched / last reflected real legislative motion.
    last_updated = (await db.execute(select(func.max(Bill.updated_at)))).scalar()
    last_fetched = (await db.execute(select(func.max(Bill.last_fetched_at)))).scalar()
    # Latest TRACKED action: relevant bills only, and never future-dated. Plain max(last_action_date)
    # is misleading — a handful of out-of-scope bills carry future scheduled/effective dates (e.g. a
    # 2027-01-01 GA insurance bill), and decades-old enacted laws we re-touch sort low. This matches
    # the homepage's "most recent activity" (EPR-relevant, sorted by last_action_date).
    last_action = (
        await db.execute(
            select(func.max(Bill.last_action_date)).where(
                Bill.epr_relevant.is_(True),
                Bill.last_action_date <= now.date(),
            )
        )
    ).scalar()
    fed_last = (await db.execute(select(func.max(FederalAction.published_date)))).scalar()

    return {
        "subscribers_active": active_subs,
        "subscribers_total": total_subs,
        "pro_total": pro_total,
        "pro_paid": pro_total - comp_total,
        "pro_comp": comp_total,
        "access_requests": access_total,
        "bills_total": bills_total,
        "bills_relevant": bills_relevant,
        "data_freshness": {
            "bills_last_updated": last_updated.isoformat() if last_updated else None,
            "bills_last_fetched": last_fetched.isoformat() if last_fetched else None,
            "bills_last_action": last_action.isoformat() if last_action else None,
            "federal_last_published": fed_last.isoformat() if fed_last else None,
        },
    }


@router.get("/subscribers")
async def list_subscribers(
    search: str | None = None,
    active: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    _: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """The public free-update sign-ups (filter-scope subscriptions), newest first. Optional email/org
    search and active filter."""
    limit = _clamp_limit(limit)
    q = select(AlertSubscription).where(AlertSubscription.scope == "filter")
    if search:
        like = f"%{search.strip()}%"
        q = q.where(
            or_(
                AlertSubscription.email.ilike(like),
                AlertSubscription.organization.ilike(like),
            )
        )
    if active is not None:
        q = q.where(AlertSubscription.active.is_(active))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            q.order_by(AlertSubscription.created_at.desc()).limit(limit).offset(max(0, offset))
        )
    ).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": s.id,
                "email": s.email,
                "organization": s.organization,
                "states": s.states or [],
                "instrument_types": s.instrument_types or [],
                "material_categories": s.material_categories or [],
                "active": s.active,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ],
    }


class SubscriberActive(BaseModel):
    active: bool


@router.post("/subscribers/{subscription_id}/active")
async def set_subscriber_active(
    subscription_id: int,
    payload: SubscriberActive,
    _: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Activate or deactivate a sign-up (mute/unmute their alerts without deleting the record)."""
    sub = (
        await db.execute(
            select(AlertSubscription).where(AlertSubscription.id == subscription_id)
        )
    ).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="subscription not found")
    sub.active = payload.active
    await db.commit()
    return {"id": sub.id, "active": sub.active}


@router.get("/access-requests")
async def list_access_requests(
    limit: int = 100,
    offset: int = 0,
    _: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """The willingness-to-pay leads (pricing / company-gate clicks), newest first."""
    limit = _clamp_limit(limit)
    total = (await db.execute(select(func.count()).select_from(AccessRequest))).scalar() or 0
    rows = (
        await db.execute(
            select(AccessRequest)
            .order_by(AccessRequest.created_at.desc())
            .limit(limit)
            .offset(max(0, offset))
        )
    ).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "email": r.email,
                "name": r.name,
                "organization": r.organization,
                "plan_interest": r.plan_interest,
                "message": r.message,
                "source": r.source,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


def _entitlement_payload(e: Entitlement) -> dict:
    return {
        "email": e.email,
        "plan": e.plan,
        "status": e.status,
        "is_pro": is_pro(e),
        "comp": e.comp,
        "comp_note": e.comp_note,
        "comp_granted_by": e.comp_granted_by,
        "comp_granted_at": e.comp_granted_at.isoformat() if e.comp_granted_at else None,
        "has_stripe": bool(e.stripe_subscription_id),
        "current_period_end": e.current_period_end.isoformat() if e.current_period_end else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("/entitlements")
async def list_entitlements(
    search: str | None = None,
    plan: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """All accounts with a billing identity (paid + comp + free-with-history), newest first."""
    limit = _clamp_limit(limit)
    q = select(Entitlement)
    if search:
        q = q.where(Entitlement.email.ilike(f"%{search.strip()}%"))
    if plan:
        q = q.where(Entitlement.plan == plan)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            q.order_by(Entitlement.created_at.desc()).limit(limit).offset(max(0, offset))
        )
    ).scalars().all()
    return {"total": total, "items": [_entitlement_payload(e) for e in rows]}


class GrantPro(BaseModel):
    email: str
    # Days until the comp grant expires; omit/None for an indefinite grant.
    days: int | None = None
    # Why it was granted (e.g. "early partner", "design jam attendee") — audit trail.
    note: str | None = None


@router.post("/grant-pro")
async def grant_pro(
    payload: GrantPro,
    admin: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Grant complimentary Pro to an email. Upserts the Entitlement (creating a row for an email that
    has never had one). Idempotent — re-granting refreshes the expiry/note. A grant on top of a live
    Stripe subscription is refused (manage paid seats in Stripe)."""
    email = (payload.email or "").lower().strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="a valid email is required")
    if payload.days is not None and payload.days <= 0:
        raise HTTPException(status_code=422, detail="days must be a positive number")

    ent = (
        await db.execute(select(Entitlement).where(Entitlement.email == email))
    ).scalar_one_or_none()
    if ent is None:
        ent = Entitlement(email=email)
        db.add(ent)
    elif ent.stripe_subscription_id and ent.status in ("active", "trialing") and not ent.comp:
        raise HTTPException(
            status_code=409,
            detail="this email has a live Stripe subscription — manage it in Stripe, not here",
        )

    now = datetime.now(timezone.utc)
    ent.plan = "pro"
    ent.status = "active"
    ent.comp = True
    ent.comp_note = (payload.note or None)
    ent.comp_granted_by = admin.email
    ent.comp_granted_at = now
    ent.current_period_end = now + timedelta(days=payload.days) if payload.days else None
    await db.commit()
    await db.refresh(ent)
    log.info(
        "admin_grant_pro", target=email, by=admin.email, days=payload.days, indefinite=not payload.days
    )
    return _entitlement_payload(ent)


class RevokePro(BaseModel):
    email: str


@router.post("/revoke-pro")
async def revoke_pro(
    payload: RevokePro,
    admin: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a complimentary grant (back to free). Only comp grants are revocable here — a paid
    Stripe subscription must be cancelled through Stripe so the two systems can't drift."""
    email = (payload.email or "").lower().strip()
    ent = (
        await db.execute(select(Entitlement).where(Entitlement.email == email))
    ).scalar_one_or_none()
    if not ent:
        raise HTTPException(status_code=404, detail="no entitlement for that email")
    if not ent.comp:
        raise HTTPException(
            status_code=409,
            detail="not a complimentary grant — cancel the Stripe subscription instead",
        )
    ent.plan = "free"
    ent.status = "canceled"
    ent.comp = False
    ent.current_period_end = None
    await db.commit()
    log.info("admin_revoke_pro", target=email, by=admin.email)
    return _entitlement_payload(ent)
