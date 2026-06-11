"""Event-triggered compliance-deadline reminders — the loss-triggered half of the alert loop.

Distinct from the digest (a periodic roundup) and the dispatcher (per-bill-change). This fires when a
compliance deadline a subscriber follows is approaching, so the reader's return is embedded in their
calendar's urgency, not just an inbox cadence.

Reuses the digest's per-subscriber matching (subscription_matches_bill / subscription_matches_federal)
and Gazette email styling. Each deadline carries a single `reminder_sent` boolean, so we send ONE
consolidated reminder per deadline once it comes within the lead window
(max of settings.deadline_reminder_days). Staged 30-then-7-day reminders would need a per-threshold
column on compliance_deadlines — left to Phase B.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.alerts.digest import (
    _ACCENT,
    _DASHBOARD_URL,
    _INK,
    _INK_SOFT,
    _MUTED,
    _PAPER,
    _RULE,
    _SERIF,
    _jurisdictions_summary,
    _matches_list,
    _merge_subs_by_email,
    _section,
    _status_label,
    _topics_summary,
    subscription_matches_bill,
    subscription_matches_federal,
    topic_label,
)
from app.models import AlertSubscription, ComplianceDeadline, FederalAction

log = structlog.get_logger()


@dataclass
class DeadlineItem:
    deadline: ComplianceDeadline
    days_until: int


@dataclass
class DeadlineAlertContent:
    items: list[DeadlineItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)


async def _load_due_deadlines(
    db: AsyncSession, today: date, lead_days: int
) -> list[ComplianceDeadline]:
    """Upcoming, not-yet-reminded deadlines inside the lead window, with their bill eager-loaded."""
    horizon = today + timedelta(days=lead_days)
    rows = (
        await db.execute(
            select(ComplianceDeadline)
            .options(selectinload(ComplianceDeadline.bill))
            .where(
                ComplianceDeadline.reminder_sent.is_(False),
                ComplianceDeadline.deadline_date >= today,
                ComplianceDeadline.deadline_date <= horizon,
            )
            .order_by(ComplianceDeadline.deadline_date.asc())
        )
    ).scalars().all()
    return list(rows)


def _deadline_matches(
    sub: AlertSubscription,
    item: DeadlineItem,
    federal_by_id: dict[int, FederalAction],
) -> bool:
    """A deadline matches a subscriber via its linked bill (topics + states + materials + confidence),
    its linked federal action, or — for a bare deadline — its jurisdiction alone."""
    d = item.deadline
    if d.bill is not None:
        return subscription_matches_bill(sub, d.bill)
    if d.federal_action_id is not None:
        action = federal_by_id.get(d.federal_action_id)
        if action is not None:
            return subscription_matches_federal(sub, action)
    return _matches_list(sub.states, d.state)


async def build_deadline_alerts(
    db: AsyncSession, today: date, lead_days: int
) -> list[tuple[AlertSubscription, DeadlineAlertContent]]:
    """One (subscription, content) pair per active subscriber with a deadline approaching in-scope.

    Subscribers are deduped by email (union of scopes), mirroring the digest. Caller is responsible
    for marking `reminder_sent` on the deadlines it actually emails (so an unmatched deadline stays
    eligible if someone subscribes before it passes the window).
    """
    deadlines = await _load_due_deadlines(db, today, lead_days)
    items = [DeadlineItem(deadline=d, days_until=(d.deadline_date - today).days) for d in deadlines]

    fed_ids = {d.federal_action_id for d in deadlines if d.federal_action_id is not None}
    federal_by_id: dict[int, FederalAction] = {}
    if fed_ids:
        rows = (
            await db.execute(select(FederalAction).where(FederalAction.id.in_(fed_ids)))
        ).scalars().all()
        federal_by_id = {a.id: a for a in rows}

    subs = list(
        (
            await db.execute(select(AlertSubscription).where(AlertSubscription.active.is_(True)))
        ).scalars().all()
    )

    results: list[tuple[AlertSubscription, DeadlineAlertContent]] = []
    for sub in _merge_subs_by_email(subs):
        matched = [it for it in items if _deadline_matches(sub, it, federal_by_id)]
        if matched:
            results.append((sub, DeadlineAlertContent(items=matched)))
    return results


# --- Rendering -----------------------------------------------------------------------------------

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _short_date(d: date) -> str:
    return f"{_MONTHS[d.month - 1]} {d.day}"


def _long_date(d: date) -> str:
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"


def _lead(days_until: int) -> str:
    """'today' / '1 day' / '47 days' — the loss-countdown."""
    if days_until <= 0:
        return "today"
    return f"{days_until} day{'s' if days_until != 1 else ''}"


def _deadline_label_plain(item: DeadlineItem) -> str:
    """Plain-text 'CA SB 54' / 'WA' label for subject lines."""
    d = item.deadline
    if d.bill is not None:
        return f"{d.bill.state} {d.bill.bill_number or 'bill'}"
    return d.state


def render_deadline_alert_subject(content: DeadlineAlertContent) -> str:
    items = sorted(content.items, key=lambda it: it.days_until)
    if content.total == 1:
        # "47 days — CA SB 54 compliance due Jul 1"  (or "Due today — …")
        it = items[0]
        d = it.deadline
        head = "Due today" if it.days_until <= 0 else _lead(it.days_until)
        return (
            f"{head} — {_deadline_label_plain(it)} {_status_label(d.deadline_type).lower()} "
            f"due {_short_date(d.deadline_date)}"
        )
    soonest = items[0].days_until
    when = "today" if soonest <= 0 else f"in {_lead(soonest)}"
    return f"{content.total} compliance deadlines approaching (soonest {when})"


def _deadline_headline_html(item: DeadlineItem) -> str:
    """'CA SB 54 · Extended Producer Responsibility' link, or state + type for a bare deadline."""
    d = item.deadline
    if d.bill is not None:
        url = d.bill.source_url or d.source_url or "#"
        label = f"{d.bill.state} {d.bill.bill_number or 'Bill'} · {topic_label(d.bill.instrument_type)}"
    else:
        url = d.source_url or "#"
        label = f"{d.state} · {_status_label(d.deadline_type)}"
    return f'<a href="{url}" style="color:{_ACCENT};text-decoration:none;font-weight:bold;">{label}</a>'


def _deadline_footer(sub: AlertSubscription) -> str:
    """'You're tracking EPR in CA. Adjust what you follow →'"""
    return (
        f"You're tracking {_topics_summary(sub)} in {_jurisdictions_summary(sub)}. "
        f'<a href="{_DASHBOARD_URL}/compliance" style="color:{_ACCENT};">Adjust what you follow →</a>'
    )


