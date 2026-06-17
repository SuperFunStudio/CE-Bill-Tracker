"""Stripe billing — Checkout for the annual Pro seat + the webhook that flips entitlement.

Flow: the authed dashboard POSTs /billing/checkout → we ensure a Stripe customer for the user's
email, open a Checkout Session for the annual Pro price (with the founding launch offer: a first-year
coupon + a 90-day free trial), and return its URL. Stripe redirects back to the dashboard, but the
source of truth for "is this account Pro" is the webhook (/billing/webhook), which upserts the
Entitlement on checkout.session.completed + customer.subscription.* events.

Stripe's SDK is synchronous, so network calls run in a threadpool to avoid blocking the event loop.
See gating-and-monetization-plan.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import stripe
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.auth import AuthedUser, get_current_user, get_entitlement, grant_comp_days, is_pro
from app.config import settings
from app.database import get_db
from app.models import Entitlement

log = structlog.get_logger()
router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = settings.stripe_secret_key


def _price_for_period(period: str) -> str:
    """The configured Stripe price id for a billing period ("annual" | "monthly"); "" if unconfigured."""
    return {
        "annual": settings.stripe_pro_annual_price_id,
        "monthly": settings.stripe_pro_monthly_price_id,
    }.get(period, "")


@router.get("/me")
async def billing_me(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The dashboard's entitlement check — is the signed-in user on Pro.

    `is_pro` is the gate boolean the frontend reads. `is_trial` flags a seat that's mid-trial (either
    a founding Stripe trial — status "trialing" — or a complimentary grant) so the UI can show a
    "trial — N days left" badge and a convert nudge.
    """
    ent = await get_entitlement(db, user)
    return {
        "email": user.email,
        "plan": ent.plan if ent else "free",
        "status": ent.status if ent else None,
        "is_pro": is_pro(ent),
        "is_trial": bool(ent and is_pro(ent) and (ent.status == "trialing" or ent.comp)),
        "is_founding": bool(ent and ent.founding),
        "current_period_end": (
            ent.current_period_end.isoformat() if ent and ent.current_period_end else None
        ),
    }


# First rung of the value ladder: a no-card taste of Pro on signup.
_SIGNUP_TRIAL_DAYS = 7


@router.post("/signup-trial")
async def signup_trial(
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant this account its one-time 7-day signup trial (full Pro, no card). Idempotent — a no-op
    if the trial was already used. Called by the frontend right after a free account is created."""
    ent = await _get_or_create_entitlement(db, user.email, user.uid)
    if ent.signup_trial_used:
        return {"granted": False, "reason": "already_used"}
    grant_comp_days(ent, _SIGNUP_TRIAL_DAYS)
    ent.signup_trial_used = True
    await db.commit()
    return {"granted": True}


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


class CheckoutRequest(BaseModel):
    # Which billing period to subscribe to. Defaults to "annual" — the cheaper-per-month option we
    # nudge toward (and what older clients posting an empty body get).
    period: str = "annual"


@router.post("/checkout")
async def create_checkout(
    payload: CheckoutRequest | None = None,
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a Stripe Checkout Session for the Pro subscription (monthly|annual); return its hosted URL.

    Everyone gets the 90-day free trial. The founding coupon (50% off for life) is applied while the
    founding window is open; once it closes, the coupon's Stripe redeem-by lapses, so we catch the
    rejection and retry at full price rather than hard-break checkout. `founding` metadata records
    whether the coupon actually went on, which the webhook reads to stamp the seat.
    """
    period = (payload.period if payload else "annual").lower().strip()
    price_id = _price_for_period(period)
    if not settings.stripe_secret_key or not price_id:
        raise HTTPException(status_code=503, detail="billing not configured")
    ent = await _get_or_create_entitlement(db, user.email, user.uid)

    if not ent.stripe_customer_id:
        customer = await run_in_threadpool(
            stripe.Customer.create, email=user.email, metadata={"firebase_uid": user.uid}
        )
        ent.stripe_customer_id = customer.id
    await db.commit()

    base_args: dict = dict(
        mode="subscription",
        customer=ent.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.app_base_url}/design-guide?checkout=success",
        cancel_url=f"{settings.app_base_url}/pricing?checkout=cancel",
        client_reference_id=user.uid,
    )
    if settings.stripe_founding_trial_days > 0:
        base_args["subscription_data"] = {"trial_period_days": settings.stripe_founding_trial_days}

    def _create(with_founding: bool):
        # Stripe rejects a session that sets both `discounts` and `allow_promotion_codes`, so it's the
        # founding coupon OR an open promo-code box, never both.
        extra: dict = (
            {"discounts": [{"coupon": settings.stripe_founding_coupon_id}]}
            if with_founding
            else {"allow_promotion_codes": True}
        )
        return stripe.checkout.Session.create(
            **base_args,
            metadata={
                "email": user.email,
                "firebase_uid": user.uid,
                "tier": "pro",
                "period": period,
                "founding": "true" if with_founding else "false",
            },
            **extra,
        )

    want_founding = bool(settings.stripe_founding_coupon_id)
    try:
        session = await run_in_threadpool(_create, want_founding)
    except Exception as e:
        # Most likely the founding coupon lapsed (window closed). Fall back to full price so checkout
        # keeps working; re-raise if we weren't applying a coupon (then it's a real error).
        if not want_founding:
            raise
        log.warning("founding_coupon_rejected", error=str(e))
        session = await run_in_threadpool(_create, False)
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
    # "trialing" is full Pro access (the founding 90-day trial); only a dead sub drops to free.
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
            # A founding sub lands as status "trialing" during the 90-day trial; the retrieved
            # subscription below corrects this. Default to active for the rare no-subscription case.
            ent.status = "active"
            # A real paid conversion supersedes any complimentary grant — drop the comp marker so
            # the gate stops applying a comp/trial expiry to what is now a Stripe-backed seat.
            ent.comp = False
            # Stamp founding only if the coupon actually went on at checkout (metadata reflects the
            # resilient fallback above). Kept for the badge; never un-stamped on renewal.
            if meta.get("founding") == "true":
                ent.founding = True
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
