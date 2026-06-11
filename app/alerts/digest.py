"""Periodic (monthly) subscriber digest.

This is distinct from the real-time per-change alerts in dispatcher.py. The dispatcher fires one
email per alert-worthy BillChange as it happens. The *digest* is a single periodic roundup, scoped
to exactly what each subscriber signed up for (topics = instrument_types, jurisdictions = states),
summarizing the movement over a window: bill status changes, newly tracked bills, and relevant
federal actions.

Unlike the dispatcher — which only matches on states + material_categories and so ignores the
instrument_type topic every real subscriber actually picked — the digest matches on instrument_type,
which is the field the signup form collects.

build_digests() returns one (subscription, DigestContent) pair per active subscriber that has
matching movement. render_digest_html() turns one into an email body. The scheduler job
(run_digest_cycle) and scripts/send_digest.py both consume these.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertSubscription, Bill, BillChange, FederalAction

log = structlog.get_logger()

# Human labels for the instrument_type / topic slugs subscribers pick on signup.
TOPIC_LABELS = {
    "epr": "Extended Producer Responsibility",
    "right_to_repair": "Right to Repair",
    "recycled_content": "Recycled Content",
    "labeling": "Labeling / Disclosure",
    "deposit_return": "Deposit Return",
    "packaging": "Packaging",
    "single_use": "Single-Use Restrictions",
}


def topic_label(slug: str | None) -> str:
    if not slug:
        return "Other"
    return TOPIC_LABELS.get(slug, slug.replace("_", " ").title())


def _matches_list(values: list | None, candidate: str | None) -> bool:
    """A subscriber filter list matches a candidate value when the list is empty/None, contains
    the sentinel "ALL", or explicitly contains the candidate."""
    if not values or "ALL" in values:
        return True
    return candidate in values


def subscription_matches_bill(sub: AlertSubscription, bill: Bill) -> bool:
    """True if a bill falls within a subscriber's jurisdictions + topics + confidence floor."""
    if not _matches_list(sub.states, bill.state):
        return False
    if not _matches_list(sub.instrument_types, bill.instrument_type):
        return False
    # material_categories is a secondary filter: only applied when the subscriber set specific
    # materials (most signups leave it as match-all).
    mats = sub.material_categories or []
    if mats and "ALL" not in mats:
        if not any(c in mats for c in (bill.material_categories or [])):
            return False
    if (bill.confidence_score or 0) < (sub.min_confidence or 0):
        return False
    return True


def subscription_matches_federal(sub: AlertSubscription, action: FederalAction) -> bool:
    """Federal actions are national (no state) and EPR-scoped (no instrument_type). Include them for
    subscribers who follow EPR (or all topics); apply the material filter when one is set."""
    topics = sub.instrument_types or []
    if topics and "ALL" not in topics and "epr" not in topics:
        return False
    mats = sub.material_categories or []
    if mats and "ALL" not in mats:
        if not any(c in mats for c in (action.material_categories or [])):
            return False
    return True


# Cap each section so a backfill or busy month can't produce a thousand-row email. Overflow is
# surfaced as a "+N more" line linking back to the dashboard.
MAX_PER_SECTION = 25

_URGENCY_RANK = {"high": 0, "medium": 1, "low": 2}


def _bill_sort_key(b: Bill) -> tuple:
    """Surface the most actionable bills first: urgency, then confidence, then recent action."""
    action = b.last_action_date or b.status_date
    return (
        _URGENCY_RANK.get(b.urgency or "", 3),
        -(b.confidence_score or 0),
        # Sort recent action first; None sorts last.
        -(action.toordinal() if action else 0),
    )


@dataclass
class StatusChangeItem:
    bill: Bill
    old_status: str
    new_status: str
    detected_at: datetime


@dataclass
class DigestContent:
    status_changes: list[StatusChangeItem] = field(default_factory=list)
    new_bills: list[Bill] = field(default_factory=list)
    federal_actions: list[FederalAction] = field(default_factory=list)
    # How many matched items were dropped past MAX_PER_SECTION, per section.
    status_overflow: int = 0
    new_overflow: int = 0
    federal_overflow: int = 0

    @property
    def total(self) -> int:
        """Total matched items, including those past the per-section cap."""
        return (
            len(self.status_changes) + self.status_overflow
            + len(self.new_bills) + self.new_overflow
            + len(self.federal_actions) + self.federal_overflow
        )


