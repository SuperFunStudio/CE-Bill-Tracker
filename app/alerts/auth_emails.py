"""Account-security emails (verify address, reset password) sent through OUR SendGrid pipeline.

Firebase Auth will happily send these itself, but its mailer is a separate sending identity —
`noreply@ce-bill-tracker.firebaseapp.com`, unauthenticated against our brand domain and cold. Every
other Atlas Circular email already goes out as `hello@atlascircular.com` (SPF/DKIM/DMARC-aligned,
reputation warmed by the digest/alert cycles) wrapped in the shared masthead, so a verification mail
from a firebaseapp.com address was both the most spam-prone message we send and the one that looked
least like us — for a brand-new user, the very first impression.

So we keep Firebase as the *source of the link* and take over the delivery:

  - firebase-admin mints the real action link (generate_email_verification_link /
    generate_password_reset_link) — same one-time oobCode the built-in template would carry, so the
    /__/auth/action handler, expiry and single-use semantics are unchanged;
  - we render it in the shared shell (app/alerts/email_shell) and send it via EmailSender.

Best-effort by design: every entry point returns a bool and never raises. A False return means the
caller should fall back to the Firebase client SDK's own send (see app/api/auth_email.py), so a
SendGrid outage or a flag flip degrades to "plainer email" rather than "no way to verify an account".

NOTE: the link still points at the project's authDomain (ce-bill-tracker.firebaseapp.com/__/auth/…)
until a custom auth domain is attached in Firebase Hosting. That's cosmetic for deliverability now
that the From-domain is aligned, but worth closing — see docs/EMAIL_DELIVERABILITY.md.
"""
from __future__ import annotations

import structlog
from starlette.concurrency import run_in_threadpool

from app.alerts.email_shell import (
    DASHBOARD_URL,
    _ACCENT,
    _INK,
    _INK_SOFT,
    _MUTED,
    _SERIF,
    cta_button,
    render_shell,
)
from app.config import settings

log = structlog.get_logger()

# How long Firebase's action links stay valid. Not configurable through the Admin SDK (the project
# setting governs it) — stated in the copy so the reader knows the link is perishable.
_LINK_TTL_COPY = "This link expires in about an hour and can only be used once."


def _action_code_settings():
    """Where the user lands after completing the action, or None to use the project default.

    The continue URL's domain must be on Firebase's authorized-domains list; if it isn't, the
    Identity Toolkit rejects the whole call. `_generate_link` therefore retries without these
    settings rather than failing the send outright.
    """
    from firebase_admin import auth as fb_auth

    return fb_auth.ActionCodeSettings(url=f"{DASHBOARD_URL}/", handle_code_in_app=False)


async def _generate_link(kind: str, email: str) -> str | None:
    """Mint a Firebase action link for `email`. Returns None if Firebase won't issue one.

    Runs in a threadpool — the Admin SDK is synchronous and this call hits the Identity Toolkit API.
    """
    from app.api.auth import _ensure_firebase

    _ensure_firebase()
    from firebase_admin import auth as fb_auth

    make = (
        fb_auth.generate_email_verification_link
        if kind == "verify"
        else fb_auth.generate_password_reset_link
    )
    try:
        return await run_in_threadpool(make, email, _action_code_settings())
    except Exception as e:
        # Most likely an unauthorized continue URL. Retry with the project's default landing page
        # before giving up — a plain link still verifies the account.
        log.info("auth_link_continue_url_rejected", kind=kind, error=str(e))
        try:
            return await run_in_threadpool(make, email)
        except Exception as e2:
            # USER_NOT_FOUND lands here too (password reset for an unknown address) — expected, and
            # deliberately invisible to the caller so the API can't be used to enumerate accounts.
            log.info("auth_link_generation_failed", kind=kind, error=str(e2))
            return None


# --- Rendering -------------------------------------------------------------------------------------


def _para(text: str) -> str:
    return (
        f'<p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">{text}</p>'
    )


