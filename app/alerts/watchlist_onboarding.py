"""The one-time watch-list onboarding email.

When a Pro (or trialing) user stars their first bill, we don't email immediately — we wait a debounce
window (~1h) so a burst of stars collapses into a single email, then send ONE message that:

  - lists every bill currently on their watch list (linked into the app),
  - bundles in any topics / jurisdictions they follow (their "filter" subscriptions), so the separate
    subscription-welcome email isn't a second confusing "Welcome to…" in their inbox,
  - explains the cadence: future emails only come when a bill they follow actually moves, and
  - sets the Pro expectation: the dashboard features lock when the trial ends, but the alert emails
    they subscribed to keep arriving for a full year (the retention promise enforced in
    alerts/retention.py).

build_watchlist_onboarding() returns one (subscription, content) pair per eligible account; the
scheduler job (run_watchlist_onboarding_cycle) renders + sends them and stamps
onboarding_email_sent_at so each account is onboarded exactly once.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.applinks import DASHBOARD_URL, bill_url, state_url
from app.alerts.digest import (
    _ACCENT,
    _INK,
    _INK_SOFT,
    _MUTED,
    _PAPER,
    _RULE,
    _SERIF,
    topic_label,
)
from app.alerts.retention import ALERT_RETENTION_DAYS
from app.alerts.unsubscribe import unsubscribe_url
from app.models import AlertSubscription, Bill, WatchlistItem

log = structlog.get_logger()

# Wait this long after the FIRST star before sending, so a burst of stars batches into one email.
DEBOUNCE_MINUTES = 60
# Don't onboard watch lists whose first star is older than this — guards against a one-time blast to
# everyone who already had a watch list when this feature shipped (they've long since found it).
MAX_LOOKBACK_DAYS = 14
# Cap the bill list so a power-user with a huge watch list doesn't get a thousand-row email.
MAX_BILLS = 30


@dataclass
class OnboardingContent:
    sub: AlertSubscription  # the "watchlist"-scope row — stamp target, unsubscribe id, recipient email
    bills: list[Bill]  # watched bills, newest-starred first
    bill_overflow: int = 0  # how many watched bills beyond MAX_BILLS were omitted
    topics: list[str] = field(default_factory=list)  # followed instrument_type slugs (from filters)
    states: list[str] = field(default_factory=list)  # followed state codes (from filters)
    retention_until: datetime | None = None  # first-star + ALERT_RETENTION_DAYS, for the copy


async def build_watchlist_onboarding(
    db: AsyncSession,
    now: datetime,
    debounce_minutes: int = DEBOUNCE_MINUTES,
    max_lookback_days: int = MAX_LOOKBACK_DAYS,
) -> list[OnboardingContent]:
    """One (sub, content) per account whose first star is between debounce and max_lookback old and
    that hasn't been onboarded yet. Pure read — the caller sends and stamps onboarding_email_sent_at."""
    subs = (
        (
            await db.execute(
                select(AlertSubscription).where(
                    AlertSubscription.scope == "watchlist",
                    AlertSubscription.active.is_(True),
                    AlertSubscription.onboarding_email_sent_at.is_(None),
                    AlertSubscription.email.isnot(None),
                    AlertSubscription.firebase_uid.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not subs:
        return []

    uids = [s.firebase_uid for s in subs]
    # Pull every watched bill for these owners in one query, newest star first.
    rows = (
        await db.execute(
            select(WatchlistItem.firebase_uid, WatchlistItem.created_at, Bill)
            .join(Bill, Bill.id == WatchlistItem.bill_id)
            .where(WatchlistItem.firebase_uid.in_(uids))
            .order_by(WatchlistItem.created_at.desc())
        )
    ).all()
    by_uid: dict[str, list[tuple[datetime, Bill]]] = {}
    for uid, created_at, bill in rows:
        by_uid.setdefault(uid, []).append((created_at, bill))

    # Bundle in the topics/states each owner follows via their "filter" subscriptions (matched by the
    # same email — the public subscribe flow doesn't always carry a uid).
    emails = {s.email.lower() for s in subs if s.email}
    filter_subs = (
        (
            await db.execute(
                select(AlertSubscription).where(
                    AlertSubscription.scope != "watchlist",
                    AlertSubscription.active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    filters_by_email: dict[str, list[AlertSubscription]] = {}
    for fs in filter_subs:
        if fs.email and fs.email.lower() in emails:
            filters_by_email.setdefault(fs.email.lower(), []).append(fs)

    debounce = timedelta(minutes=debounce_minutes)
    lookback = timedelta(days=max_lookback_days)
    out: list[OnboardingContent] = []
    for sub in subs:
        starred = by_uid.get(sub.firebase_uid, [])
        if not starred:
            continue  # subscription exists but every starred bill was removed — nothing to onboard
        first_star = min(ts for ts, _ in starred)
        age = now - first_star
        if age < debounce or age > lookback:
            continue  # too soon to batch, or too old (pre-feature) to bother

        bills = [b for _, b in starred]
        owner_filters = filters_by_email.get((sub.email or "").lower(), [])
        topics: list[str] = []
        states: list[str] = []
        for fs in owner_filters:
            for t in fs.instrument_types or []:
                if t and t != "ALL" and t not in topics:
                    topics.append(t)
            for st in fs.states or []:
                if st and st != "ALL" and st not in states:
                    states.append(st)

        out.append(
            OnboardingContent(
                sub=sub,
                bills=bills[:MAX_BILLS],
                bill_overflow=max(0, len(bills) - MAX_BILLS),
                topics=topics,
                states=states,
                retention_until=first_star + timedelta(days=ALERT_RETENTION_DAYS),
            )
        )
    return out


# --- Rendering -----------------------------------------------------------------------------------

_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}


def render_onboarding_subject(content: OnboardingContent) -> str:
    n = len(content.bills)
    noun = "bill" if n == 1 else "bills"
    return f"You're tracking {n} {noun} — here's how your alerts work"


def _bill_row(b: Bill) -> str:
    return f"""
      <tr>
        <td style="padding:11px 0;border-bottom:1px solid {_RULE};font:15px {_SERIF};color:{_INK};">
          <a href="{bill_url(b.id)}" style="color:{_ACCENT};text-decoration:none;font-weight:bold;">
            {b.state} {b.bill_number or 'Bill'}</a>
          <span style="color:{_MUTED};"> · {topic_label(b.instrument_type)}</span><br>
          <span style="color:{_INK_SOFT};">{(b.title or '')[:140]}</span>
        </td>
      </tr>"""


def _state_chip(code: str) -> str:
    url = state_url(code)
    name = _STATE_NAMES.get(code.upper(), code.upper())
    if not url:
        return name
    return f'<a href="{url}" style="color:{_ACCENT};text-decoration:none;">{name}</a>'


def render_onboarding_text(content: OnboardingContent) -> str:
    """Plain-text counterpart (deliverability — a multipart/alternative scores better than HTML-only)."""
    lines = [
        "Welcome to your Atlas Circular watch list.",
        "",
        "You're now tracking these bills — we'll email you only when one of them moves:",
    ]
    for b in content.bills:
        lines.append(f"  • {b.state} {b.bill_number or 'Bill'} — {(b.title or '')[:120]}  {bill_url(b.id)}")
    if content.bill_overflow:
        lines.append(f"  …and {content.bill_overflow} more on your watch list.")
    if content.topics or content.states:
        topic_str = ", ".join(topic_label(t) for t in content.topics) or "all topics"
        state_str = ", ".join(_STATE_NAMES.get(s.upper(), s.upper()) for s in content.states) or "all states"
        lines += ["", f"You also follow: {topic_str} in {state_str}."]
    lines += [
        "",
        "These are Pro features. When your 7-day trial ends the dashboard tools lock, but the alert",
        "emails you subscribed to keep arriving for a full year. Keep Pro to retain full access:",
        f"  {DASHBOARD_URL}/pricing",
        "",
        f"Open your watch list: {DASHBOARD_URL}/company",
    ]
    return "\n".join(lines)


def render_onboarding_html(content: OnboardingContent) -> str:
    bill_rows = "".join(_bill_row(b) for b in content.bills)
    overflow = ""
    if content.bill_overflow:
        overflow = f"""
    <p style="font:14px {_SERIF};color:{_MUTED};margin:8px 0 0;">
      …and {content.bill_overflow} more on
      <a href="{DASHBOARD_URL}/company" style="color:{_ACCENT};">your watch list</a>.</p>"""

    follows = ""
    if content.topics or content.states:
        topic_str = ", ".join(topic_label(t) for t in content.topics) or "every topic"
        if content.states:
            state_str = ", ".join(_state_chip(s) for s in content.states)
        else:
            state_str = "all 50 states"
        follows = f"""
    <h2 style="font:bold 14px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;color:{_INK};
        border-bottom:1px solid rgba(26,26,46,0.25);padding-bottom:6px;margin:26px 0 8px;">
      You also follow</h2>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0;">
      <strong>{topic_str}</strong> in {state_str} — you'll get these updates in the same alerts.</p>"""

    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
  <div style="background:{_PAPER};padding:26px 28px 18px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      Atlas Circular · EPR Legislative Intelligence
    </div>
    <h1 style="font:bold 38px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:16px 0 6px;line-height:1.05;">Atlas Circular</h1>
    <p style="font:italic 15px {_SERIF};color:{_INK_SOFT};margin:0;">Your watch list is live</p>
  </div>
  <div style="padding:20px 28px 24px;">
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">
      You're now tracking {len(content.bills)} {'bill' if len(content.bills) == 1 else 'bills'}.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 14px;">
      We won't fill your inbox — you'll only hear from us <strong>when one of these bills actually
      moves</strong> (a status change or an approaching compliance deadline). Tap any bill to open it
      in the dashboard.</p>
    <table style="width:100%;border-collapse:collapse;">{bill_rows}
    </table>{overflow}
    {follows}
    <div style="background:{_PAPER};border:1px solid {_RULE};border-radius:6px;padding:14px 16px;margin:24px 0 18px;">
      <p style="font:14px {_SERIF};color:{_INK};line-height:1.6;margin:0;">
        <strong>Watch lists and alerts are Pro features.</strong> When your 7-day Pro trial ends the
        dashboard tools lock — but the alerts you set up keep emailing you for a
        <strong>full year</strong>, so you won't miss a deadline while you decide. Keep Pro to retain
        the full dashboard.</p>
    </div>
    <a href="{DASHBOARD_URL}/company" style="display:inline-block;background:{_ACCENT};color:#fff;
       text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">
      Open your watch list →</a>
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    You're receiving this because you started a watch list on Atlas Circular.
    <br><a href="{unsubscribe_url(content.sub.id)}" style="color:{_MUTED};text-decoration:underline;">
      Unsubscribe from these alerts</a>
  </div>
 </div>
</body></html>
"""
