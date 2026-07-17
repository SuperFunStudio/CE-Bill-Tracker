"""Stripe billing — Checkout for the annual Pro seat + the webhook that flips entitlement.

Flow: the authed dashboard POSTs /billing/checkout → we ensure a Stripe customer for the user's
email, open a Checkout Session for the annual Pro price (with the founding launch offer: a first-year
coupon + a 90-day free trial), and return its URL. Stripe redirects back to the dashboard, but the
source of truth for "is this account Pro" is the webhook (/billing/webhook), which upserts the
Entitlement on checkout.session.completed + customer.subscription.* events.

Stripe's SDK is synchronous, so network calls run in a threadpool to avoid blocking the event loop.
See gating-and-monetization-plan.
"""
# NOTE: no `from __future__ import annotations` here — slowapi's @limiter.limit wrapper carries its own
# module globals, so stringized annotations on decorated routes can't be resolved by FastAPI. Keeping
# annotations eager (real objects) avoids that. PEP 604 unions (X | None) are fine at runtime on 3.10+.
import json
from datetime import datetime, timezone

import stripe
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.auth import (
    AuthedUser,
    effective_capabilities,
    get_current_user,
    get_entitlement,
    grant_comp_days,
    is_edu_email,
    is_pro,
    resolve_plan,
)
from app.config import settings
from app.database import get_db
from app.models import Entitlement
from app.ratelimit import limiter

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
        # The *resolved* plan (collapses to "free" when a paid plan isn't live), so the frontend and
        # the capabilities below always agree.
        "plan": resolve_plan(ent),
        "status": ent.status if ent else None,
        "is_pro": is_pro(ent),
        # The per-feature gate the frontend reads (mirrors app/api/auth.py PLAN_CAPS + any active
        # temporary Pro preview). Sorted for a stable payload.
        "capabilities": sorted(effective_capabilities(ent)),
        "is_trial": bool(ent and is_pro(ent) and (ent.status == "trialing" or ent.comp)),
        "is_founding": bool(ent and ent.founding),
        "current_period_end": (
            ent.current_period_end.isoformat() if ent and ent.current_period_end else None
        ),
    }


# First rung of the value ladder: a no-card taste of Pro on signup.
_SIGNUP_TRIAL_DAYS = 7