def _shell(inner: str, footer: str) -> str:
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
  <div style="background:{_PAPER};padding:26px 28px 18px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      SignalScout · Compliance Deadline Reminder
    </div>
    <h1 style="font:bold 40px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:16px 0 6px;line-height:1.05;">Battle of the Bills</h1>
    <p style="font:italic 15px {_SERIF};color:{_INK_SOFT};margin:0;">
      A deadline you're tracking is coming due</p>
  </div>
  <div style="padding:18px 28px 24px;">
    {inner}
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    {footer}
  </div>
 </div>
</body></html>
"""


def _render_single(item: DeadlineItem) -> str:
    """The loss-framed single-deadline layout: 'A compliance deadline you're tracking is N out.'"""
    d = item.deadline
    status = f" ({_status_label(d.bill.status)})" if d.bill and d.bill.status else ""
    what = (d.who_affected or d.description or (d.bill.title if d.bill else "") or "").strip()
    open_url = d.source_url or (d.bill.source_url if d.bill else None) or f"{_DASHBOARD_URL}/compliance"
    return f"""
    <p style="font:16px {_SERIF};color:{_INK};margin:0 0 14px;">
      A compliance deadline you're tracking is <strong>{_lead(item.days_until)}</strong> out.</p>
    <p style="font:16px {_SERIF};color:{_INK};margin:0 0 4px;">
      {_deadline_headline_html(item)}<span style="color:{_MUTED};">{status}</span></p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};margin:0 0 14px;">
      {(d.description or (d.bill.title if d.bill else '') or '')[:240]}</p>
    <p style="font:15px {_SERIF};color:{_INK};margin:0 0 4px;">
      <strong>Due:</strong> {_long_date(d.deadline_date)}</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};margin:0 0 18px;">
      <strong style="color:{_INK};">What it means for you:</strong> {what[:300]}</p>
    <a href="{open_url}" style="display:inline-block;background:{_ACCENT};color:#fff;text-decoration:none;
       font:bold 14px {_SERIF};padding:10px 22px;border-radius:4px;">Open the deadline →</a>"""


def render_deadline_alert_html(sub: AlertSubscription, content: DeadlineAlertContent) -> str:
    """Render one subscriber's reminder. Single deadline → the loss-framed layout; multiple →
    a Gazette list led by the soonest."""
    items = sorted(content.items, key=lambda it: it.days_until)
    if content.total == 1:
        return _shell(_render_single(items[0]), _deadline_footer(sub))

    rows = ""
    for item in items:
        d = item.deadline
        countdown_color = "#b91c1c" if item.days_until <= 7 else _MUTED
        desc = (d.description or (d.bill.title if d.bill else "") or "").strip()
        rows += f"""
      <tr>
        <td style="padding:12px 0;border-bottom:1px solid {_RULE};font:15px {_SERIF};color:{_INK};">
          {_deadline_headline_html(item)}
          <span style="color:{countdown_color};font-weight:bold;"> · due in {_lead(item.days_until)}</span><br>
          <span style="color:{_INK_SOFT};">{desc[:160]}</span><br>
          <span style="color:{_MUTED};font-size:13px;">
            {_status_label(d.deadline_type)} · {_long_date(d.deadline_date)}
            {(' · ' + d.who_affected) if d.who_affected else ''}</span>
        </td>
      </tr>"""
    inner = _section("Approaching Deadlines", rows, 0)
    return _shell(inner, _deadline_footer(sub))
