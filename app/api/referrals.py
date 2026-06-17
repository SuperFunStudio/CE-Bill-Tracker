"""Share-to-unlock referrals.

A signed-in account gets a stable referral_code (GET /referrals/me). When a NEW account signs up via
that code, the frontend calls POST /referrals/attribute, which records the referral and grants the
*referrer* a 30-day comp Pro seat (reusing the comp-grant machinery — see app/api/auth.is_pro). Guards:
a code can't credit its own owner, and a given new account can only be the referred party once
(unique referred_uid), so the grant can't be replayed. Residual abuse (a sharer spinning up throwaway
accounts to self-refer) is inherent to the "friend signs up" model and accepted for launch — at least
each one is a real account. See state-profile-pages / compliance-action-vision.
"""
# NOTE: no `from __future__ import annotations` — see the note in app/api/billing.py (slowapi's
# @limiter.limit wrapper + stringized annotations don't mix). PEP 604 unions are fine at runtime here.
import secrets
import string

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthedUser, get_current_user, grant_comp_days
from app.database import get_db
from app.models import Entitlement, Referral
from app.ratelimit import limiter

log = structlog.get_logger()
router = APIRouter(prefix="/referrals", tags=["referrals"])

# Unambiguous alphabet (no 0/O/1/I) — codes get typed/copied by humans.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_REFERRAL_GRANT_DAYS = 30


async def _get_or_create_entitlement(db: AsyncSession, user: AuthedUser) -> Entitlement:
    res = await db.execute(select(Entitlement).where(Entitlement.email == user.email))
    ent = res.scalar_one_or_none()
    if ent is None:
        ent = Entitlement(email=user.email, firebase_uid=user.uid, plan="free")
        db.add(ent)
        await db.flush()
    elif user.uid and not ent.firebase_uid:
        ent.firebase_uid = user.uid
    return ent


async def _ensure_code(db: AsyncSession, ent: Entitlement) -> str:
    if ent.referral_code:
        return ent.referral_code
    for _ in range(6):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        clash = await db.execute(select(Entitlement.id).where(Entitlement.referral_code == code))
        if clash.scalar_one_or_none() is None:
            ent.referral_code = code
            await db.commit()
            return code
    # Astronomically unlikely with a 32^8 space; fall back to a uid-derived code.
    ent.referral_code = (ent.firebase_uid or secrets.token_hex(4))[:16]
    await db.commit()
    return ent.referral_code


@router.get("/me")
async def my_referral(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The signed-in account's referral code (generated on first call). The frontend builds the share
    link as `<origin>/?ref=<code>`."""
    ent = await _get_or_create_entitlement(db, user)
    code = await _ensure_code(db, ent)
    return {"code": code}


class AttributeRequest(BaseModel):
    code: str


@router.post("/attribute")
@limiter.limit("30/hour")
async def attribute(
    request: Request,
    payload: AttributeRequest,
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Credit a referral for the signed-in (newly-created) account and grant the referrer 30 days of
    Pro. Idempotent / guarded; returns {granted: bool, reason?}."""
    code = (payload.code or "").strip().upper()
    if not code:
        return {"granted": False, "reason": "no_code"}

    # The referred account must have a verified email before it can credit anyone — this is the lever
    # that stops a sharer from farming referral rewards with scripted throwaway signups (each one would
    # have to pass real email verification). The frontend keeps the pending code and retries once the
    # new account verifies. See docs/SECURITY_ASSESSMENT.md H-2.
    if not user.email_verified:
        return {"granted": False, "reason": "email_unverified"}

    referrer = (
        await db.execute(select(Entitlement).where(Entitlement.referral_code == code))
    ).scalar_one_or_none()
    if not referrer:
        return {"granted": False, "reason": "invalid_code"}
    if referrer.firebase_uid == user.uid:
        return {"granted": False, "reason": "self"}

    already = (
        await db.execute(select(Referral.id).where(Referral.referred_uid == user.uid))
    ).scalar_one_or_none()
    if already:
        return {"granted": False, "reason": "already_referred"}

    # Make sure the referred account exists (so it can't be double-credited later) and record + grant.
    await _get_or_create_entitlement(db, user)
    db.add(
        Referral(
            referrer_uid=referrer.firebase_uid or "",
            referred_uid=user.uid,
            referred_email=user.email,
        )
    )
    grant_comp_days(referrer, _REFERRAL_GRANT_DAYS)
    await db.commit()
    log.info("referral_granted", referrer_uid=referrer.firebase_uid, referred_uid=user.uid)
    return {"granted": True}
