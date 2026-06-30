"""Emails for the "request access / pricing" capture: an auto-reply to the requester and a lead
notification to the team. Both are best-effort (SendGrid, fire-and-forget from a FastAPI background
task) and silently no-op without an API key. Styled to match the digest's Gazette voice.
"""
from __future__ import annotations

import structlog

from app.alerts.digest import _ACCENT, _INK, _INK_SOFT, _MUTED, _PAPER, _RULE, _SERIF
from app.config import settings

log = structlog.get_logger()

# Human labels for the tiers a visitor can request.
PLAN_LABELS = {
    "pro": "Pro",
    "team": "Team",
    "enterprise": "Enterprise / API",
    "api": "API",
    "company_impact": "Portfolio Exposure",
}


def plan_label(slug: str | None) -> str:
    if not slug:
        return "a plan"
    return PLAN_LABELS.get(slug, slug.replace("_", " ").title())


def _shell(title: str, body: str) -> str:
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:600px;margin:0 auto;background:#fff;">
  <div style="background:{_PAPER};padding:24px 28px 16px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      SignalScout · {title}
    </div>
    <h1 style="font:bold 34px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:14px 0 4px;line-height:1.05;">Battle of the Bills</h1>
  </div>
  <div style="padding:22px 28px;font:16px {_SERIF};color:{_INK};line-height:1.55;">
    {body}
  </div>
 </div>
</body></html>
"""


def render_confirmation_subject(plan: str | None) -> str:
    return f"Thanks — your Battle of the Bills {plan_label(plan)} request is in"


def render_confirmation_html(name: str | None, plan: str | None) -> str:
    greeting = f"Hi {name}," if name else "Hi there,"
    body = f"""
    <p style="margin:0 0 14px;">{greeting}</p>
    <p style="margin:0 0 14px;">
      Thanks for your interest in <strong>{plan_label(plan)}</strong> on Battle of the Bills. We've
      got your request and we'll be in touch shortly to get you set up — we're onboarding early users
      and finalizing pricing right now.</p>
    <p style="margin:0 0 14px;color:{_INK_SOFT};">
      In the meantime, the full bill explorer, map, deadline dashboard, and free email alerts are
      open to you at <a href="https://battleofbills.com" style="color:{_ACCENT};">the dashboard</a>.</p>
    <p style="margin:0;color:{_MUTED};">— The Battle of the Bills team</p>"""
    return _shell("Request received", body)


def render_notification_subject(email: str, plan: str | None) -> str:
    return f"New {plan_label(plan)} access request — {email}"


def render_notification_html(
    email: str,
    name: str | None,
    organization: str | None,
    plan: str | None,
    message: str | None,
    source: str | None,
) -> str:
    rows = [
        ("Email", email),
        ("Name", name or "—"),
        ("Organization", organization or "—"),
        ("Tier", plan_label(plan)),
        ("Source", source or "—"),
        ("Message", message or "—"),
    ]
    table = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;color:{_MUTED};white-space:nowrap;'
        f'vertical-align:top;">{k}</td>'
        f'<td style="padding:6px 0;color:{_INK};">{v}</td></tr>'
        for k, v in rows
    )
    body = f"""
    <p style="margin:0 0 14px;">A new access request just came in:</p>
    <table style="width:100%;border-collapse:collapse;font:14px {_SERIF};
        border-top:1px solid {_RULE};border-bottom:1px solid {_RULE};">{table}</table>"""
    return _shell("New lead", body)


async def send_access_request_emails(
    email: str,
    name: str | None,
    organization: str | None,
    plan: str | None,
    message: str | None,
    source: str | None,
) -> None:
    """Best-effort: auto-reply to the requester + notify the team. Never raises."""
    if not settings.sendgrid_api_key:
        log.info("access_request_emails_skipped_no_sendgrid_key", email=email)
        return
    try:
        from app.alerts.sendgrid_sender import SendGridSender

        sender = SendGridSender()
        await sender.send_html(
            email, render_confirmation_subject(plan), render_confirmation_html(name, plan)
        )
        notify = settings.access_request_notify_email
        if notify:
            await sender.send_html(
                notify,
                render_notification_subject(email, plan),
                render_notification_html(email, name, organization, plan, message, source),
            )
    except Exception as e:  # never let an email failure surface to the API caller
        log.warning("access_request_emails_failed", email=email, error=str(e))
