"""Event-triggered "new bill" alerts — the "something moved" trigger.

When a newly-tracked, relevant bill matches a subscriber's topics + jurisdictions, email them once so
the dashboard's return is driven by real movement, not a cadence. Distinct from the digest (periodic
roundup) and the dispatcher (status/text changes on bills already tracked).

Reuses the digest's per-subscriber matching (subscription_matches_bill) and Gazette styling. Each bill
carries a `new_bill_alert_sent` boolean; we send ONE consolidated email per subscriber covering their
newly-matched bills, and the caller marks the bills it actually emailed. Bounded to a recent
created_at window so flipping the flag on can't blast a historical backfill.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.digest import (
    _ACCENT,
    _INK,
    _INK_SOFT,
    _MUTED,
    _PAPER,
    _RULE,
    _SERIF,
    _jurisdictions_summary,
    _materials_summary,
    _merge_subs_by_email,
    _status_label,
    _topics_summary,
    subscription_matches_bill,
    topic_label,
)
from app.models import AlertSubscription, Bill

log = structlog.get_logger()


def _materials_phrase(bill: Bill) -> str:
    cats = bill.material_categories or []
    pretty = [c.replace("_", " ") for c in cats]
    if not pretty:
        return "the materials you follow"
    if len(pretty) == 1:
        return pretty[0]
    return ", ".join(pretty[:-1]) + " and " + pretty[-1]


@dataclass
class NewBillAlertContent:
    bills: list[Bill] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.bills)


async def _load_new_bills(db: AsyncSession, today: date, window_days: int) -> list[Bill]:
    """Relevant, not-yet-alerted bills first tracked within the window, newest first."""
    since = today - timedelta(days=window_days)
    rows = (
        await db.execute(
            select(Bill)
            .where(
                Bill.ce_relevant.is_(True),
                Bill.new_bill_alert_sent.is_(False),
                Bill.created_at >= since,
            )
            .order_by(Bill.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def build_new_bill_alerts(
    db: AsyncSession, today: date, window_days: int
) -> list[tuple[AlertSubscription, NewBillAlertContent]]:
    """One (subscription, content) pair per active subscriber with a newly-matched bill.

    Subscribers are deduped by email (union of scopes), mirroring the digest. Caller marks
    new_bill_alert_sent on the bills it actually emails.
    """
    bills = await _load_new_bills(db, today, window_days)

    subs = list(
        (
            await db.execute(select(AlertSubscription).where(AlertSubscription.active.is_(True)))
        ).scalars().all()
    )

    results: list[tuple[AlertSubscription, NewBillAlertContent]] = []
    for sub in _merge_subs_by_email(subs):
        matched = [b for b in bills if subscription_matches_bill(sub, b)]
        if matched:
            results.append((sub, NewBillAlertContent(bills=matched)))
    return results


# --- Rendering -----------------------------------------------------------------------------------


def render_new_bill_alert_subject(content: NewBillAlertContent) -> str:
    if content.total == 1:
        b = content.bills[0]
        return (
            f"New in {b.state} — a {topic_label(b.instrument_type).lower()} "
            f"bill affecting {_materials_phrase(b)}"
        )
    return f"{content.total} new bills on your radar"


def _new_bill_block(b: Bill) -> str:
    url = b.source_url or "#"
    action = b.last_action_date or b.status_date
    action_str = f" · first action {action.isoformat()}" if action else ""
    return f"""
    <div style="padding:14px 0;border-bottom:1px solid {_RULE};">
      <div style="font:15px {_SERIF};color:{_INK};">
        <a href="{url}" style="color:{_ACCENT};text-decoration:none;font-weight:bold;">
          {b.state} {b.bill_number or 'Bill'}</a>
        <span style="color:{_MUTED};"> just {_status_label(b.status).lower()}</span>
      </div>
      <div style="font:15px {_SERIF};color:{_INK_SOFT};margin:4px 0 8px;">{(b.title or '')[:160]}</div>
      <div style="font:13px {_SERIF};color:{_MUTED};">
        Why it's on your radar: <span style="color:{_INK_SOFT};">{topic_label(b.instrument_type)},
        covering {_materials_phrase(b)} — materials you follow.</span>
      </div>
      <div style="font:13px {_SERIF};color:{_MUTED};margin-top:4px;">
        Status: {_status_label(b.status)}{action_str}</div>
      <div style="margin-top:8px;">
        <a href="{url}" style="color:{_ACCENT};text-decoration:none;font-weight:bold;font:13px {_SERIF};">
          See the bill →</a>
      </div>
    </div>"""


def render_new_bill_alert_html(sub: AlertSubscription, content: NewBillAlertContent) -> str:
    """Render one subscriber's new-bill alert as a Gazette-styled HTML email."""
    blocks = "".join(_new_bill_block(b) for b in content.bills)
    scope = " · ".join(
        filter(None, [_topics_summary(sub), _materials_summary(sub), _jurisdictions_summary(sub)])
    )
    following = f"Following: {scope}"
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
  <div style="background:{_PAPER};padding:26px 28px 18px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      SignalScout · New Legislation
    </div>
    <h1 style="font:bold 40px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:16px 0 6px;line-height:1.05;">Battle of the Bills</h1>
    <p style="font:italic 15px {_SERIF};color:{_INK_SOFT};margin:0;">
      Something moved on the topics &amp; states you follow</p>
  </div>
  <div style="padding:14px 28px 24px;">
    {blocks}
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    {following}. Reply to this email to change your alerts or unsubscribe.
  </div>
 </div>
</body></html>
"""
