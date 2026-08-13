from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.unsubscribe import CONFIRM, UNSUBSCRIBE, verify_token
from app.alerts.welcome_email import (
    send_confirmation_for_subscription,
    send_welcome_for_subscription,
)
from app.database import get_db
from app.models import AlertSubscription
from app.ratelimit import limiter
from app.schemas import SubscriptionCreate, SubscriptionResponse

router = APIRouter(prefix="/subscriptions", tags=["alerts"])


def _notice_page(message: str, title: str = "Unsubscribe") -> str:
    """A tiny self-contained result page for the emailed-link endpoints (unsubscribe, confirm). Those
    links are opened in a browser (GET) or POSTed by the mail client (one-click), so they return HTML
    rather than JSON — the reader is a person, not a caller."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>Atlas Circular — {title}</title></head>
<body style="margin:0;background:#f4f1ea;font-family:Georgia,'Times New Roman',serif;color:#1a1a2e;">
  <div style="max-width:520px;margin:64px auto;background:#fff;border:1px solid #e3ddd0;
       border-top:4px double #1a1a2e;padding:36px 32px;text-align:center;">
    <div style="font:11px Georgia;letter-spacing:0.18em;text-transform:uppercase;color:#6b6b6b;">
      Atlas Circular</div>
    <p style="font-size:17px;line-height:1.6;margin:22px 0 0;">{message}</p>
    <a href="https://www.atlascircular.com" style="display:inline-block;margin-top:24px;color:#1e6ae9;
       text-decoration:none;font-weight:bold;">Back to the dashboard →</a>
  </div>
</body></html>"""


@router.api_route("/unsubscribe", methods=["GET", "POST"], include_in_schema=False)
async def unsubscribe(token: str = "", db: AsyncSession = Depends(get_db)):
    """One-click unsubscribe from the recurring emails. Accepts the signed token as a query param for
    both GET (link click) and POST (RFC 8058 List-Unsubscribe-Post). Idempotent."""
    sub_id = verify_token(token, UNSUBSCRIBE)
    if sub_id is None:
        return HTMLResponse(
            _notice_page("This unsubscribe link is invalid or has expired."), status_code=400
        )
    sub = (
        await db.execute(select(AlertSubscription).where(AlertSubscription.id == sub_id))
    ).scalar_one_or_none()
    if sub is None:
        return HTMLResponse(
            _notice_page("We couldn't find that subscription — it may already be removed."),
            status_code=404,
        )
    if sub.active:
        # 'self_unsubscribe' — the recipient asked us to stop. Recorded because this is
        # indistinguishable from an admin mute otherwise, and they mean opposite things. See
        # migration 048.
        sub.set_active(False, source="self_unsubscribe")
        await db.commit()
    return HTMLResponse(
        _notice_page(
            "You've been unsubscribed. You won't receive further Atlas Circular updates at this address. "
            "Changed your mind? You can re-subscribe any time from the dashboard."
        )
    )


