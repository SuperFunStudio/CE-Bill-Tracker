"""Trial-ending reminder — the conversion nudge for no-card comp trials.

The signup (7-day) and referral (30-day) grants give Pro access with no card on file, so they lapse
silently. This finds accounts whose comp grant expires inside the lead window and emails a "keep your
access" nudge anchored on the founding offer. Idempotent via Entitlement.trial_reminder_sent_for, so
the daily cycle sends once per trial expiry (an extended/re-granted trial re-qualifies).

Stripe's own 90-day trial is excluded (comp=False) — it's card-on-file, auto-converts, and Stripe
sends its own trial-ending email. Reuses the digest's Gazette styling. See app/scheduler/jobs.py
run_trial_reminder_cycle + scripts/send_trial_reminders.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.digest import _ACCENT, _DASHBOARD_URL, _INK, _INK_SOFT, _MUTED, _PAPER, _SERIF
from app.models import Entitlement

log = structlog.get_logger()


@dataclass
class TrialReminderItem:
    entitlement: Entitlement
    days_until: int


async def build_trial_reminders(
    db: AsyncSession, now: datetime, lead_days: int
) -> list[TrialReminderItem]:
    """Accounts on a live no-card comp trial that expires within `lead_days` and haven't been reminded
    for this expiry yet. Caller marks trial_reminder_sent_for on the ones it emails."""
    horizon = now + timedelta(days=lead_days)
    rows = (
        await db.execute(
            select(Entitlement).where(
                Entitlement.comp.is_(True),
                Entitlement.plan == "pro",
                Entitlement.email.isnot(None),
                Entitlement.current_period_end.isnot(None),
                Entitlement.current_period_end > now,
                Entitlement.current_period_end <= horizon,
            )
        )
    ).scalars().all()

    items: list[TrialReminderItem] = []
    for ent in rows:
        # Already reminded for this exact expiry → skip (a later extension moves period_end and re-qualifies).
        if ent.trial_reminder_sent_for is not None and ent.trial_reminder_sent_for == ent.current_period_end:
            continue
        days_until = max(0, (ent.current_period_end - now).days)
        items.append(TrialReminderItem(entitlement=ent, days_until=days_until))
    return items


# --- Rendering -----------------------------------------------------------------------------------

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _when(days_until: int) -> str:
    if days_until <= 0:
        return "today"
    if days_until == 1:
        return "tomorrow"
    return f"in {days_until} days"


def render_trial_reminder_subject(item: TrialReminderItem) -> str:
    return f"Your Atlas Circular Pro trial ends {_when(item.days_until)}"


def render_trial_reminder_html(item: TrialReminderItem) -> str:
    end = item.entitlement.current_period_end
    end_str = f"{_MONTHS[end.month - 1]} {end.day}" if end else "soon"
    keep = [
        "The full Upcoming Deadlines timeline — every EPR compliance date, all 50 states",
        "Personal &amp; shared watch lists with alerts",
        "The complete dynamic Design Guide",
        "CSV export of bills &amp; deadlines",
    ]
    bullets = "".join(
        f'<li style="margin:0 0 6px;">{k}</li>' for k in keep
    )
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
  <div style="background:{_PAPER};padding:26px 28px 18px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      Atlas Circular · Your Pro Trial
    </div>
    <h1 style="font:bold 40px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:16px 0 6px;line-height:1.05;">Atlas Circular</h1>
    <p style="font:italic 15px {_SERIF};color:{_INK_SOFT};margin:0;">
      Your Pro access ends {_when(item.days_until)}</p>
  </div>
  <div style="padding:20px 28px 24px;">
    <p style="font:16px {_SERIF};color:{_INK};margin:0 0 14px;">
      Your Atlas Circular <strong>Pro trial ends {_when(item.days_until)}</strong> ({end_str}). Subscribe
      now to keep:</p>
    <ul style="font:15px {_SERIF};color:{_INK_SOFT};margin:0 0 16px;padding-left:20px;">
      {bullets}
    </ul>
    <p style="font:15px {_SERIF};color:{_ACCENT};margin:0 0 18px;">
      <strong>Founding members lock in 50% off for life</strong> — but early access closes Nov 30.</p>
    <a href="{_DASHBOARD_URL}/pricing" style="display:inline-block;background:{_ACCENT};color:#fff;
       text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">
      Keep your access →</a>
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    You're getting this because your Atlas Circular Pro trial is about to end.
    <a href="{_DASHBOARD_URL}/pricing" style="color:{_ACCENT};">See plans →</a>
  </div>
 </div>
</body></html>
"""