async def _load_candidates(
    db: AsyncSession, since: datetime
) -> tuple[list[StatusChangeItem], list[Bill], list[FederalAction]]:
    """Load every candidate item in the window once, so per-subscriber filtering is in-memory."""
    # Status changes: most recent first, joined to their bill.
    change_rows = (
        await db.execute(
            select(BillChange, Bill)
            .join(Bill, Bill.id == BillChange.bill_id)
            .where(
                BillChange.change_type == "status_change",
                BillChange.detected_at >= since,
            )
            .order_by(BillChange.detected_at.desc())
        )
    ).all()
    status_changes = [
        StatusChangeItem(
            bill=bill,
            old_status=(c.old_value or {}).get("status", "unknown"),
            new_status=(c.new_value or {}).get("status", "unknown"),
            detected_at=c.detected_at,
        )
        for c, bill in change_rows
    ]

    new_bills = list(
        (
            await db.execute(
                select(Bill)
                .where(Bill.created_at >= since, Bill.epr_relevant.is_(True))
                .order_by(Bill.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    federal_actions = list(
        (
            await db.execute(
                select(FederalAction)
                .where(
                    FederalAction.published_date >= since.date(),
                    FederalAction.epr_relevant.is_(True),
                )
                .order_by(FederalAction.published_date.desc())
            )
        )
        .scalars()
        .all()
    )
    return status_changes, new_bills, federal_actions


def _union_list(lists: list[list]) -> list:
    """Union of subscriber filter lists, collapsing to the match-all sentinel ["ALL"] when any
    member is match-all (empty or contains "ALL")."""
    if any(not lst or "ALL" in lst for lst in lists):
        return ["ALL"]
    seen: list = []
    for lst in lists:
        for v in lst:
            if v not in seen:
                seen.append(v)
    return seen


def _merge_subs_by_email(subs: list[AlertSubscription]) -> list[AlertSubscription]:
    """Collapse multiple active subscriptions for the same email into one broadest-scope row, so a
    person who signed up twice gets a single digest covering the union of what they follow."""
    groups: dict[str, list[AlertSubscription]] = {}
    for sub in subs:
        if not sub.email:
            continue  # digest is email-only; Slack-only subscribers get real-time alerts already
        groups.setdefault(sub.email.lower(), []).append(sub)

    merged: list[AlertSubscription] = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        newest = max(group, key=lambda s: s.created_at)
        merged.append(
            AlertSubscription(
                email=newest.email,
                organization=newest.organization,
                states=_union_list([s.states or [] for s in group]),
                material_categories=_union_list([s.material_categories or [] for s in group]),
                instrument_types=_union_list([s.instrument_types or [] for s in group]),
                min_confidence=min((s.min_confidence or 0) for s in group),
                active=True,
            )
        )
    return merged


async def build_digests(
    db: AsyncSession, since: datetime
) -> list[tuple[AlertSubscription, DigestContent]]:
    """Build a digest for every active subscriber that has matching movement since `since`.

    Subscribers are deduped by email (union of scopes). Subscribers with no email or no matching
    items are omitted (no empty emails). Each section is capped at MAX_PER_SECTION; the overflow
    count is recorded so the email can say "+N more".
    """
    status_changes, new_bills, federal_actions = await _load_candidates(db, since)

    subs = list(
        (
            await db.execute(
                select(AlertSubscription).where(AlertSubscription.active.is_(True))
            )
        )
        .scalars()
        .all()
    )

    new_bills = sorted(new_bills, key=_bill_sort_key)

    results: list[tuple[AlertSubscription, DigestContent]] = []
    for sub in _merge_subs_by_email(subs):
        matched_status = [
            item for item in status_changes if subscription_matches_bill(sub, item.bill)
        ]
        matched_new = [b for b in new_bills if subscription_matches_bill(sub, b)]
        matched_federal = [a for a in federal_actions if subscription_matches_federal(sub, a)]

        content = DigestContent(
            status_changes=matched_status[:MAX_PER_SECTION],
            new_bills=matched_new[:MAX_PER_SECTION],
            federal_actions=matched_federal[:MAX_PER_SECTION],
            status_overflow=max(0, len(matched_status) - MAX_PER_SECTION),
            new_overflow=max(0, len(matched_new) - MAX_PER_SECTION),
            federal_overflow=max(0, len(matched_federal) - MAX_PER_SECTION),
        )
        if content.total:
            results.append((sub, content))
    return results


# --- Rendering -----------------------------------------------------------------------------------

_STATUS_LABELS = {
    "introduced": "Introduced",
    "in_committee": "In Committee",
    "passed_chamber": "Passed Chamber",
    "passed": "Passed",
    "enrolled": "Enrolled",
    "enacted": "Enacted",
    "signed": "Signed",
    "vetoed": "Vetoed",
    "failed": "Failed",
}


def _status_label(s: str | None) -> str:
    if not s:
        return "Unknown"
    return _STATUS_LABELS.get(s, s.replace("_", " ").title())


def _topics_summary(sub: AlertSubscription) -> str:
    topics = sub.instrument_types or []
    if not topics or "ALL" in topics:
        return "all policy topics"
    return ", ".join(topic_label(t) for t in topics)


def _jurisdictions_summary(sub: AlertSubscription) -> str:
    states = sub.states or []
    if not states or "ALL" in states:
        return "all jurisdictions"
    return ", ".join(states)


# Gazette palette — mirrors dashboard-next/src/app/globals.css light mode (the "Battle of the Bills"
# masthead). Email clients can't load web fonts reliably, so we use a Georgia serif stack to carry
# the New Yorker / newspaper feel the dashboard gets from `.font-serif`.
_SERIF = "Georgia, 'Times New Roman', Times, serif"
_INK = "#1a1a2e"        # --text-primary
_INK_SOFT = "#495057"   # --text-secondary
_MUTED = "#6b7280"      # --text-muted
_PAPER = "#f8f9fa"      # --bg-primary
_RULE = "#dee2e6"       # --border-default
_ACCENT = "#1e6ae9"     # --green-accent (blue in light mode)
_DASHBOARD_URL = "https://ce-bill-tracker.web.app"


def render_digest_subject(content: DigestContent, period_label: str) -> str:
    return f"Battle of the Bills — your {period_label} EPR digest ({content.total} updates)"


def _byline(b: Bill, extra: str = "") -> str:
    """A serif headline line: 'CA SB 54 · Extended Producer Responsibility'."""
    url = b.source_url or "#"
    return (
        f'<a href="{url}" style="color:{_ACCENT};text-decoration:none;font-weight:bold;">'
        f"{b.state} {b.bill_number or 'Bill'}</a>"
        f'<span style="color:{_MUTED};"> · {topic_label(b.instrument_type)}</span>{extra}'
    )


def render_digest_html(
    sub: AlertSubscription, content: DigestContent, period_label: str
) -> str:
    """Render one subscriber's digest as a Gazette-styled HTML email body."""
    sections: list[str] = []

    if content.status_changes:
        rows = ""
        for item in content.status_changes:
            b = item.bill
            stance = ""
            if b.policy_stance == "advances":
                stance = f' <span style="color:{_ACCENT};">▲ advances</span>'
            elif b.policy_stance == "weakens":
                stance = ' <span style="color:#b91c1c;">▼ weakens</span>'
            rows += f"""
      <tr>
        <td style="padding:12px 0;border-bottom:1px solid {_RULE};font:15px {_SERIF};color:{_INK};">
          {_byline(b, stance)}<br>
          <span style="color:{_INK_SOFT};">{(b.title or '')[:140]}</span><br>
          <span style="color:{_MUTED};font-size:13px;">
            {_status_label(item.old_status)} → <strong>{_status_label(item.new_status)}</strong></span>
        </td>
      </tr>"""
        sections.append(_section("Bill Status Changes", rows, content.status_overflow))

    if content.new_bills:
        rows = ""
        for b in content.new_bills:
            rows += f"""
      <tr>
        <td style="padding:12px 0;border-bottom:1px solid {_RULE};font:15px {_SERIF};color:{_INK};">
          {_byline(b)}<br>
          <span style="color:{_INK_SOFT};">{(b.title or '')[:140]}</span>
        </td>
      </tr>"""
        sections.append(_section("Newly Tracked Bills", rows, content.new_overflow))

    if content.federal_actions:
        rows = ""
        for a in content.federal_actions:
            url = a.document_url or "#"
            risk = ""
            if a.preemption_risk in ("high", "medium"):
                risk = f' <span style="color:#b91c1c;">· {a.preemption_risk} preemption risk</span>'
            rows += f"""
      <tr>
        <td style="padding:12px 0;border-bottom:1px solid {_RULE};font:15px {_SERIF};color:{_INK};">
          <a href="{url}" style="color:{_ACCENT};text-decoration:none;font-weight:bold;">
            {a.agency or 'Federal'}</a>{risk}<br>
          <span style="color:{_INK_SOFT};">{(a.title or '')[:140]}</span>
        </td>
      </tr>"""
        sections.append(_section("Federal Actions", rows, content.federal_overflow))

    body = "\n".join(sections)
    dateline = (
        f"{period_label.capitalize()} edition · {content.total} updates · "
        f"{_topics_summary(sub)} · {_jurisdictions_summary(sub)}"
    )
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
  <!-- Masthead -->
  <div style="background:{_PAPER};padding:26px 28px 18px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      SignalScout · EPR Legislative Intelligence
    </div>
    <h1 style="font:bold 40px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:16px 0 6px;line-height:1.05;">Battle of the Bills</h1>
    <p style="font:italic 15px {_SERIF};color:{_INK_SOFT};margin:0;">
      Tracking circularity-aligned legislation across the USA</p>
  </div>
  <!-- Dateline -->
  <div style="padding:9px 28px;font:italic 13px {_SERIF};color:{_MUTED};text-align:center;
       border-bottom:1px solid {_RULE};">{dateline}</div>
  <!-- Body -->
  <div style="padding:8px 28px 24px;">
    {body}
  </div>
  <!-- Colophon -->
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    You're receiving this because you subscribed to SignalScout updates.<br>
    Reply to this email to unsubscribe.
  </div>
 </div>
</body></html>
"""


def _section(heading: str, rows: str, overflow: int = 0) -> str:
    more = ""
    if overflow > 0:
        more = (
            f'\n  <p style="font:italic 13px {_SERIF};color:{_MUTED};margin:8px 0 0;">'
            f'+{overflow} more — <a href="{_DASHBOARD_URL}" style="color:{_ACCENT};">'
            "view all in the dashboard</a>.</p>"
        )
    return f"""
  <h2 style="font:bold 15px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;color:{_INK};
      border-bottom:1px solid rgba(26,26,46,0.25);padding-bottom:6px;margin:26px 0 2px;">{heading}</h2>
  <table style="width:100%;border-collapse:collapse;">{rows}
  </table>{more}"""