def _fine_print(text: str) -> str:
    """Small grey note under the CTA. Own top margin — it follows the button, which has none."""
    return (
        f'<p style="font:14px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">{text}</p>'
    )


def _fallback_link(link: str) -> str:
    """The raw URL, for clients that strip the button. Wrapped so a long link can't blow out the
    layout on mobile."""
    return f"""
    <p style="font:13px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">
      If the button doesn't work, paste this into your browser:<br>
      <a href="{link}" style="color:{_ACCENT};word-break:break-all;">{link}</a></p>"""


def render_verify_subject() -> str:
    return "Confirm your email to activate your account"


def render_verify_html(link: str) -> str:
    inner = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 12px;font-weight:bold;">
      One click and you're in.</p>
    {_para("Confirm this address to activate your <strong>Atlas Circular</strong> account and start "
           "your 7-day Pro trial — the full deadlines timeline, watch lists, the Design Guide and "
           "CSV export, no card required.")}
    {cta_button(link, "Confirm my email →")}
    {_fine_print(f"{_LINK_TTL_COPY} If you didn't create an Atlas Circular account, you can ignore "
                 "this email — nothing will happen until the link is used.")}
    {_fallback_link(link)}"""
    return render_shell(
        inner,
        # No unsubscribe/subscribe footer: this is transactional, and there's nothing to opt out of.
        preheader="Confirm your address to activate your account and start your 7-day Pro trial.",
        colophon="You're receiving this because this address was used to create an Atlas Circular account.",
    )


def render_reset_subject() -> str:
    return "Reset your password"


def render_reset_html(link: str) -> str:
    inner = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 12px;font-weight:bold;">
      Let's get you back in.</p>
    {_para("Someone — hopefully you — asked to reset the password on this <strong>Atlas Circular"
           "</strong> account. Choose a new one here:")}
    {cta_button(link, "Set a new password →")}
    {_fine_print(f"{_LINK_TTL_COPY} If you didn't request this, no action is needed — your current "
                 "password still works and nobody can change it without this link.")}
    {_fallback_link(link)}"""
    return render_shell(
        inner,
        preheader="Set a new password — the link works once and expires in about an hour.",
        colophon="You're receiving this because a password reset was requested for this address.",
    )


# --- Sending ---------------------------------------------------------------------------------------


async def _send(kind: str, email: str) -> bool:
    """Generate the action link and deliver it as an Atlas Circular email. Never raises.

    False means "we didn't send" — the caller should fall back to Firebase's own mailer.
    """
    if not settings.enable_auth_emails:
        log.info("auth_email_skipped_flag_off", kind=kind, email=email)
        return False
    if not email or not settings.email_configured:
        log.info("auth_email_skipped_unconfigured", kind=kind)
        return False
    try:
        link = await _generate_link(kind, email)
        if not link:
            return False
        from app.alerts.email_sender import EmailSender

        if kind == "verify":
            subject, html = render_verify_subject(), render_verify_html(link)
        else:
            subject, html = render_reset_subject(), render_reset_html(link)
        # No List-Unsubscribe header here, unlike the digest/alert cycles: these are strictly
        # transactional account-security messages, not bulk mail you can opt out of.
        ok = await EmailSender().send_html(email, subject, html)
        log.info("auth_email_sent", kind=kind, email=email, ok=ok)
        return ok
    except Exception as e:
        log.warning("auth_email_failed", kind=kind, email=email, error=str(e))
        return False


async def send_verification_email(email: str) -> bool:
    """Branded 'confirm your address' email. False → caller falls back to the Firebase SDK send."""
    return await _send("verify", email)


async def send_password_reset_email(email: str) -> bool:
    """Branded password-reset email. False → caller falls back to the Firebase SDK send.

    Returns False for an address with no account (Firebase won't mint a link); callers must NOT
    reflect that distinction back to the client — see app/api/auth_email.py.
    """
    return await _send("reset", email)
