"""Periodic (monthly) subscriber digest.

This is distinct from the real-time per-change alerts in dispatcher.py. The dispatcher fires one
email per alert-worthy BillChange as it happens. The *digest* is a single periodic roundup, scoped
to exactly what each subscriber signed up for (topics = instrument_types, jurisdictions = states),
summarizing the movement over a window: bill status changes, newly tracked bills, and relevant
federal actions.

The digest and the dispatcher now share one matching rule (subscription_matches_bill): states +
instrument_types (topics) + material_categories + confidence floor. (The dispatcher historically
matched only states + materials, ignoring the topic every real subscriber actually picks; that was
fixed to call this same function.)

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

from app.alerts.applinks import bill_url
from app.alerts.retention import filter_retained_subscriptions
from app.alerts.unsubscribe import unsubscribe_url
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


def material_label(slug: str | None) -> str:
    # Mirrors the dashboard's material chip labels (BillFilters.tsx): title-cased slug.
    if not slug:
        return "Other"
    return slug.replace("_", " ").title()


def _matches_list(values: list | None, candidate: str | None) -> bool:
    """A subscriber filter list matches a candidate value when the list is empty/None, contains
    the sentinel "ALL", or explicitly contains the candidate."""
    if not values or "ALL" in values:
        return True
    return candidate in values


def _matches_scope(
    region_scope: dict | None, region: str | None, jurisdiction: str | None
) -> bool:
    """Region-keyed jurisdiction match (the multi-region successor to _matches_list on states).

    region_scope = {"US": ["CA","OR"], "EU": ["*"]}. Empty/None scope = match all regions +
    jurisdictions. A region key whose list is empty or contains "*"/"ALL" matches any jurisdiction
    in that region; otherwise the jurisdiction code must be listed. A bill whose region isn't a key
    at all does NOT match (so a US-only subscriber never gets EU alerts). See migration 032.
    """
    if not region_scope:
        return True
    region = region or "US"
    if region not in region_scope:
        return False
    codes = region_scope[region]
    if not codes or "*" in codes or "ALL" in codes:
        return True
    return jurisdiction in codes


def _union_scope(scopes: list[dict]) -> dict:
    """Union region-keyed scopes when merging a subscriber's rows. Any empty scope means match-all
    (everything), so the union is {}. Otherwise per region: a whole-region ("*") wins, else union codes."""
    if any(not s for s in scopes):
        return {}
    out: dict[str, list] = {}
    for s in scopes:
        for region, codes in s.items():
            if out.get(region) == ["*"]:
                continue
            if not codes or "*" in codes or "ALL" in codes:
                out[region] = ["*"]
            else:
                out[region] = sorted(set(out.get(region, [])) | set(codes))
    return out


def subscription_matches_bill(
    sub: AlertSubscription, bill: Bill, watchlist_ids: set[int] | None = None
) -> bool:
    """True if a bill is in scope for a subscriber.

    A bill is in scope if EITHER it's on the subscriber's watch list OR it passes their topic /
    jurisdiction / material filters — so one merged subscriber covers both their starred bills and
    the topics they follow (see _merge_subs_by_email). `watchlist_ids` is the owner's user_watchlist
    membership, loaded once per cycle via load_watchlists; pass it whenever the subscriber owns a
    watch list (sub.firebase_uid is set).

    A starred bill matches regardless of the filter columns and the confidence floor — if you
    followed it, you want it however the classifier scored it. A "watchlist"-scope subscriber (a
    pure watch list, with no filter intent) matches ONLY its starred bills; its empty filter columns
    are not treated as match-all.
    """
    in_watchlist = watchlist_ids is not None and bill.id in watchlist_ids
    if getattr(sub, "scope", "filter") == "watchlist":
        return in_watchlist
    if in_watchlist:
        return True

    if not _matches_scope(sub.region_scope, bill.region, bill.state):
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
    subscribers who follow EPR (or all topics); apply the material filter when one is set.

    Watch lists track individual bills, not federal actions, so a watchlist subscription never
    matches a federal action."""
    if getattr(sub, "scope", "filter") == "watchlist":
        return False
    # Federal actions are US national — only for subscribers whose scope includes the US.
    if not _matches_scope(sub.region_scope, "US", "US"):
        return False
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
                .where(Bill.created_at >= since, Bill.ce_relevant.is_(True))
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
                    FederalAction.ce_relevant.is_(True),
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


