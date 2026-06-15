"""Per-account settings + the Pro watch list, behind Firebase-token auth.

/me/settings is free (any authenticated user) — it persists UI prefs (the saved scope) per Firebase
uid so they follow the user across devices. /me/watchlist is Pro-gated — the bills an account
follows. See app/api/auth.py + gating-and-monetization-plan.
"""
from __future__ import annotations

import stripe
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.auth import (
    AuthedUser,
    _ensure_firebase,
    get_current_user,
    get_entitlement,
    require_pro,
)
from app.config import settings
from app.database import get_db
from app.models import AlertSubscription, Entitlement, UserSettings, WatchlistItem

log = structlog.get_logger()
router = APIRouter(prefix="/me", tags=["me"])

# Events a watch-list follower can be notified about (the "global per-user" notification prefs).
# A subset of AlertSubscription.alert_on: a watch list tracks specific bills, so "new_bill" (which is
# about bills you haven't seen yet) doesn't apply.
WATCHLIST_ALERT_EVENTS = {"status_change", "text_update", "deadline"}
DEFAULT_WATCHLIST_ALERT_ON = ["status_change", "deadline"]


async def _get_watchlist_subscription(
    db: AsyncSession, uid: str
) -> AlertSubscription | None:
    res = await db.execute(
        select(AlertSubscription).where(
            AlertSubscription.firebase_uid == uid,
            AlertSubscription.scope == "watchlist",
        )
    )
    return res.scalar_one_or_none()


async def _ensure_watchlist_subscription(
    db: AsyncSession, user: AuthedUser
) -> AlertSubscription:
    """Return the user's watch-list alert subscription, creating it with default prefs if absent.

    This is the delivery side of the watch list: membership lives in user_watchlist, while this one
    row per user carries the notification prefs (which events to email about). min_confidence is 0 —
    a bill you explicitly starred should alert regardless of how the classifier scored it. Does not
    commit; the caller owns the transaction."""
    sub = await _get_watchlist_subscription(db, user.uid)
    if sub is None:
        sub = AlertSubscription(
            firebase_uid=user.uid,
            scope="watchlist",
            email=user.email,
            states=[],
            material_categories=[],
            instrument_types=[],
            min_confidence=0.0,
            alert_on=list(DEFAULT_WATCHLIST_ALERT_ON),
            active=True,
        )
        db.add(sub)
    elif not sub.email and user.email:
        sub.email = user.email
    return sub


class SettingsUpdate(BaseModel):
    prefs: dict


@router.get("/settings")
async def get_settings(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(UserSettings).where(UserSettings.firebase_uid == user.uid))
    row = res.scalar_one_or_none()
    return {"prefs": row.prefs if row else {}}


@router.put("/settings")
async def put_settings(
    payload: SettingsUpdate,
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(UserSettings).where(UserSettings.firebase_uid == user.uid))
    row = res.scalar_one_or_none()
    if row is None:
        row = UserSettings(firebase_uid=user.uid, email=user.email, prefs=payload.prefs or {})
        db.add(row)
    else:
        row.prefs = payload.prefs or {}
        if not row.email:
            row.email = user.email
    await db.commit()
    return {"prefs": row.prefs}


class WatchAdd(BaseModel):
    bill_id: int


@router.get("/watchlist")
async def get_watchlist(
    user: AuthedUser = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(WatchlistItem.bill_id).where(WatchlistItem.firebase_uid == user.uid)
    )
    return {"bill_ids": [r[0] for r in res.all()]}


@router.post("/watchlist", status_code=201)
async def add_watch(
    payload: WatchAdd,
    user: AuthedUser = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    exists = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.firebase_uid == user.uid,
            WatchlistItem.bill_id == payload.bill_id,
        )
    )
    if exists.scalar_one_or_none() is None:
        db.add(WatchlistItem(firebase_uid=user.uid, bill_id=payload.bill_id))
        # Following a bill opts the user into the alert pipeline: ensure their watch-list alert
        # subscription exists (with default prefs) so status changes on this bill reach them.
        await _ensure_watchlist_subscription(db, user)
        try:
            await db.commit()
        except IntegrityError:
            # Bad bill_id (FK) or a concurrent insert — neither should 500 the client.
            await db.rollback()
    return {"bill_id": payload.bill_id, "watched": True}


