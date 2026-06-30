from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.unsubscribe import verify_token
from app.alerts.welcome_email import send_welcome_for_subscription
from app.database import get_db
from app.models import AlertSubscription
from app.ratelimit import limiter
from app.schemas import SubscriptionCreate, SubscriptionResponse

router = APIRouter(prefix="/subscriptions", tags=["alerts"])


def _unsubscribe_page(message: str) -> str:
    """A tiny self-contained confirmation page — the unsubscribe link is opened in a browser (GET) or
    POSTed by the mail client (one-click), so it returns HTML rather than JSON."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SignalScout — Unsubscribe</title></head>
<body style="margin:0;background:#f4f1ea;font-family:Georgia,'Times New Roman',serif;color:#1a1a2e;">
  <div style="max-width:520px;margin:64px auto;background:#fff;border:1px solid #e3ddd0;
       border-top:4px double #1a1a2e;padding:36px 32px;text-align:center;">
    <div style="font:11px Georgia;letter-spacing:0.18em;text-transform:uppercase;color:#6b6b6b;">
      SignalScout · Battle of the Bills</div>
    <p style="font-size:17px;line-height:1.6;margin:22px 0 0;">{message}</p>
    <a href="https://battleofbills.com" style="display:inline-block;margin-top:24px;color:#1a4d2e;
       text-decoration:none;font-weight:bold;">Back to the dashboard →</a>
  </div>
</body></html>"""


@router.api_route("/unsubscribe", methods=["GET", "POST"], include_in_schema=False)
async def unsubscribe(token: str = "", db: AsyncSession = Depends(get_db)):
    """One-click unsubscribe from the recurring emails. Accepts the signed token as a query param for
    both GET (link click) and POST (RFC 8058 List-Unsubscribe-Post). Idempotent."""
    sub_id = verify_token(token)
    if sub_id is None:
        return HTMLResponse(
            _unsubscribe_page("This unsubscribe link is invalid or has expired."), status_code=400
        )
    sub = (
        await db.execute(select(AlertSubscription).where(AlertSubscription.id == sub_id))
    ).scalar_one_or_none()
    if sub is None:
        return HTMLResponse(
            _unsubscribe_page("We couldn't find that subscription — it may already be removed."),
            status_code=404,
        )
    if sub.active:
        sub.active = False
        await db.commit()
    return HTMLResponse(
        _unsubscribe_page(
            "You've been unsubscribed. You won't receive further SignalScout updates at this address. "
            "Changed your mind? You can re-subscribe any time from the dashboard."
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
    if not payload.email and not payload.slack_webhook:
        raise HTTPException(status_code=422, detail="email or slack_webhook required")
    data = payload.model_dump()
    # Back-compat: a caller that still sends the flat `states` list (and no region_scope) is treated
    # as US-scoped, so legacy signup forms keep working. New clients send region_scope directly.
    if not data.get("region_scope") and data.get("states"):
        data["region_scope"] = {"US": data["states"]}
    sub = AlertSubscription(**data)
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    # Best-effort welcome email — fired after the response, in its own DB session. No-op unless
    # enable_welcome_email is set; an email subscriber with no email is filtered downstream.
    if sub.email:
        background_tasks.add_task(send_welcome_for_subscription, sub.id)
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