@router.post("/signup-trial")
@limiter.limit("15/hour")
async def signup_trial(
    request: Request,
    background_tasks: BackgroundTasks,
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant this account its one-time 7-day signup trial (full Pro, no card) and send the account
    welcome. Idempotent — a no-op if the trial was already used (so the welcome fires exactly once per
    new account). Called by the frontend right after a free account is created (incl. referral signups).

    Requires a verified email (H-2): a comp Pro seat now grants real data access (post C-1), so we
    don't hand it to unverified throwaway accounts. The frontend sends a verification email on
    email/password signup and retries this once the address is verified; Google sign-ins are verified
    out of the gate and get the trial immediately."""
    if not user.email_verified:
        return {"granted": False, "reason": "email_unverified"}
    ent = await _get_or_create_entitlement(db, user.email, user.uid)
    if ent.signup_trial_used:
        return {"granted": False, "reason": "already_used"}
    grant_comp_days(ent, _SIGNUP_TRIAL_DAYS)
    ent.signup_trial_used = True
    await db.commit()
    # Welcome the brand-new account (best-effort, after the response is sent).
    from app.alerts.welcome_email import send_account_welcome

    background_tasks.add_task(send_account_welcome, user.email)
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
    # Which membership to buy: "pro" (default) | "student" | "research".
    plan: str = "pro"
    # Pro only — billing period. Defaults to "annual" (the cheaper-per-month option we nudge toward,
    # and what older clients posting an empty body get).
    period: str = "annual"
    # Student only — the pay-what-you-wish choice. 0 (or negative) => a free comp membership, no Stripe.
    # >0 or None => hand off to Stripe, where the exact custom amount is entered (suggested $15).
    amount_cents: int | None = None


async def _ensure_customer(db: AsyncSession, ent: Entitlement, user: AuthedUser) -> None:
    """Make sure the entitlement has a Stripe customer, creating one on first checkout."""
    if not ent.stripe_customer_id:
        customer = await run_in_threadpool(
            stripe.Customer.create, email=user.email, metadata={"firebase_uid": user.uid}
        )
        ent.stripe_customer_id = customer.id
    await db.commit()


async def _student_checkout(payload: CheckoutRequest, user: AuthedUser, db: AsyncSession) -> dict:
    """Student tier — pay-what-you-wish, gated to a verified educational email. A $0 choice grants a
    free comp membership on the spot (no Stripe); any amount routes to Stripe's custom-amount Checkout."""
    if not (user.email_verified and is_edu_email(user.email)):
        # 403 with a clear reason so the frontend can prompt for a verified .edu address.
        raise HTTPException(status_code=403, detail="student tier requires a verified educational email")
    ent = await _get_or_create_entitlement(db, user.email, user.uid)
    amount = payload.amount_cents
    if amount is not None and amount <= 0:
        # Free student membership: indefinite comp on the student plan (no Stripe subscription). Left as
        # comp so an admin could later expire it; NULL period_end = no expiry.
        ent.plan = "student"
        ent.status = "active"
        ent.comp = True
        ent.current_period_end = None
        await db.commit()
        return {"url": f"{settings.app_base_url}/ask?welcome=student", "comp": True}
    if not settings.stripe_secret_key or not settings.stripe_student_price_id:
        raise HTTPException(status_code=503, detail="billing not configured")
    await _ensure_customer(db, ent, user)
    # The student price is configured in Stripe with custom_unit_amount enabled (floor $1, preset $15),
    # so the exact pay-what-you-wish amount is entered on Stripe's hosted screen.
    session = await run_in_threadpool(
        stripe.checkout.Session.create,
        mode="subscription",
        customer=ent.stripe_customer_id,
        line_items=[{"price": settings.stripe_student_price_id, "quantity": 1}],
        success_url=f"{settings.app_base_url}/ask?checkout=success",
        cancel_url=f"{settings.app_base_url}/pricing?checkout=cancel",
        client_reference_id=user.uid,
        metadata={"email": user.email, "firebase_uid": user.uid, "tier": "student"},
    )
    return {"url": session.url}


async def _research_checkout(user: AuthedUser, db: AsyncSession) -> dict:
    """Research (Founding Supporter) tier — a fixed annual subscription, no founding coupon/trial."""
    if not settings.stripe_secret_key or not settings.stripe_research_price_id:
        raise HTTPException(status_code=503, detail="billing not configured")
    ent = await _get_or_create_entitlement(db, user.email, user.uid)
    await _ensure_customer(db, ent, user)
    session = await run_in_threadpool(
        stripe.checkout.Session.create,
        mode="subscription",
        customer=ent.stripe_customer_id,
        line_items=[{"price": settings.stripe_research_price_id, "quantity": 1}],
        success_url=f"{settings.app_base_url}/ask?checkout=success",
        cancel_url=f"{settings.app_base_url}/pricing?checkout=cancel",
        client_reference_id=user.uid,
        metadata={"email": user.email, "firebase_uid": user.uid, "tier": "research"},
    )
    return {"url": session.url}


@router.post("/checkout")
@limiter.limit("20/hour")
async def create_checkout(
    request: Request,
    payload: CheckoutRequest | None = None,
    user: AuthedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a Checkout Session for the requested membership and return its hosted URL (or, for a $0
    student membership, grant it directly and return a success URL).

    Pro: everyone gets the 90-day free trial. The founding coupon (50% off for life) is applied while
    the founding window is open; once it closes, the coupon's Stripe redeem-by lapses, so we catch the
    rejection and retry at full price rather than hard-break checkout. `founding` metadata records
    whether the coupon actually went on, which the webhook reads to stamp the seat.
    """
    plan = (payload.plan if payload else "pro").lower().strip()
    if plan == "student":
        return await _student_checkout(payload or CheckoutRequest(), user, db)
    if plan == "research":
        return await _research_checkout(user, db)

    # Pro (default).
    period = (payload.period if payload else "annual").lower().strip()
    price_id = _price_for_period(period)
    if not settings.stripe_secret_key or not price_id:
        raise HTTPException(status_code=503, detail="billing not configured")
    ent = await _get_or_create_entitlement(db, user.email, user.uid)
    await _ensure_customer(db, ent, user)

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


def _plan_for_price(price_id: str | None) -> str:
    """Map a Stripe price id to the membership plan it grants. Unknown/blank ids fall back to "pro"
    (the historical default — no regression for the pre-tiers Pro price)."""
    mapping = {
        settings.stripe_pro_monthly_price_id: "pro",
        settings.stripe_pro_annual_price_id: "pro",
        settings.stripe_student_price_id: "student",
        settings.stripe_research_price_id: "research",
    }
    return mapping.get(price_id or "", "pro") if price_id else "pro"


def _sub_price_id(sub: dict) -> str | None:
    """The price id of a subscription's first line item, defensively across Stripe's shapes."""
    try:
        return sub["items"]["data"][0]["price"]["id"]
    except (KeyError, IndexError, TypeError):
        return None


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
    # Plan comes from which price the sub is on (student/research/pro). "trialing" is live access (the
    # founding 90-day Pro trial); only a dead sub drops to free.
    ent.plan = _plan_for_price(_sub_price_id(sub)) if status in ("active", "trialing") else "free"
    # This seat is now Stripe-backed; clear any comp marker so its period_end isn't read as a comp expiry.
    ent.comp = False
    await db.commit()


@router.post("/webhook")
@limiter.exempt  # Stripe sends bursts + retries from many IPs; signature verification is the guard here
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Stripe → us. Verifies the signature (when a signing secret is set) and upserts entitlement.

    This, not the redirect, is the source of truth for Pro access.
    """
    body = await request.body()
    sig = request.headers.get("stripe-signature")
    secret = settings.stripe_webhook_secret
    # Fail CLOSED: with no signing secret we cannot verify the event, and this endpoint grants Pro
    # entitlements — an unverified body could forge a free subscription. Reject rather than trust it.
    # See docs/SECURITY_ASSESSMENT.md C-4.
    if not secret:
        log.error("stripe_webhook_secret_unset")
        raise HTTPException(status_code=503, detail="webhook signature verification not configured")
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
            # Which membership this checkout bought — from the metadata we stamped at session creation.
            tier = (meta.get("tier") or "pro").lower().strip()
            ent.plan = tier if tier in ("pro", "student", "research") else "pro"
            # A founding sub lands as status "trialing" during the 90-day trial; the retrieved
            # subscription below corrects this. Default to active for the rare no-subscription case.
            ent.status = "active"
            # A real paid conversion supersedes any complimentary grant — drop the comp marker so
            # the gate stops applying a comp/trial expiry to what is now a Stripe-backed seat.
            ent.comp = False
            # Stamp founding only for a Pro seat where the coupon actually went on at checkout (metadata
            # reflects the resilient fallback above). Kept for the badge; never un-stamped on renewal.
            if tier == "pro" and meta.get("founding") == "true":
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
            # Confirm the purchase / welcome them to Pro (best-effort, after we ACK Stripe). Fired
            # only here, on checkout.session.completed, so renewals via subscription.* don't re-send.
            # A founding seat lands as "trialing" (billed after the 90-day trial) — flex the copy.
            # Only Pro gets the Pro-welcome copy; student/research conversions skip it (the dashboard
            # toasts their welcome) until dedicated tier emails exist.
            if tier == "pro":
                from app.alerts.welcome_email import send_pro_welcome

                background_tasks.add_task(
                    send_pro_welcome,
                    email,
                    is_trial=(ent.status == "trialing"),
                    founding=bool(ent.founding),
                )

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
            # The cancel happened in the Stripe-hosted portal, so this email is the only acknowledgement
            # the user gets. Best-effort, after we ACK Stripe.
            if ent.email:
                from app.alerts.welcome_email import send_subscription_canceled

                background_tasks.add_task(send_subscription_canceled, ent.email)

    elif etype == "invoice.payment_failed":
        # A Pro renewal card failed — warn them and point at the portal before the seat lapses to free.
        # Requires this event to be subscribed on the Stripe dashboard webhook to ever fire.
        res = await db.execute(
            select(Entitlement).where(Entitlement.stripe_customer_id == obj.get("customer"))
        )
        ent = res.scalar_one_or_none()
        email = (ent.email if ent else None) or (obj.get("customer_email") or "").lower().strip()
        if email:
            from app.alerts.welcome_email import send_payment_failed

            background_tasks.add_task(send_payment_failed, email)

    return {"received": True}
