"""Stripe billing — Checkout for the $39/mo Pro seat + the webhook that flips entitlement.

Flow: the authed dashboard POSTs /billing/checkout → we ensure a Stripe customer for the user's
email, open a Checkout Session for STRIPE_PRO_PRICE_ID, and return its URL. Stripe redirects back to
the dashboard, but the source of truth for "is this account Pro" is the webhook (/billing/webhook),
which upserts the Entitlement on checkout.session.completed + customer.subscription.* events.

Stripe's SDK is synchronous, so network calls run in a threadpool to avoid blocking the event loop.
See gating-and-monetization-plan.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import stripe
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.auth import AuthedUser, get_current_user, get_entitlement, is_pro
from app.config import settings
from app.database import get_db
from app.models import Entitlement

log = structlog.get_logger()
router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = settings.stripe_secret_key


@router.get("/me")
async def billing_me(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The dashboard's entitlement check — what plan is the signed-in user on."""
    ent = await get_entitlement(db, user)
    return {
        "email": user.email,
        "plan": ent.plan if ent else "free",
        "status": ent.status if ent else None,
        "is_pro": is_pro(ent),
        "current_period_end": (
            ent.current_period_end.isoformat() if ent and ent.current_period_end else None
        ),
    }


async def _get_or_create_entitlement(
    db: AsyncSession, email: str, firebase_uid: str | None
) -> Entitlement:
    res = await db.execute(select(Entitlement).where(Entitlement.email == email))
    ent = res.scalar_one_or_none()
    if ent is None:
        ent = Entitlement(email=email, firebase_uid=firebase_uid, plan="free")
        db.add(ent)
        await db.flush()
    elif firebase_uid and not ent.firebase_uid:
        ent.firebase_uid = firebase_uid
    return ent


@router.post("/checkout")
async def create_checkout(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a Stripe Checkout Session for the Pro subscription; return its hosted URL."""
    if not settings.stripe_secret_key or not settings.stripe_pro_price_id:
        raise HTTPException(status_code=503, detail="billing not configured")
    ent = await _get_or_create_entitlement(db, user.email, user.uid)

    if not ent.stripe_customer_id:
        customer = await run_in_threadpool(
            stripe.Customer.create, email=user.email, metadata={"firebase_uid": user.uid}
        )
        ent.stripe_customer_id = customer.id
    await db.commit()

    session = await run_in_threadpool(
        stripe.checkout.Session.create,
        mode="subscription",
        customer=ent.stripe_customer_id,
        line_items=[{"price": settings.stripe_pro_price_id, "quantity": 1}],
        success_url=f"{settings.app_base_url}/design-guide?checkout=success",
        cancel_url=f"{settings.app_base_url}/pricing?checkout=cancel",
        client_reference_id=user.uid,
        metadata={"email": user.email, "firebase_uid": user.uid},
        allow_promotion_codes=True,
    )
    return {"url": session.url}


@router.post("/portal")
async def billing_portal(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stripe-hosted customer portal so subscribers can manage/cancel their plan."""
    ent = await get_entitlement(db, user)
    if not ent or not ent.stripe_customer_id:
        raise HTTPException(status_code=404, detail="no stripe customer")
    session = await run_in_threadpool(
        stripe.billing_portal.Session.create,
        customer=ent.stripe_customer_id,
        return_url=f"{settings.app_base_url}/account",
    )
    return {"url": session.url}


def _period_end(sub) -> datetime | None:
    ts = sub.get("current_period_end") if isinstance(sub, dict) else getattr(sub, "current_period_end", None)
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


async def _apply_subscription(db: AsyncSession, customer_id: str | None, sub: dict) -> None:
    """Sync an Entitlement to a Stripe subscription object (status + period + plan)."""
    if not customer_id:
        return
    res = await db.execute(
        select(Entitlement).where(Entitlement.stripe_customer_id == customer_id)
    )
    ent = res.scalar_one_or_none()
    if not ent:
        return
    status = sub.get("status")
    ent.status = status
    ent.stripe_subscription_id = sub.get("id") or ent.stripe_subscription_id
    ent.current_period_end = _period_end(sub)
    ent.plan = "pro" if status in ("active", "trialing") else "free"
    # This seat is now Stripe-backed; clear any comp marker so its period_end isn't read as a comp expiry.
    ent.comp = False
    await db.commit()


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Stripe → us. Verifies the signature (when a signing secret is set) and upserts entitlement.

    This, not the redirect, is the source of truth for Pro access.
    """
    body = await request.body()
    sig = request.headers.get("stripe-signature")
    secret = settings.stripe_webhook_secret
    if secret:
        try:
            stripe.Webhook.construct_event(body, sig, secret)  # verify signature; raises on mismatch
        except Exception as e:
            log.warning("stripe_webhook_bad_signature", error=str(e))
            raise HTTPException(status_code=400, detail="invalid signature")
    # Always handle the event as a plain dict. Stripe's StripeObject routes .get() through
    # __getattr__ and raises AttributeError/KeyError, so we never touch the SDK object directly.
    event = json.loads(body)

    etype = event["type"]
    obj = event["data"]["object"]
    log.info("stripe_webhook", event_type=etype)

    if etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        email = (meta.get("email") or obj.get("customer_email") or "").lower().strip()
        uid = meta.get("firebase_uid") or obj.get("client_reference_id")
        if email:
            ent = await _get_or_create_entitlement(db, email, uid)
            ent.stripe_customer_id = obj.get("customer") or ent.stripe_customer_id
            ent.stripe_subscription_id = obj.get("subscription") or ent.stripe_subscription_id
            ent.plan = "pro"
            ent.status = "active"
            # A real paid conversion supersedes any complimentary grant — drop the comp marker so
            # is_pro() stops applying a comp expiry to what is now a Stripe-backed seat.
            ent.comp = False
            sub_id = obj.get("subscription")
            if sub_id:
                try:
                    sub_obj = await run_in_threadpool(stripe.Subscription.retrieve, sub_id)
                    sub = sub_obj.to_dict() if hasattr(sub_obj, "to_dict") else dict(sub_obj)
                    ent.status = sub.get("status", "active")
                    ent.current_period_end = _period_end(sub)
                except Exception as e:
                    log.warning("stripe_sub_retrieve_failed", error=str(e))
            await db.commit()

    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        await _apply_subscription(db, obj.get("customer"), obj)

    elif etype == "customer.subscription.deleted":
        res = await db.execute(
            select(Entitlement).where(Entitlement.stripe_customer_id == obj.get("customer"))
        )
        ent = res.scalar_one_or_none()
        if ent:
            ent.plan = "free"
            ent.status = "canceled"
            await db.commit()

    return {"received": True}