@router.api_route("/confirm", methods=["GET", "POST"], include_in_schema=False)
async def confirm_subscription(
    background_tasks: BackgroundTasks, token: str = "", db: AsyncSession = Depends(get_db)
):
    """Double opt-in: the click that proves the address belongs to the person who typed it.

    Until this runs, the row created by POST /subscriptions is inactive and confirmed_at is NULL, so
    every send path skips it. This is the ONLY thing that flips it on. Idempotent — mail clients
    prefetch links and people click twice, so a second visit re-reports success rather than
    re-sending the welcome roundup.
    """
    sub_id = verify_token(token, CONFIRM)
    if sub_id is None:
        return HTMLResponse(
            _notice_page(
                "This confirmation link is invalid or has expired. You can sign up again from the "
                "dashboard and we'll send a fresh one.",
                title="Confirm",
            ),
            status_code=400,
        )
    sub = (
        await db.execute(select(AlertSubscription).where(AlertSubscription.id == sub_id))
    ).scalar_one_or_none()
    if sub is None:
        return HTMLResponse(
            _notice_page("We couldn't find that sign-up — it may have been removed.", title="Confirm"),
            status_code=404,
        )
    if sub.confirmed_at is not None:
        # Already through the gate. Note this does NOT resurrect someone who later unsubscribed: a
        # re-click of an old confirmation link must never undo a deliberate opt-out, so the branch
        # only reports state and changes nothing.
        return HTMLResponse(
            _notice_page(
                "You're already confirmed — nothing more to do."
                if sub.active
                else "This address was confirmed previously and has since been unsubscribed. "
                "Sign up again from the dashboard if you'd like updates back.",
                title="Confirm",
            )
        )

    sub.confirmed_at = datetime.now(timezone.utc)
    sub.set_active(True)
    await db.commit()
    # The welcome roundup is what they actually signed up for — it fires HERE rather than at signup,
    # because signup is the moment we still don't know whose address this is.
    background_tasks.add_task(send_welcome_for_subscription, sub.id)
    return HTMLResponse(
        _notice_page(
            "You're confirmed. Your first briefing — a catch-up on what's moved recently in your "
            "scope — is on its way, and after that you'll only hear from us when something changes.",
            title="Confirmed",
        )
    )


@router.post("", response_model=SubscriptionResponse, status_code=201)
@limiter.limit("12/minute")
async def create_subscription(
    request: Request,
    payload: SubscriptionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Public sign-up. This endpoint is anonymous and unauthenticated, so the address in the body is
    an ASSERTION, not a fact — anyone can type anyone's address here.

    So an emailed sign-up lands inactive and unconfirmed, and the only mail it triggers is the
    confirmation ask. Nothing else can reach the address until that link is clicked, because every
    send path filters on `active`. A Slack-webhook-only subscription has no address to confirm and
    stays immediately active. See migration 049 and /subscriptions/confirm.
    """
    if not payload.email and not payload.slack_webhook:
        raise HTTPException(status_code=422, detail="email or slack_webhook required")
    data = payload.model_dump()
    # Back-compat: a caller that still sends the flat `states` list (and no region_scope) is treated
    # as US-scoped, so legacy signup forms keep working. New clients send region_scope directly.
    if not data.get("region_scope") and data.get("states"):
        data["region_scope"] = {"US": data["states"]}

    needs_confirmation = bool(payload.email)

    # Re-submitting the same address before confirming updates the pending row instead of stacking up
    # another one. Without this, the rate limiter is the only thing between a stranger and an
    # unbounded pile of rows (and confirmation emails) aimed at someone else's inbox. Deliberately
    # scoped to UNCONFIRMED rows: an address that already confirmed gets a genuinely separate
    # subscription, exactly as before.
    sub: AlertSubscription | None = None
    if needs_confirmation:
        sub = (
            await db.execute(
                select(AlertSubscription)
                .where(
                    AlertSubscription.email == payload.email,
                    AlertSubscription.scope == "filter",
                    AlertSubscription.confirmed_at.is_(None),
                )
                .order_by(AlertSubscription.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    if sub is not None:
        for key, value in data.items():
            setattr(sub, key, value)
        sub.active = False
    else:
        sub = AlertSubscription(**data)
        # Fail closed: an unconfirmed address is never mailable. `active` is set directly rather than
        # through set_active() because this row was never active — there is no deactivation to record,
        # and stamping one would misreport a brand-new sign-up as churn.
        if needs_confirmation:
            sub.active = False
        else:
            sub.confirmed_at = datetime.now(timezone.utc)
        db.add(sub)
    await db.commit()
    await db.refresh(sub)

    if needs_confirmation:
        # Fired after the response, in its own DB session. Not gated on enable_welcome_email — see
        # send_confirmation_email: a sign-up whose confirmation never sent is a row nobody can rescue.
        background_tasks.add_task(send_confirmation_for_subscription, sub.id)
    return sub


@router.delete("/{subscription_id}", status_code=204)
async def delete_subscription(subscription_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AlertSubscription).where(AlertSubscription.id == subscription_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub.active = False
    await db.commit()
