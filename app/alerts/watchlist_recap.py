"""The recurring watch-list "you added bills" recap email.

The onboarding email (watchlist_onboarding.py) fires once, on a user's FIRST star. This is its
recurring sibling: whenever an ALREADY-ONBOARDED user adds more bills, we wait a 30-minute debounce
window (so a burst of stars collapses into one email), then send ONE recap that:

  - lists the bills they just added (since the last recap / their onboarding), linked into the app,
  - notes how many bills are now on their watch list in total, and
  - points them to My Portfolio (/company) — the watch list's home.

Idempotency: each account's "watchlist"-scope subscription carries watchlist_recap_sent_at, a
high-water mark. New adds (WatchlistItem.created_at) past COALESCE(watchlist_recap_sent_at,
onboarding_email_sent_at) are eligible; once recapped, the stamp moves to now so the same adds aren't
re-sent. build_watchlist_recap() is a pure read; the scheduler job (run_watchlist_recap_cycle) renders,
sends, and stamps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.applinks import DASHBOARD_URL, bill_url
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
from app.alerts.unsubscribe import unsubscribe_url
from app.models import AlertSubscription, Bill, WatchlistItem

log = structlog.get_logger()

# Wait this long after the most-recent add before sending, so a burst of stars batches into one email.
DEBOUNCE_MINUTES = 30
# Cap the listed bills so a power-user adding a huge batch doesn't get a thousand-row email.
MAX_BILLS = 30


@dataclass
class RecapContent:
    sub: AlertSubscription  # the "watchlist"-scope row — stamp target, unsubscribe id, recipient email
    new_bills: list[Bill] = field(default_factory=list)  # bills added since the last recap, newest first
    new_overflow: int = 0  # how many newly-added bills beyond MAX_BILLS were omitted
    total_watched: int = 0  # total bills on the watch list now (for the "now tracking N" line)


async def build_watchlist_recap(
    db: AsyncSession,
    now: datetime,
    debounce_minutes: int = DEBOUNCE_MINUTES,
) -> list[RecapContent]:
    """One (sub, content) per ALREADY-ONBOARDED account that has added bills since its last recap and
    whose most-recent add has settled past the debounce window. Pure read — the caller sends + stamps."""
    subs = (
        (
            await db.execute(
                select(AlertSubscription).where(
                    AlertSubscription.scope == "watchlist",
                    AlertSubscription.active.is_(True),
                    # Recap only AFTER onboarding handled the first batch (avoids a double email).
                    AlertSubscription.onboarding_email_sent_at.isnot(None),
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

    debounce = timedelta(minutes=debounce_minutes)
    out: list[RecapContent] = []
    for sub in subs:
        items = by_uid.get(sub.firebase_uid, [])
        if not items:
            continue
        # Adds the user hasn't been recapped on yet (since the last recap, else since onboarding).
        cutoff = sub.watchlist_recap_sent_at or sub.onboarding_email_sent_at
        new_items = [(ts, b) for ts, b in items if cutoff is None or ts > cutoff]
        if not new_items:
            continue
        # Debounce: hold until the burst settles (no new add in the last `debounce` window).
        if now - max(ts for ts, _ in new_items) < debounce:
            continue

        new_bills = [b for _, b in new_items]
        out.append(
            RecapContent(
                sub=sub,
                new_bills=new_bills[:MAX_BILLS],
                new_overflow=max(0, len(new_bills) - MAX_BILLS),
                total_watched=len(items),
            )
        )
    return out


# --- Rendering -----------------------------------------------------------------------------------

def render_recap_subject(content: RecapContent) -> str:
    n = len(content.new_bills)
    noun = "bill" if n == 1 else "bills"
    return f"You added {n} {noun} to your watch list"


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


def render_recap_text(content: RecapContent) -> str:
    """Plain-text counterpart (multipart/alternative scores better than HTML-only for deliverability)."""
    n = len(content.new_bills)
    lines = [
        f"You just added {n} {'bill' if n == 1 else 'bills'} to your watch list.",
        "",
        "We'll email you only when one of these moves (a status change or an approaching deadline):",
    ]
    for b in content.new_bills:
        lines.append(f"  • {b.state} {b.bill_number or 'Bill'} — {(b.title or '')[:120]}  {bill_url(b.id)}")
    if content.new_overflow:
        lines.append(f"  …and {content.new_overflow} more just added.")
    lines += [
        "",
        f"You're now tracking {content.total_watched} {'bill' if content.total_watched == 1 else 'bills'} in total.",
        "",
        f"See your full watch list in My Portfolio: {DASHBOARD_URL}/company",
    ]
    return "\n".join(lines)


def render_recap_html(content: RecapContent) -> str:
    bill_rows = "".join(_bill_row(b) for b in content.new_bills)
    overflow = ""
    if content.new_overflow:
        overflow = f"""
    <p style="font:14px {_SERIF};color:{_MUTED};margin:8px 0 0;">
      …and {content.new_overflow} more just added to
      <a href="{DASHBOARD_URL}/company" style="color:{_ACCENT};">My Portfolio</a>.</p>"""
    n = len(content.new_bills)
    total = content.total_watched

    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
  <div style="background:{_PAPER};padding:26px 28px 18px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      Battle of the Bills · EPR Legislative Intelligence
    </div>
    <h1 style="font:bold 38px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:16px 0 6px;line-height:1.05;">Battle of the Bills</h1>
    <p style="font:italic 15px {_SERIF};color:{_INK_SOFT};margin:0;">Added to your watch list</p>
  </div>
  <div style="padding:20px 28px 24px;">
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">
      You added {n} {'bill' if n == 1 else 'bills'} to your watch list.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 14px;">
      We'll only email you <strong>when one of these moves</strong> (a status change or an approaching
      compliance deadline). Tap any bill to open it in the dashboard.</p>
    <table style="width:100%;border-collapse:collapse;">{bill_rows}
    </table>{overflow}
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:18px 0 0;">
      You're now tracking <strong>{total} {'bill' if total == 1 else 'bills'}</strong> in total.</p>
    <div style="margin:22px 0 0;">
      <a href="{DASHBOARD_URL}/company" style="display:inline-block;background:{_ACCENT};color:#fff;
         text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">
        See your watch list in My Portfolio →</a>
    </div>
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    You're receiving this because you follow bills on Battle of the Bills.
    <br><a href="{unsubscribe_url(content.sub.id)}" style="color:{_MUTED};text-decoration:underline;">
      Unsubscribe from these alerts</a>
  </div>
 </div>
</body></html>
"""
