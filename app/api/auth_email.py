"""Account-security email endpoints — verification + password reset, sent as Atlas Circular.

The frontend used to call the Firebase client SDK directly for both of these, which meant they went
out from `noreply@ce-bill-tracker.firebaseapp.com`: a cold, brand-misaligned sending identity, on the
two messages a user is most likely to be *waiting* for. These routes move the delivery onto our own
authenticated SendGrid domain (app/alerts/auth_emails.py) while Firebase still mints the action link.

Both endpoints degrade gracefully instead of failing closed. `sent: false` in the response is not an
error — it means we didn't deliver (flag off, SendGrid unconfigured, or the send failed) and the
caller should fall back to the Firebase SDK's own send. Losing the branded email must never mean
losing the ability to verify an address or recover an account.
"""
# NOTE: no `from __future__ import annotations` — see the note in app/api/billing.py (slowapi's
# @limiter.limit wrapper doesn't cope with stringized annotations).
import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.alerts.auth_emails import send_password_reset_email, send_verification_email
from app.api.auth import AuthedUser, get_current_user
from app.ratelimit import limiter

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])


class SentResponse(BaseModel):
    # True = a branded email went out. False = fall back to the Firebase client SDK send.
    sent: bool


class PasswordResetRequest(BaseModel):
    # Plain str, not pydantic's EmailStr — the project doesn't carry the email-validator dependency.
    # Firebase is the real validator here: an address it doesn't recognise simply yields no link.
    email: str


@router.post("/send-verification", response_model=SentResponse)
@limiter.limit("6/hour")
async def send_verification(
    request: Request,
    user: AuthedUser = Depends(get_current_user),
):
    """Send the branded 'confirm your address' email to the signed-in account.

    Authenticated on purpose: the address comes from the verified ID token, never from the request
    body, so this can't be pointed at a third party's inbox. Already-verified accounts are a no-op
    (reported as sent so the caller doesn't fall back and mail them anyway).
    """
    if user.email_verified:
        return SentResponse(sent=True)
    sent = await send_verification_email(user.email)
    return SentResponse(sent=sent)


@router.post("/send-password-reset", response_model=SentResponse)
@limiter.limit("6/hour")
async def send_password_reset(payload: PasswordResetRequest, request: Request):
    """Send the branded password-reset email. Unauthenticated by necessity — the whole point is that
    the caller can't sign in.

    Rate-limited per IP, and the response deliberately carries no signal about whether an account
    exists: an unknown address yields `sent: false`, identical to a SendGrid failure. The frontend
    treats both the same (fall back to the Firebase SDK, which is itself silent on unknown
    addresses) and shows the same "check your inbox" copy either way, so neither this endpoint nor
    the UI can be used to enumerate registered addresses.
    """
    sent = await send_password_reset_email(str(payload.email).strip().lower())
    return SentResponse(sent=sent)