async def load_watchlists(db: AsyncSession, uids: set[str]) -> dict[str, set[int]]:
    """Map each Firebase uid to the set of bill ids it follows (its user_watchlist membership).

    Loaded once per alert cycle for the owners of watchlist subscriptions, then handed to
    subscription_matches_bill so the per-(sub, bill) check is an in-memory set lookup."""
    if not uids:
        return {}
    # Imported here to avoid a circular import at module load (models -> Base, fine, but keep
    # the alerts package's import graph shallow).
    from app.models import WatchlistItem

    rows = (
        await db.execute(
            select(WatchlistItem.firebase_uid, WatchlistItem.bill_id).where(
                WatchlistItem.firebase_uid.in_(uids)
            )
        )
    ).all()
    out: dict[str, set[int]] = {}
    for uid, bill_id in rows:
        out.setdefault(uid, set()).add(bill_id)
    return out


def _merge_subs_by_email(subs: list[AlertSubscription]) -> list[AlertSubscription]:
    """Collapse all of a person's active subscriptions (by email) into ONE subscriber, so they get a
    single email per channel covering everything they follow.

    A person can hold both a "filter" subscription (topics / jurisdictions / materials) and a
    "watchlist" subscription (specific starred bills). They are merged into one row that matches a
    bill if it's on the watch list OR it passes the filters (the OR lives in subscription_matches_bill):

      - filters present (with or without a watch list) -> one "filter"-scope row carrying the union
        of the filter columns, plus firebase_uid set to the watch-list owner (if any) so the matcher
        can OR in the starred bills. alert_on carries the watch list's notification prefs.
      - watch list only (no filters)                   -> the watchlist row, passed through unchanged.

    Subscribers with no email are dropped (digest/alerts are email-only; Slack-only subscribers get
    real-time alerts)."""
    groups: dict[str, list[AlertSubscription]] = {}
    for sub in subs:
        if not sub.email:
            continue
        groups.setdefault(sub.email.lower(), []).append(sub)

    merged: list[AlertSubscription] = []
    for group in groups.values():
        filters = [s for s in group if getattr(s, "scope", "filter") != "watchlist"]
        watches = [s for s in group if getattr(s, "scope", "filter") == "watchlist"]
        watch = watches[0] if watches else None

        if not filters:
            # Pure watch list — one row, already bill-set scoped.
            merged.append(watch)
            continue

        if len(filters) == 1 and watch is None:
            # Lone filter subscription, no watch list — pass through unchanged.
            merged.append(filters[0])
            continue

        newest = max(filters, key=lambda s: s.created_at)
        combined = AlertSubscription(
            # firebase_uid present => this subscriber owns a watch list; the matcher ORs it in and
            # the deadline channel reads alert_on to honour the watch-list deadline pref.
            firebase_uid=watch.firebase_uid if watch else None,
            scope="filter",
            email=newest.email,
            organization=newest.organization,
            states=_union_list([s.states or [] for s in filters]),
            region_scope=_union_scope([s.region_scope or {} for s in filters]),
            material_categories=_union_list([s.material_categories or [] for s in filters]),
            instrument_types=_union_list([s.instrument_types or [] for s in filters]),
            min_confidence=min((s.min_confidence or 0) for s in filters),
            alert_on=list(watch.alert_on or []) if watch else None,
            active=True,
        )
        merged.append(combined)
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

    subs = await filter_retained_subscriptions(
        db,
        list(
            (
                await db.execute(
                    select(AlertSubscription).where(AlertSubscription.active.is_(True))
                )
            )
            .scalars()
            .all()
        ),
    )

    new_bills = sorted(new_bills, key=_bill_sort_key)

    merged_subs = _merge_subs_by_email(subs)
    watchlists = await load_watchlists(
        db, {s.firebase_uid for s in merged_subs if s.firebase_uid}
    )

    results: list[tuple[AlertSubscription, DigestContent]] = []
    for sub in merged_subs:
        # Any subscriber that owns a watch list gets its starred bills OR'd into the match.
        wl = watchlists.get(sub.firebase_uid) if sub.firebase_uid else None
        matched_status = [
            item for item in status_changes if subscription_matches_bill(sub, item.bill, wl)
        ]
        matched_new = [b for b in new_bills if subscription_matches_bill(sub, b, wl)]
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
    # Pure watch list (no filters): the email is entirely about starred bills.
    if getattr(sub, "scope", "filter") == "watchlist":
        return "the bills on your watch list"
    topics = sub.instrument_types or []
    base = "all policy topics" if (not topics or "ALL" in topics) else ", ".join(
        topic_label(t) for t in topics
    )
    # A combined subscriber (owns a watch list AND topic filters) follows both.
    if getattr(sub, "firebase_uid", None):
        base += " (plus your watch list)"
    return base