@router.delete("/watchlist/{bill_id}")
async def remove_watch(
    bill_id: int,
    user: AuthedUser = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.firebase_uid == user.uid,
            WatchlistItem.bill_id == bill_id,
        )
    )
    await db.commit()
    return {"bill_id": bill_id, "watched": False}


class WatchlistPrefs(BaseModel):
    # Which events to email about for watched bills. Subset of WATCHLIST_ALERT_EVENTS.
    alert_on: list[str]
    # Master on/off for watch-list emails (the subscription's active flag).
    active: bool = True


def _prefs_payload(sub: AlertSubscription | None) -> dict:
    if sub is None:
        return {"alert_on": list(DEFAULT_WATCHLIST_ALERT_ON), "active": True}
    return {"alert_on": list(sub.alert_on or []), "active": bool(sub.active)}


@router.get("/watchlist/prefs")
async def get_watchlist_prefs(
    user: AuthedUser = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    """The user's watch-list notification prefs. Returns defaults if they haven't starred a bill yet
    (no subscription row created)."""
    return _prefs_payload(await _get_watchlist_subscription(db, user.uid))


@router.put("/watchlist/prefs")
async def put_watchlist_prefs(
    payload: WatchlistPrefs,
    user: AuthedUser = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    """Update which events the user is emailed about for their watched bills. Creates the
    subscription if it doesn't exist yet, so prefs can be set before the first star."""
    # Drop anything outside the allowed set (e.g. "new_bill" doesn't apply to a watch list).
    cleaned = [e for e in payload.alert_on if e in WATCHLIST_ALERT_EVENTS]
    sub = await _ensure_watchlist_subscription(db, user)
    sub.alert_on = cleaned
    sub.active = payload.active
    await db.commit()
    return _prefs_payload(sub)


@router.delete("/account")
async def delete_account(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete the signed-in account: cancel any live Stripe subscription, purge the
    user's rows, then remove the Firebase user.

    Order matters: cancel billing first (so a failed purge never leaves an uncancelled sub), then
    erase data, then delete the auth identity last (its token is still needed to reach this route).
    Stripe and Firebase calls are best-effort — a failure there must not block the local erase, so
    the caller gets a clean account-gone response even if an external system lagged. The response
    flags whether the Firebase delete actually landed (it needs the Firebase Auth Admin role, which
    may be absent in some environments — see app/api/auth.py)."""
    ent = await get_entitlement(db, user)

    # 1. Cancel the Stripe subscription if it's live. Best-effort: log and continue on failure.
    if ent and ent.stripe_subscription_id and ent.status in ("active", "trialing"):
        stripe.api_key = settings.stripe_secret_key
        try:
            await run_in_threadpool(stripe.Subscription.delete, ent.stripe_subscription_id)
        except Exception as e:  # noqa: BLE001 — never let billing block the erase
            log.warning("delete_account_stripe_cancel_failed", error=str(e), email=user.email)

    # 2. Purge all of this user's rows. WatchlistItem / UserSettings / the watch-list AlertSubscription
    #    key on firebase_uid; topic-alert subscriptions and the Entitlement key on email.
    await db.execute(delete(WatchlistItem).where(WatchlistItem.firebase_uid == user.uid))
    await db.execute(delete(UserSettings).where(UserSettings.firebase_uid == user.uid))
    await db.execute(
        delete(AlertSubscription).where(
            (AlertSubscription.firebase_uid == user.uid)
            | (AlertSubscription.email == user.email)
        )
    )
    await db.execute(delete(Entitlement).where(Entitlement.email == user.email))
    await db.commit()

    # 3. Delete the Firebase auth user last. Privileged call — needs the Firebase Auth Admin role.
    firebase_deleted = False
    try:
        _ensure_firebase()
        from firebase_admin import auth as fb_auth

        await run_in_threadpool(fb_auth.delete_user, user.uid)
        firebase_deleted = True
    except Exception as e:  # noqa: BLE001 — data is already gone; report the lag, don't 500
        log.warning("delete_account_firebase_delete_failed", error=str(e), uid=user.uid)

    log.info("account_deleted", email=user.email, firebase_deleted=firebase_deleted)
    return {"deleted": True, "firebase_deleted": firebase_deleted}
