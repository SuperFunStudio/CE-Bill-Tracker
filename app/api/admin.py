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

import stripe
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.auth import AuthedUser, _ensure_firebase, is_pro, require_admin
from app.config import settings
from app.database import get_db
from app.models import (
    AccessRequest,
    AlertSubscription,
    Bill,
    Entitlement,
    FederalAction,
    UserSettings,
    WatchlistItem,
)

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


# ── Account management ─────────────────────────────────────────────────────────
# There is no central "users" table — identity lives in Firebase Auth, and a person's data is keyed
# two ways: by firebase_uid (watchlist, settings, watchlist alert-sub) and by email (entitlement,
# anonymous filter subs). So an account is resolved from BOTH: we gather every firebase_uid we've
# seen for an email across our own rows AND from Firebase, then act on the union. Firebase calls are
# best-effort — the firebase-admin role may be absent (same caveat as the user self-delete in
# app/api/user.py), so DB purges still work even when Firebase is unreachable.


def _ms_to_iso(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


async def _firebase_user(email: str) -> tuple[dict | None, str | None]:
    """Best-effort Firebase lookup by email. Returns (info, error) — info is None if the user doesn't
    exist or Firebase is unreachable/unauthorized, with the reason in error."""
    try:
        _ensure_firebase()
        from firebase_admin import auth as fb_auth

        u = await run_in_threadpool(fb_auth.get_user_by_email, email)
        meta = getattr(u, "user_metadata", None)
        return (
            {
                "uid": u.uid,
                "disabled": bool(u.disabled),
                "email_verified": bool(u.email_verified),
                "providers": [p.provider_id for p in (u.provider_data or [])],
                "created_at": _ms_to_iso(getattr(meta, "creation_timestamp", None)),
                "last_sign_in_at": _ms_to_iso(getattr(meta, "last_sign_in_timestamp", None)),
            },
            None,
        )
    except Exception as e:  # noqa: BLE001 — UserNotFound, missing role, or no network all land here
        return None, str(e)


async def _collect_uids(db: AsyncSession, email: str) -> set[str]:
    """Every firebase_uid we've ever associated with this email, across our own tables."""
    uids: set[str] = set()
    for stmt in (
        select(Entitlement.firebase_uid).where(Entitlement.email == email),
        select(UserSettings.firebase_uid).where(UserSettings.email == email),
        select(AlertSubscription.firebase_uid).where(AlertSubscription.email == email),
    ):
        for (uid,) in (await db.execute(stmt)).all():
            if uid:
                uids.add(uid)
    return uids


@router.get("/account")
async def admin_account(
    email: str,
    _: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Everything we know about one account, resolved by email: entitlement, Firebase identity
    (best-effort), and how much data is attached (watchlist + subscriptions + saved settings)."""
    email = (email or "").lower().strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="a valid email is required")

    ent = (
        await db.execute(select(Entitlement).where(Entitlement.email == email))
    ).scalar_one_or_none()

    fb, fb_err = await _firebase_user(email)
    uids = await _collect_uids(db, email)
    if fb:
        uids.add(fb["uid"])

    watch_count = 0
    if uids:
        watch_count = (
            await db.execute(
                select(func.count()).select_from(WatchlistItem).where(
                    WatchlistItem.firebase_uid.in_(uids)
                )
            )
        ).scalar() or 0

    sub_filter = or_(AlertSubscription.email == email)
    if uids:
        sub_filter = or_(AlertSubscription.email == email, AlertSubscription.firebase_uid.in_(uids))
    subs = (
        await db.execute(select(AlertSubscription).where(sub_filter))
    ).scalars().all()

    settings_present = (
        await db.execute(
            select(func.count()).select_from(UserSettings).where(UserSettings.email == email)
        )
    ).scalar() or 0

    return {
        "email": email,
        "exists": bool(ent or fb or uids or subs or settings_present),
        "entitlement": _entitlement_payload(ent) if ent else None,
        "firebase": fb,
        "firebase_error": fb_err,
        "uids_known": sorted(uids),
        "watchlist_count": watch_count,
        "settings_present": bool(settings_present),
        "subscriptions": [
            {
                "id": s.id,
                "scope": s.scope,
                "active": s.active,
                "states": s.states or [],
                "instrument_types": s.instrument_types or [],
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in subs
        ],
    }


class AccountEmail(BaseModel):
    email: str


@router.post("/account/delete")
async def admin_delete_account(
    payload: AccountEmail,
    admin: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete an account by email — the admin-driven twin of the user self-delete:
    cancel any live Stripe sub, purge every row keyed to the email or its firebase uids, then delete
    the Firebase auth user(s). Best-effort on Stripe + Firebase so a lagging external system never
    blocks the local erase. Refuses to delete the acting admin's own account (use the Account page)."""
    email = (payload.email or "").lower().strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="a valid email is required")
    if email == admin.email.lower().strip():
        raise HTTPException(status_code=409, detail="refusing to delete your own admin account here")

    ent = (
        await db.execute(select(Entitlement).where(Entitlement.email == email))
    ).scalar_one_or_none()

    fb, _fb_err = await _firebase_user(email)
    uids = await _collect_uids(db, email)
    if fb:
        uids.add(fb["uid"])

    # 1. Cancel a live Stripe subscription first (best-effort).
    if ent and ent.stripe_subscription_id and ent.status in ("active", "trialing"):
        stripe.api_key = settings.stripe_secret_key
        try:
            await run_in_threadpool(stripe.Subscription.delete, ent.stripe_subscription_id)
        except Exception as e:  # noqa: BLE001 — never let billing block the erase
            log.warning("admin_delete_stripe_cancel_failed", error=str(e), email=email)

    # 2. Purge all rows. uid-keyed (watchlist) + email-or-uid keyed (settings, subscriptions) +
    #    email-keyed (entitlement).
    if uids:
        await db.execute(delete(WatchlistItem).where(WatchlistItem.firebase_uid.in_(uids)))
    await db.execute(
        delete(UserSettings).where(
            or_(UserSettings.email == email, UserSettings.firebase_uid.in_(uids or {""}))
        )
    )
    await db.execute(
        delete(AlertSubscription).where(
            or_(AlertSubscription.email == email, AlertSubscription.firebase_uid.in_(uids or {""}))
        )
    )
    await db.execute(delete(Entitlement).where(Entitlement.email == email))
    await db.commit()

    # 3. Delete the Firebase auth user(s) last (best-effort — needs the Firebase Auth Admin role).
    firebase_deleted = 0
    if uids:
        try:
            _ensure_firebase()
            from firebase_admin import auth as fb_auth

            for uid in uids:
                try:
                    await run_in_threadpool(fb_auth.delete_user, uid)
                    firebase_deleted += 1
                except Exception as e:  # noqa: BLE001 — data already gone; report the lag
                    log.warning("admin_delete_firebase_failed", error=str(e), uid=uid)
        except Exception as e:  # noqa: BLE001 — firebase unavailable entirely
            log.warning("admin_delete_firebase_unavailable", error=str(e), email=email)

    log.info("admin_delete_account", target=email, by=admin.email, uids=len(uids), fb_deleted=firebase_deleted)
    return {"deleted": True, "email": email, "uids": len(uids), "firebase_deleted": firebase_deleted}


class AccountDisable(BaseModel):
    email: str
    disabled: bool


@router.post("/account/disable")
async def admin_set_account_disabled(
    payload: AccountDisable,
    admin: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Suspend or restore a user's ability to sign in (Firebase `disabled` flag) — a reversible freeze
    that leaves their data intact. Needs the Firebase Auth Admin role; returns 502 if Firebase can't
    be reached. Refuses to disable the acting admin's own account."""
    email = (payload.email or "").lower().strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="a valid email is required")
    if payload.disabled and email == admin.email.lower().strip():
        raise HTTPException(status_code=409, detail="refusing to disable your own admin account")

    try:
        _ensure_firebase()
        from firebase_admin import auth as fb_auth

        u = await run_in_threadpool(fb_auth.get_user_by_email, email)
        await run_in_threadpool(fb_auth.update_user, u.uid, disabled=payload.disabled)
    except Exception as e:  # noqa: BLE001 — user-not-found, missing role, or no network
        # Log the detail server-side; return a generic message rather than echoing the backend
        # exception string to the client (L-1).
        log.warning("admin_set_disabled_failed", target=email, error=str(e))
        raise HTTPException(status_code=502, detail="could not update the Firebase user")
    log.info("admin_set_disabled", target=email, by=admin.email, disabled=payload.disabled)
    return {"email": email, "disabled": payload.disabled}