def _jurisdictions_summary(sub: AlertSubscription) -> str:
    states = sub.states or []
    if not states or "ALL" in states:
        return "all jurisdictions"
    return ", ".join(states)


def _materials_summary(sub: AlertSubscription) -> str:
    """Human label for the material/product filter, or "" when unfiltered (ALL/empty).

    Returns empty so callers can omit the materials clause entirely rather than
    printing a clunky "all materials" — the topic + jurisdiction summaries already
    carry the "you're following everything" reading.
    """
    mats = sub.material_categories or []
    if not mats or "ALL" in mats:
        return ""
    return ", ".join(material_label(m) for m in mats)


# Gazette palette — mirrors dashboard-next/src/app/globals.css light mode (the "Battle of the Bills"
# masthead). Email clients can't load web fonts reliably, so we use a Georgia serif stack to carry
# the New Yorker / newspaper feel the dashboard gets from `.font-serif`.
_SERIF = "Georgia, 'Times New Roman', Times, serif"
_INK = "#1a1a2e"        # --text-primary
_INK_SOFT = "#495057"   # --text-secondary
_MUTED = "#6b7280"      # --text-muted
_PAPER = "#f8f9fa"      # --bg-primary
_RULE = "#dee2e6"       # --border-default
_ACCENT = "#1e6ae9"     # --green-accent (Atlas blue)
_DASHBOARD_URL = "https://www.atlascircular.com"


def render_digest_subject(content: DigestContent, period_label: str) -> str:
    return f"Atlas Circular — your {period_label} EPR digest ({content.total} updates)"


def _byline(b: Bill, extra: str = "") -> str:
    """A serif headline line: 'CA SB 54 · Extended Producer Responsibility'. The bill number links
    into the app (the detail panel), not the external legislature page — see applinks.bill_url."""
    return (
        f'<a href="{bill_url(b.id)}" style="color:{_ACCENT};text-decoration:none;font-weight:bold;">'
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
    scope = " · ".join(
        filter(None, [_topics_summary(sub), _materials_summary(sub), _jurisdictions_summary(sub)])
    )
    dateline = f"{period_label.capitalize()} edition · {content.total} updates · {scope}"
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
  <!-- Masthead -->
  <div style="background:{_PAPER};padding:26px 28px 18px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      Atlas Circular · EPR Legislative Intelligence
    </div>
    <h1 style="font:bold 40px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:16px 0 6px;line-height:1.05;">Atlas Circular</h1>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};margin:0;">
      Tracking sustainability across the globe</p>
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
    You're receiving this because you subscribed to Atlas Circular updates.<br>
    <a href="{unsubscribe_url(sub.id)}" style="color:{_MUTED};text-decoration:underline;">Unsubscribe</a>
    · or reply to this email.
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
