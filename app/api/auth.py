"""Firebase ID-token verification for premium routes.

The dashboard signs users in with Firebase Auth (email/password + Google) and sends the resulting
ID token as `Authorization: Bearer <token>`. We verify it with firebase-admin (project-scoped, via
the Cloud Run service account's ADC) and resolve the caller's entitlement. Identity is keyed on the
verified email, the same key the billing webhook writes. See gating-and-monetization-plan.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Entitlement

log = structlog.get_logger()

_initialized = False


def _ensure_firebase() -> None:
    """Initialize the firebase-admin app once. Token verification only needs the project id plus
    Google's public certs (fetched over HTTPS), so this works with ADC on Cloud Run and without
    any credentials locally."""
    global _initialized
    if _initialized:
        return
    import firebase_admin
    from firebase_admin import credentials

    if not firebase_admin._apps:
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})
        except Exception:
            firebase_admin.initialize_app(options={"projectId": settings.firebase_project_id})
    _initialized = True


class AuthedUser:
    def __init__(self, uid: str, email: str):
        self.uid = uid
        self.email = email


async def get_current_user(authorization: str | None = Header(default=None)) -> AuthedUser:
    """Verify the Bearer Firebase ID token; 401 on missing/invalid. Returns uid + verified email."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    _ensure_firebase()
    from firebase_admin import auth as fb_auth

    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception as e:
        log.info("firebase_token_invalid", error=str(e))
        raise HTTPException(status_code=401, detail="invalid or expired token")
    email = (decoded.get("email") or "").lower().strip()
    uid = decoded.get("uid") or decoded.get("user_id") or ""
    if not email or not uid:
        raise HTTPException(status_code=401, detail="token missing email/uid")
    return AuthedUser(uid=uid, email=email)


async def get_entitlement(db: AsyncSession, user: AuthedUser) -> Entitlement | None:
    res = await db.execute(select(Entitlement).where(Entitlement.email == user.email))
    return res.scalar_one_or_none()


def is_pro(ent: Entitlement | None) -> bool:
    """A live Pro seat: plan is pro and the subscription is in good standing (active or trialing).

    "trialing" counts — a founding 90-day Stripe trial is full Pro access. A complimentary grant
    (ent.comp) has no Stripe webhook to flip it off, so we enforce its expiry here: a comp seat whose
    current_period_end has passed is no longer Pro. A NULL period_end on a comp seat means indefinite.
    """
    if not (ent and ent.plan == "pro" and ent.status in ("active", "trialing")):
        return False
    if ent.comp and ent.current_period_end and ent.current_period_end < datetime.now(timezone.utc):
        return False
    return True


def grant_comp_days(ent: Entitlement, days: int) -> None:
    """Give an entitlement `days` of complimentary (no-card) Pro, stacking on an existing comp grant.
    A real paid subscription is left untouched — it doesn't need it. Used by the signup trial (7d) and
    the referral reward (30d); is_pro() enforces the expiry since there's no Stripe webhook behind it.
    """
    now = datetime.now(timezone.utc)
    if ent.plan == "pro" and not ent.comp and ent.status in ("active", "trialing"):
        return
    base = (
        ent.current_period_end
        if (ent.comp and ent.current_period_end and ent.current_period_end > now)
        else now
    )
    ent.plan = "pro"
    ent.status = "active"
    ent.comp = True
    ent.current_period_end = base + timedelta(days=days)


async def require_pro(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthedUser:
    """Guard for Pro-only routes — 401 if unauthenticated, 403 if authenticated but not Pro."""
    ent = await get_entitlement(db, user)
    if not is_pro(ent):
        raise HTTPException(status_code=403, detail="pro subscription required")
    return user


def is_admin(user: AuthedUser) -> bool:
    """Is this verified email on the admin allowlist (settings.admin_emails)?"""
    allow = {e.lower().strip() for e in settings.admin_emails}
    return bool(user.email) and user.email.lower().strip() in allow


async def require_admin(
    user: AuthedUser = Depends(get_current_user),
) -> AuthedUser:
    """Guard for the hidden /admin console — 401 if unauthenticated, 403 if not an admin."""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="admin access required")
    return user
