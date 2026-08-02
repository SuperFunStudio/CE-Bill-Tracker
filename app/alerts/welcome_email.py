"""One-time welcome email sent when someone subscribes.

Distinct from both the real-time per-change alerts (dispatcher.py) and the periodic digest
(digest.py). This is the subscriber's *catch-up roundup*: "here's what has actually moved in your
scope recently" — a 6-month window on movement-tracked sources (US, Brazil, …) and 12 months on
year-only foreign sources — so the first thing they get orients them on recent activity without an
empty inbox, and without surfacing laws enacted years ago as if they were news. After this one
roundup the ongoing cadence takes over (new-bill alerts + status-change dispatch, both gated to
genuinely recent action). Bills with no date at all can't be windowed, so they ride along in a small
"also on the books" aside rather than being dropped or mislabelled as recent.

Two layers:
  - Structured roundup (build_state_of_play): deterministic, windowed counts pulled straight from the
    DB — what was enacted vs. what's advancing recently, broken out by jurisdiction and topic, plus
    the recently-enacted / moving-now bill lists and the undated aside.
  - An optional one-paragraph recap (render_recap_paragraph): Claude writing the roundup up in a
    momentum-aware correspondent's voice, on-brand with the "Atlas Circular" masthead. Flag-gated
    (enable_welcome_recap) and best-effort — the email renders fine without it. The prose is anchored
    to the structured counts so it can't drift far from the numbers (classifier noise can still leak
    a mis-tagged bill into the list, same caveat as the digest).

send_welcome_email() is best-effort and gated on enable_welcome_email; the API fires it from a
background task on signup, and scripts/send_welcome.py previews/sends it manually.
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
    _bill_sort_key,
    _jurisdictions_summary,
    _materials_summary,
    _status_label,
    _topics_summary,
    subscription_matches_bill,
    topic_label,
)
from app.alerts.applinks import bill_url
from app.alerts.email_shell import cta_button, render_shell
from app.alerts.unsubscribe import unsubscribe_url
from app.config import settings
from app.models import AlertSubscription, Bill

log = structlog.get_logger()

_DASHBOARD_URL = "https://www.atlascircular.com"

# Status buckets. "Enacted" = signed into law; "dead" = no longer moving; everything else in between
# is "active". Mirrors the enacted/pending split in /bills/map-summary.
_ENACTED_STATUSES = {"enacted", "signed"}
_DEAD_STATUSES = {"failed", "vetoed"}

# Roundup windows — how far back an *action* can be and still count as "recent activity". Two windows
# because our sources date bills differently:
#   - Movement-tracked sources (US LegiScan/OpenStates, Brazil, …) stamp a real last_action_date on
#     every step, so 6 months of that is a genuine activity feed.
#   - Year-only foreign sources (EUR-Lex/CELLAR and most non-US adapters) carry only a Jan-1,
#     year-granular status_date and no last_action_date, so a 6-month cut would drop most of a year's
#     corpus on an accident of granularity. 12 months keeps the current legislative year visible.
# A bill with NO date at all can't be windowed — it goes to the "also on the books" aside instead of
# being silently dropped or masqueraded as recent (the same fail-closed stance as the new-bill alert
# gate in alerts/new_bill_alerts.py).
RECENT_WINDOW_DAYS = 183       # ~6 months, for bills with a real last_action_date
YEARONLY_WINDOW_DAYS = 365     # 12 months, for year-only foreign bills (status_date only)

# Keep every list to a digestible handful.
_MAX_RECENT = 6
_MAX_ON_THE_BOOKS = 8
_MAX_ESTABLISHED = 5
_MAX_STANDING_ROWS = 8


def _is_enacted(b: Bill) -> bool:
    return (b.status or "") in _ENACTED_STATUSES


def _is_dead(b: Bill) -> bool:
    return (b.status or "") in _DEAD_STATUSES


def _is_active(b: Bill) -> bool:
    return not _is_enacted(b) and not _is_dead(b)


def _action_window(b: Bill) -> tuple[date, int] | None:
    """(action_date, window_days) for windowing this bill, or None if it carries no date at all.

    A real last_action_date marks a movement-tracked source (6-month window); a bare status_date is a
    year-only foreign stamp (12-month window). No date → not windowable → caller routes it to the
    'on the books' aside."""
    if b.last_action_date:
        return b.last_action_date, RECENT_WINDOW_DAYS
    if b.status_date:
        return b.status_date, YEARONLY_WINDOW_DAYS
    return None


@dataclass
class StandingRow:
    """Enacted vs. active tally for one jurisdiction (or topic), over the roundup window."""
    label: str
    enacted: int = 0
    active: int = 0

    @property
    def total(self) -> int:
        return self.enacted + self.active


@dataclass
class StateOfPlay:
    """Windowed activity roundup for one subscriber's scope — what MOVED recently, not all-time
    standings. `recent_*` cover the 6/12-month windows; `on_the_books` holds undated in-scope bills;
    `established` is an orientation fallback shown only when nothing moved recently."""
    scope_total: int = 0            # every in-scope bill, for the empty-state copy
    enacted_recent: int = 0         # enacted within window
    active_recent: int = 0          # non-enacted movement within window
    by_state: list[StandingRow] = field(default_factory=list)  # windowed
    by_topic: list[StandingRow] = field(default_factory=list)  # windowed
    recent_enacted: list[Bill] = field(default_factory=list)   # enacted in window, newest action first
    recent_movement: list[Bill] = field(default_factory=list)  # other in-window movement, newest first
    on_the_books: list[Bill] = field(default_factory=list)     # undated in-scope bills (aside)
    on_the_books_total: int = 0     # for the overflow count
    established: list[Bill] = field(default_factory=list)       # fallback when nothing moved recently

    @property
    def total_recent(self) -> int:
        return self.enacted_recent + self.active_recent

    @property
    def has_recent(self) -> bool:
        return self.total_recent > 0

    @property
    def has_content(self) -> bool:
        return self.has_recent or bool(self.on_the_books) or bool(self.established)


def _recent_action_key(b: Bill):
    """Most recent action first; bills with no date sort last."""
    action = b.last_action_date or b.status_date
    return -(action.toordinal() if action else 0)


async def build_state_of_play(
    db: AsyncSession, sub: AlertSubscription, today: date | None = None
) -> StateOfPlay:
    """Build the windowed activity roundup of EPR-relevant bills within a subscriber's scope.

    This is the first thing a new subscriber receives, so it's a *roundup of recent movement* — the
    last 6 months (12 for year-only foreign sources; see RECENT_WINDOW_DAYS / YEARONLY_WINDOW_DAYS) —
    NOT an all-time standings dump that would surface laws enacted years ago as if they were news.
    Bills are loaded once and filtered in memory with the same subscription_matches_bill() the digest
    uses, so scope semantics stay identical. `today` defaults to date.today() (injectable for tests)."""
    ref_day = today or date.today()
    bills = list(
        (
            await db.execute(
                select(Bill).where(Bill.ce_relevant.is_(True))
            )
        )
        .scalars()
        .all()
    )
    matched = [b for b in bills if subscription_matches_bill(sub, b)]

    sop = StateOfPlay(scope_total=len(matched))
    if not matched:
        return sop

    state_rows: dict[str, StandingRow] = {}
    topic_rows: dict[str, StandingRow] = {}
    dated_out_of_window: list[Bill] = []  # dated, but older than its window — orientation fallback only
    for b in matched:
        win = _action_window(b)
        if win is None:
            sop.on_the_books.append(b)  # no date → can't window → aside
            continue
        action_date, window_days = win
        if (ref_day - action_date).days > window_days:
            dated_out_of_window.append(b)
            continue

        # Recent movement within the applicable window.
        enacted = _is_enacted(b)
        if enacted:
            sop.enacted_recent += 1
            sop.recent_enacted.append(b)
        else:
            sop.active_recent += 1
            sop.recent_movement.append(b)  # active or freshly-dead; the row shows the status

        srow = state_rows.setdefault(b.state, StandingRow(label=b.state))
        trow = topic_rows.setdefault(
            b.instrument_type or "other", StandingRow(label=topic_label(b.instrument_type))
        )
        for row in (srow, trow):
            if enacted:
                row.enacted += 1
            else:
                row.active += 1

    sop.by_state = sorted(state_rows.values(), key=lambda r: (-r.total, r.label))[:_MAX_STANDING_ROWS]
    sop.by_topic = sorted(topic_rows.values(), key=lambda r: (-r.total, r.label))[:_MAX_STANDING_ROWS]
    sop.recent_enacted.sort(key=_recent_action_key)
    sop.recent_movement.sort(key=_recent_action_key)
    sop.recent_enacted = sop.recent_enacted[:_MAX_RECENT]
    sop.recent_movement = sop.recent_movement[:_MAX_RECENT]

    sop.on_the_books_total = len(sop.on_the_books)
    sop.on_the_books = sorted(sop.on_the_books, key=_bill_sort_key)[:_MAX_ON_THE_BOOKS]

    # Orientation fallback: if nothing moved in-window, a mature scope (e.g. a state whose landmark
    # law passed years ago) would otherwise get a near-empty email. Show a few enacted-ever laws so
    # the subscriber still lands somewhere — clearly framed as established, not as fresh movement.
    if not sop.has_recent:
        sop.established = sorted(
            (b for b in dated_out_of_window if _is_enacted(b)), key=_bill_sort_key
        )[:_MAX_ESTABLISHED]
    return sop


# --- LLM recap paragraph -------------------------------------------------------------------------

RECAP_MODEL = "claude-sonnet-4-6"

_RECAP_SYSTEM = """\
You are the correspondent for "Atlas Circular", a publication covering circular-economy and Extended \
Producer Responsibility (EPR) legislation worldwide. The through-line: these laws are how \
jurisdictions build an economy that uses materials and resources efficiently and lets a regenerative \
ecosystem stand — because without that ecosystem there is no economy at all. Every EPR law and every \
right-to-repair win is progress toward that; a veto or a dead bill is ground lost.

Write a vivid, momentum-aware recap of the RECENT ACTIVITY (roughly the last six months) for a new \
subscriber. Be BRIEF: TWO short paragraphs, roughly 90-140 words total.

  1. Open on what's moved lately — who's enacting or advancing the biggest laws and where the \
momentum is — and keep sight of why these bills matter: a more efficient, regenerative economy.
  2. Name one or two measures still in play worth watching, and close on the stakes — what's still \
undecided and why this reader will want to follow it.

Be evocative but DISCIPLINED: every factual claim — every jurisdiction, count, bill name, or status — \
must come straight from the recent-activity roundup you are given. This is a window of recent movement, \
so do NOT imply it is the complete history of these jurisdictions. Do NOT invent bill numbers, vote tallies, dates, \
sponsors, or outcomes, and do not imply a bill passed or failed unless its status says so. Let the \
framing carry through one or two sharp lines, not every sentence. Separate paragraphs with a blank \
line. No markdown, no headings, no lists, no preamble — just the prose.\
"""


def _recap_user_prompt(sub: AlertSubscription, sop: StateOfPlay) -> str:
    mats = _materials_summary(sub)
    mats_part = f" Materials/products: {mats}." if mats else ""
    scope = (
        f"Topics followed: {_topics_summary(sub)}.{mats_part} "
        f"Jurisdictions: {_jurisdictions_summary(sub)}."
    )
    standings = "; ".join(
        f"{r.label}: {r.enacted} enacted / {r.active} active" for r in sop.by_state
    ) or "no jurisdiction breakdown"
    enacted_recent = "\n".join(
        f"  - {b.state} {b.bill_number or 'bill'} ({_status_label(b.status)}): {(b.title or '')[:100]}"
        for b in sop.recent_enacted
    ) or "  (nothing enacted in this window)"
    moving = "\n".join(
        f"  - {b.state} {b.bill_number or 'bill'} ({_status_label(b.status)}): {(b.title or '')[:100]}"
        for b in sop.recent_movement
    ) or "  (nothing currently moving)"
    return f"""\
{scope}

Recent activity (last ~6 months; 12 for year-only foreign sources): {sop.enacted_recent} law(s) \
enacted and {sop.active_recent} bill(s) advancing across {len(sop.by_state)} jurisdiction(s) the \
reader follows.

Recent activity by state (enacted / advancing, within the window):
{standings}

Recently enacted:
{enacted_recent}

Moving now:
{moving}

Write the recap paragraph now."""


async def render_recap_paragraph(sub: AlertSubscription, sop: StateOfPlay) -> str | None:
    """Optional flourish: a one-paragraph momentum-aware recap of the standings. Returns None if
    disabled, unconfigured, the snapshot is empty, or the call fails — callers render without it."""
    if not settings.enable_welcome_recap or not settings.anthropic_api_key or not sop.has_recent:
        return None
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model=RECAP_MODEL,
            max_tokens=700,
            temperature=0.7,
            system=_RECAP_SYSTEM,
            messages=[{"role": "user", "content": _recap_user_prompt(sub, sop)}],
        )
        text = resp.content[0].text.strip()
        return text or None
    except Exception as e:  # never let the flourish break the welcome email
        log.warning("welcome_recap_failed", email=sub.email, error=str(e))
        return None


# --- Rendering -----------------------------------------------------------------------------------


def render_welcome_subject(sub: AlertSubscription) -> str:
    # Deliberately NOT "Welcome to…" — the account-signup email owns that, and two near-identical
    # "Welcome to Atlas Circular" subjects in one inbox read as a confusing duplicate.
    return "Your Atlas Circular alerts are live — recent activity in your scope"


def _bill_line(b: Bill, badge: str = "") -> str:
    url = bill_url(b.id)  # open the in-app detail panel rather than the external legislature page
    return f"""
      <tr>
        <td style="padding:11px 0;border-bottom:1px solid {_RULE};font:15px {_SERIF};color:{_INK};">
          <a href="{url}" style="color:{_ACCENT};text-decoration:none;font-weight:bold;">
            {b.state} {b.bill_number or 'Bill'}</a>
          <span style="color:{_MUTED};"> · {topic_label(b.instrument_type)}</span>{badge}<br>
          <span style="color:{_INK_SOFT};">{(b.title or '')[:140]}</span>
        </td>
      </tr>"""


def _standings_table(rows: list[StandingRow]) -> str:
    body = ""
    for r in rows:
        body += f"""
      <tr>
        <td style="padding:8px 0;border-bottom:1px solid {_RULE};font:15px {_SERIF};
            color:{_INK};font-weight:bold;">{r.label}</td>
        <td style="padding:8px 0;border-bottom:1px solid {_RULE};font:14px {_SERIF};
            color:{_ACCENT};text-align:right;white-space:nowrap;">{r.enacted} enacted</td>
        <td style="padding:8px 0 8px 16px;border-bottom:1px solid {_RULE};font:14px {_SERIF};
            color:{_MUTED};text-align:right;white-space:nowrap;">{r.active} active</td>
      </tr>"""
    return f'<table style="width:100%;border-collapse:collapse;">{body}\n  </table>'


def _section(heading: str, inner: str) -> str:
    return f"""
  <h2 style="font:bold 15px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;color:{_INK};
      border-bottom:1px solid rgba(26,26,46,0.25);padding-bottom:6px;margin:26px 0 4px;">{heading}</h2>
  {inner}"""


def render_welcome_html(
    sub: AlertSubscription,
    sop: StateOfPlay,
    as_of_label: str,
    recap: str | None = None,
) -> str:
    """Render the welcome email body: confirmation of scope + a windowed recent-activity roundup."""
    greeting_name = (sub.organization or "").strip()
    hello = f"Welcome, {greeting_name}" if greeting_name else "Welcome"

    sections: list[str] = []

    # Headline scoreboard — recent movement, not all-time totals.
    if sop.has_recent:
        sections.append(f"""
  <table style="width:100%;border-collapse:collapse;margin:6px 0 2px;">
    <tr>
      <td style="text-align:center;padding:12px;border:1px solid {_RULE};">
        <div style="font:bold 34px {_SERIF};color:{_ACCENT};">{sop.enacted_recent}</div>
        <div style="font:12px {_SERIF};text-transform:uppercase;letter-spacing:0.08em;color:{_MUTED};">
          enacted recently</div>
      </td>
      <td style="text-align:center;padding:12px;border:1px solid {_RULE};border-left:0;">
        <div style="font:bold 34px {_SERIF};color:{_INK};">{sop.active_recent}</div>
        <div style="font:12px {_SERIF};text-transform:uppercase;letter-spacing:0.08em;color:{_MUTED};">
          bills on the move</div>
      </td>
    </tr>
  </table>""")

    if recap:
        # The recap can come back as 2-3 paragraphs (blank-line separated); render each so the prose
        # breathes instead of collapsing into one wall of text.
        paras = [p.strip() for p in recap.split("\n\n") if p.strip()]
        para_html = "".join(
            f'<p style="font:italic 16px {_SERIF};color:{_INK};line-height:1.65;margin:0 0 12px;">'
            f"{p}</p>"
            for p in paras
        )
        sections.append(f"""
  <div style="margin:20px 0 4px;padding:2px 0 2px 18px;border-left:3px solid {_ACCENT};">
    {para_html}</div>""")

    # Recent-activity breakdowns, windowed. Show jurisdiction and topic independently: a subscriber
    # following multiple states gets the geographic split; one following multiple (or all) topics gets
    # the topical one — the all/all subscriber sees both. Only rendered when something actually moved.
    if sop.by_state and len(sop.by_state) > 1:
        sections.append(_section("Recent Activity by Jurisdiction", _standings_table(sop.by_state)))
    if sop.by_topic and len(sop.by_topic) > 1:
        sections.append(_section("Recent Activity by Topic", _standings_table(sop.by_topic)))

    if sop.recent_enacted:
        rows = "".join(_bill_line(b) for b in sop.recent_enacted)
        sections.append(
            _section("Recently Enacted",
                     f'<table style="width:100%;border-collapse:collapse;">{rows}\n  </table>')
        )

    if sop.recent_movement:
        rows = "".join(_bill_line(b) for b in sop.recent_movement)
        sections.append(
            _section("Moving Now",
                     f'<table style="width:100%;border-collapse:collapse;">{rows}\n  </table>')
        )

    # Orientation fallback — only when nothing moved in-window (a mature scope). Clearly framed as
    # established, not fresh, so old laws are never dressed up as news.
    if sop.established:
        rows = "".join(_bill_line(b) for b in sop.established)
        sections.append(
            _section("Established in Your Scope",
                     f'<p style="font:14px {_SERIF};color:{_MUTED};margin:2px 0 6px;">Nothing new has '
                     f'moved in your scope in the last few months. The laws already on the books:</p>'
                     f'<table style="width:100%;border-collapse:collapse;">{rows}\n  </table>')
        )

    # Undated in-scope bills can't be windowed (year-only/undated foreign rows), so they ride along as
    # a compact aside rather than being dropped or shown as if they were recent.
    if sop.on_the_books:
        rows = "".join(_bill_line(b) for b in sop.on_the_books)
        overflow = ""
        if sop.on_the_books_total > len(sop.on_the_books):
            overflow = (
                f'<p style="font:13px {_SERIF};color:{_MUTED};margin:6px 0 0;">…and '
                f'{sop.on_the_books_total - len(sop.on_the_books)} more in your scope without a dated '
                f'action.</p>'
            )
        sections.append(
            _section("Also on the Books",
                     f'<p style="font:14px {_SERIF};color:{_MUTED};margin:2px 0 6px;">In scope, but '
                     f'without a dated action to place on the timeline:</p>'
                     f'<table style="width:100%;border-collapse:collapse;">{rows}\n  </table>{overflow}')
        )

    if not sop.has_content:
        sections.append(f"""
  <p style="font:16px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:18px 0;">
    Nothing has matched your scope yet — but that's exactly why you're here. The moment a bill on your
    topics moves in your jurisdictions, you'll be the first to know.</p>""")

    body = "\n".join(sections)
    materials = _materials_summary(sub)
    # Slotted into the prose only when a material/product filter is set; with leading
    # space so it reads "all policy topics on Electronics across all jurisdictions".
    mat_html = f" on <strong>{materials}</strong>" if materials else ""
    scope_bits = [_topics_summary(sub)]
    if materials:
        scope_bits.append(materials)
    scope_bits.append(_jurisdictions_summary(sub))
    scope_line = " · ".join(scope_bits)

    inner = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 4px;font-weight:bold;">{hello}.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 10px;">
      You're following <strong>{_topics_summary(sub)}</strong>{mat_html} across
      <strong>{_jurisdictions_summary(sub)}</strong>. To catch you up, here's what's actually moved in
      that scope over the last six months (a full year for jurisdictions we can only date by the
      year).</p>
    {body}
    <h2 style="font:bold 15px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;color:{_INK};
        border-bottom:1px solid rgba(26,26,46,0.25);padding-bottom:6px;margin:28px 0 8px;">
      What lands in your inbox next</h2>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 14px;">
      That's the catch-up — from here it's just fresh movement. We'll email you when a new bill matching
      <strong>{_topics_summary(sub)}</strong>{mat_html} in
      <strong>{_jurisdictions_summary(sub)}</strong> is tracked, or when one changes status — only for
      genuinely recent action, never a months-old event dressed up as news. Explore the full picture
      any time at <a href="{_DASHBOARD_URL}" style="color:{_ACCENT};">the dashboard</a>.</p>"""
    colophon = (
        "You're receiving this because you just subscribed to Atlas Circular updates.<br>"
        f'<a href="{unsubscribe_url(sub.id)}" style="color:{_MUTED};text-decoration:underline;">'
        "Unsubscribe</a> · or reply to this email."
    )
    return render_shell(
        inner,
        dateline=f"Recent activity as of {as_of_label} · {scope_line}",
        colophon=colophon,
        body_padding="14px 28px 24px",
    )


# --- Sending -------------------------------------------------------------------------------------


def _as_of_label(now) -> str:
    """'June 2026' style month label for the dateline."""
    return now.strftime("%B %Y")


async def send_welcome_email(db: AsyncSession, sub: AlertSubscription) -> bool:
    """Best-effort welcome send for one subscriber. Returns True only if an email actually went out.

    Gated on enable_welcome_email + a SendGrid key + the subscriber having an email. Never raises —
    a welcome-email failure must never surface to the signup API caller.
    """
    if not settings.enable_welcome_email:
        log.info("welcome_email_skipped_flag_off", email=sub.email)
        return False
    if not sub.email:
        return False
    if not settings.sendgrid_api_key:
        log.info("welcome_email_skipped_no_sendgrid_key", email=sub.email)
        return False
    try:
        from sqlalchemy import func

        from app.alerts.sendgrid_sender import SendGridSender

        now = (await db.execute(select(func.now()))).scalar_one()
        sop = await build_state_of_play(db, sub, today=now.date())
        recap = await render_recap_paragraph(sub, sop)
        html = render_welcome_html(sub, sop, _as_of_label(now), recap=recap)
        subject = render_welcome_subject(sub)
        # Pass the List-Unsubscribe header (RFC 8058 one-click), matching the body's link — the
        # roundup is a bulk send and Gmail/Outlook penalise bulk mail without it. Same as the digest
        # and new-bill cycles.
        ok = await SendGridSender().send_html(
            sub.email, subject, html, list_unsubscribe_url=unsubscribe_url(sub.id)
        )
        log.info(
            "welcome_email_sent",
            email=sub.email,
            ok=ok,
            recent=sop.total_recent,
            on_the_books=sop.on_the_books_total,
            scope_total=sop.scope_total,
        )
        return ok
    except Exception as e:
        log.warning("welcome_email_failed", email=sub.email, error=str(e))
        return False


async def send_welcome_for_subscription(subscription_id: int) -> None:
    """Background-task entrypoint: open a fresh session, load the subscriber, send the welcome.

    The request's DB session is gone by the time this runs, so it owns its own session and reloads
    the row by id rather than holding a detached ORM object.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        sub = (
            await db.execute(
                select(AlertSubscription).where(AlertSubscription.id == subscription_id)
            )
        ).scalar_one_or_none()
        if sub is None:
            log.warning("welcome_email_subscription_missing", subscription_id=subscription_id)
            return
        await send_welcome_email(db, sub)


# --- Account-signup welcome ----------------------------------------------------------------------
# Distinct from the subscription welcome above: this fires when a brand-new Firebase free account is
# created (including via a referral link), where there's no AlertSubscription / scope to summarise.
# It welcomes the account and points at the 7-day Pro trial it just received. Triggered once per
# account from POST /billing/signup-trial. See conversion-funnel.


def render_account_welcome_subject() -> str:
    # Public brand is "Atlas Circular" — never the internal "Atlas Circular" codename in a subject.
    return "Welcome to Atlas Circular — your 7-day Pro trial is live"


def render_account_welcome_html() -> str:
    inner = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">Welcome to Atlas Circular.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 14px;">
      You've just created a free Atlas Circular account — and the next <strong>7 days are on us</strong>.
      Your Pro trial is live right now, no card required:</p>
    <ul style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 16px;padding-left:20px;">
      <li>The full <strong>Upcoming Deadlines</strong> timeline — every EPR compliance date, all 50 states</li>
      <li>Personal &amp; shared <strong>watch lists</strong> with alerts</li>
      <li>The complete dynamic <strong>Design Guide</strong></li>
      <li><strong>CSV export</strong> of bills &amp; deadlines</li>
    </ul>
    {cta_button(f"{_DASHBOARD_URL}/compliance", "Open your dashboard →")}
    <p style="font:14px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">
      When your 7 days are up, keep Pro at <strong>founding 50% off for life</strong> (closes Nov 30),
      or stay on Free. Want a heads-up when bills move?
      <a href="{_DASHBOARD_URL}" style="color:{_ACCENT};">Set up alerts →</a></p>"""
    return render_shell(
        inner,
        colophon="You're receiving this because you just created an Atlas Circular account.",
    )


async def send_account_welcome(email: str) -> bool:
    """Best-effort welcome for a brand-new free account (background-task entrypoint). Self-contained —
    no DB needed (no scope to summarise). Gated on enable_welcome_email + a SendGrid key + an email.
    Never raises — a welcome failure must never surface to the signup caller."""
    if not settings.enable_welcome_email:
        log.info("account_welcome_skipped_flag_off", email=email)
        return False
    if not email or not settings.sendgrid_api_key:
        return False
    try:
        from app.alerts.sendgrid_sender import SendGridSender

        ok = await SendGridSender().send_html(
            email, render_account_welcome_subject(), render_account_welcome_html()
        )
        log.info("account_welcome_sent", email=email, ok=ok)
        return ok
    except Exception as e:
        log.warning("account_welcome_failed", email=email, error=str(e))
        return False


# --- Complimentary Pro grant ---------------------------------------------------------------------
# Fires when an admin grants complimentary ("comp") Pro from the admin console (POST /admin/grant-pro).
# Distinct from the signup trial above: that one is automatic and self-serve; this is a gift we hand a
# specific early user. Self-contained — the grant only knows the recipient's email, an optional name,
# and the grant length (days, or None = indefinite). See grant_pro in app/api/admin.py.


def _comp_duration_label(days: int | None) -> str:
    """Human phrasing for the grant length, slotted after 'complimentary access for ...'."""
    if not days:
        return "the duration of our early-access period"
    if days == 1:
        return "1 day"
    return f"{days} days"


def render_comp_grant_subject() -> str:
    return "Your complimentary access to Atlas Circular"


def render_comp_grant_html(duration_label: str, name: str | None = None) -> str:
    greeting = f"Dear {name}," if name else "Hello,"
    inner = f"""
    <p style="font:16px {_SERIF};color:{_INK};margin:6px 0 14px;font-weight:bold;">{greeting}</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      Thank you for being an early user of <strong>Atlas Circular</strong>. You've been granted
      complimentary access for <strong>{duration_label}</strong>. Enjoy all of the features as we
      continue to develop this product.</p>
    {cta_button(f"{_DASHBOARD_URL}/compliance", "Open your dashboard →")}
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:22px 0 0;">
      Kind regards,<br>
      The Atlas Circular Team</p>"""
    return render_shell(
        inner,
        colophon="You're receiving this because you were granted complimentary access to Atlas Circular.",
    )


async def send_comp_grant_welcome(email: str, days: int | None = None, name: str | None = None) -> bool:
    """Best-effort notice that an admin granted this email complimentary Pro (background-task
    entrypoint). Self-contained — no DB needed. Gated on enable_welcome_email + a SendGrid key + an
    email. Never raises — a send failure must never surface to the admin grant caller."""
    if not settings.enable_welcome_email:
        log.info("comp_grant_welcome_skipped_flag_off", email=email)
        return False
    if not email or not settings.sendgrid_api_key:
        return False
    try:
        from app.alerts.sendgrid_sender import SendGridSender

        html = render_comp_grant_html(_comp_duration_label(days), name=name)
        ok = await SendGridSender().send_html(email, render_comp_grant_subject(), html)
        log.info("comp_grant_welcome_sent", email=email, ok=ok, days=days)
        return ok
    except Exception as e:
        log.warning("comp_grant_welcome_failed", email=email, error=str(e))
        return False


# --- Paid Pro purchase confirmation --------------------------------------------------------------
# Fires once per paid conversion, from the Stripe checkout.session.completed webhook (NOT the
# subscription.* events, which also fire on renewals). Doubles as purchase receipt + "Welcome to Pro".
# A founding seat lands mid-trial (status "trialing", card on file, billed after the 90-day trial), so
# the copy flexes between "your trial is live, billed later" and "your subscription is active".


def render_pro_welcome_subject(is_trial: bool = False) -> str:
    return (
        "Your Atlas Circular Pro trial is live"
        if is_trial
        else "You're in — your Atlas Circular Pro plan is active"
    )


def render_pro_welcome_html(is_trial: bool = False, founding: bool = False) -> str:
    founding_badge = (
        f"""
    <p style="font:13px {_SERIF};color:{_ACCENT};margin:0 0 14px;font-weight:bold;
        text-transform:uppercase;letter-spacing:0.06em;">★ Founding member · 50% off for life</p>"""
        if founding
        else ""
    )
    if is_trial:
        confirm = (
            "Your <strong>Pro trial</strong> is live and you have full access right now. You won't be "
            "billed until the trial ends — manage or cancel any time from your account before then."
        )
    else:
        confirm = (
            "Your payment went through and your <strong>Pro subscription is active</strong>. This email "
            "is your confirmation — manage your plan or grab a receipt any time from your account."
        )
    inner = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">Welcome to Pro.</p>
    {founding_badge}
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      Thank you for subscribing to <strong>Atlas Circular Pro</strong>. {confirm}</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 10px;">
      You now have the full toolkit:</p>
    <ul style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 16px;padding-left:20px;">
      <li>The full <strong>Upcoming Deadlines</strong> timeline — every EPR compliance date, all 50 states</li>
      <li>Personal &amp; shared <strong>watch lists</strong> with alerts</li>
      <li>The complete dynamic <strong>Design Guide</strong></li>
      <li><strong>CSV export</strong> of bills &amp; deadlines</li>
    </ul>
    {cta_button(f"{_DASHBOARD_URL}/compliance", "Open your dashboard →")}
    <p style="font:14px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">
      Manage your subscription, update payment details, or download invoices any time from
      <a href="{_DASHBOARD_URL}/account" style="color:{_ACCENT};">your account</a>.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:18px 0 0;">
      Kind regards,<br>
      The Atlas Circular Team</p>"""
    return render_shell(
        inner,
        colophon="You're receiving this because you subscribed to Atlas Circular Pro.",
    )


async def send_pro_welcome(email: str, is_trial: bool = False, founding: bool = False) -> bool:
    """Best-effort purchase confirmation / welcome for a paid Pro conversion (background-task
    entrypoint). Self-contained — no DB needed. Gated on enable_welcome_email + a SendGrid key + an
    email. Never raises — a send failure must never surface to the Stripe webhook caller."""
    if not settings.enable_welcome_email:
        log.info("pro_welcome_skipped_flag_off", email=email)
        return False
    if not email or not settings.sendgrid_api_key:
        return False
    try:
        from app.alerts.sendgrid_sender import SendGridSender

        html = render_pro_welcome_html(is_trial=is_trial, founding=founding)
        ok = await SendGridSender().send_html(
            email, render_pro_welcome_subject(is_trial=is_trial), html
        )
        log.info("pro_welcome_sent", email=email, ok=ok, is_trial=is_trial, founding=founding)
        return ok
    except Exception as e:
        log.warning("pro_welcome_failed", email=email, error=str(e))
        return False


# --- Billing lifecycle + referral notices --------------------------------------------------------
# Three transactional notices that close gaps in the alert map: a dunning email when a Pro renewal
# payment fails, a confirmation when a subscription is canceled, and a reward notice when a referral
# pays off. All self-contained (no DB), gated on enable_welcome_email + a SendGrid key like the rest,
# and best-effort so a send failure can never surface into the Stripe webhook / referral caller.


def _lifecycle_shell(title_line: str, body_inner: str, colophon: str) -> str:
    """Thin wrapper over the shared email shell, kept so the lifecycle notices below read cleanly.
    `title_line` becomes the masthead tagline; `body_inner` is the HTML between masthead and colophon."""
    return render_shell(body_inner, tagline=title_line, colophon=colophon)


# Backwards-compatible alias — the lifecycle notices below call _cta_button; it's the shared button now.
_cta_button = cta_button


# --- Payment failed (dunning) --------------------------------------------------------------------
# Fired from the Stripe invoice.payment_failed webhook. A Pro whose renewal card fails would otherwise
# be silently downgraded to free; this is the warning + path back. NOTE: requires the Stripe dashboard
# webhook to be subscribed to invoice.payment_failed (the endpoint historically only took 4 events).


def render_payment_failed_subject() -> str:
    return "Action needed — your Atlas Circular Pro payment didn't go through"


def render_payment_failed_html() -> str:
    body = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">
      A quick heads-up about your subscription.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      We tried to process the payment for your <strong>Atlas Circular Pro</strong> subscription, but it
      didn't go through. This is most often an expired or replaced card — nothing's lost yet.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 16px;">
      Update your payment details to keep your Pro access uninterrupted. If the payment isn't resolved,
      your account will drop back to the free plan.</p>
    {_cta_button(f"{_DASHBOARD_URL}/account", "Update payment details →")}
    <p style="font:14px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">
      Already fixed it, or want to check your status? Manage everything from
      <a href="{_DASHBOARD_URL}/account" style="color:{_ACCENT};">your account</a>.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:18px 0 0;">
      Kind regards,<br>The Atlas Circular Team</p>"""
    return _lifecycle_shell(
        "Tracking circularity globally",
        body,
        "You're receiving this because a payment on your Atlas Circular Pro subscription needs attention.",
    )


async def send_payment_failed(email: str) -> bool:
    """Best-effort dunning notice for a failed Pro renewal (background-task entrypoint). Gated on
    enable_welcome_email + a SendGrid key + an email. Never raises."""
    if not settings.enable_welcome_email:
        log.info("payment_failed_email_skipped_flag_off", email=email)
        return False
    if not email or not settings.sendgrid_api_key:
        return False
    try:
        from app.alerts.sendgrid_sender import SendGridSender

        ok = await SendGridSender().send_html(
            email, render_payment_failed_subject(), render_payment_failed_html()
        )
        log.info("payment_failed_email_sent", email=email, ok=ok)
        return ok
    except Exception as e:
        log.warning("payment_failed_email_failed", email=email, error=str(e))
        return False


# --- Subscription canceled -----------------------------------------------------------------------
# Fired from the Stripe customer.subscription.deleted webhook (the seat has lapsed to free). Cancels
# happen inside the Stripe-hosted portal, so this email is the only acknowledgement a user can get.


def render_subscription_canceled_subject() -> str:
    return "Your Atlas Circular Pro subscription has been canceled"


def render_subscription_canceled_html() -> str:
    body = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">
      Your Pro subscription has ended.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      We've canceled your <strong>Atlas Circular Pro</strong> subscription and your account is back on the
      free plan. You won't be billed again. You'll keep free access to the bill explorer and public
      pages — the Pro tools (full deadlines timeline, watch-list alerts, the Design Guide and CSV
      export) are paused.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 16px;">
      Changed your mind, or canceled by accident? You can pick Pro back up any time.</p>
    {_cta_button(f"{_DASHBOARD_URL}/account", "Reactivate Pro →")}
    <p style="font:14px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">
      We'd genuinely value a line on what we could have done better — just reply to this email.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:18px 0 0;">
      Kind regards,<br>The Atlas Circular Team</p>"""
    return _lifecycle_shell(
        "Tracking circularity globally",
        body,
        "You're receiving this because your Atlas Circular Pro subscription was canceled.",
    )


async def send_subscription_canceled(email: str) -> bool:
    """Best-effort cancellation confirmation (background-task entrypoint). Gated on
    enable_welcome_email + a SendGrid key + an email. Never raises."""
    if not settings.enable_welcome_email:
        log.info("subscription_canceled_email_skipped_flag_off", email=email)
        return False
    if not email or not settings.sendgrid_api_key:
        return False
    try:
        from app.alerts.sendgrid_sender import SendGridSender

        ok = await SendGridSender().send_html(
            email, render_subscription_canceled_subject(), render_subscription_canceled_html()
        )
        log.info("subscription_canceled_email_sent", email=email, ok=ok)
        return ok
    except Exception as e:
        log.warning("subscription_canceled_email_failed", email=email, error=str(e))
        return False


# --- Referral reward earned ----------------------------------------------------------------------
# Fired from POST /referrals/attribute when a new account signs up via someone's link and the referrer
# is granted comp days. Closes the share-to-unlock loop's missing payoff — the referrer previously had
# to poll the page to notice their reward.


def render_referral_reward_subject(days: int) -> str:
    return f"You just earned {days} free days of Atlas Circular Pro"


def render_referral_reward_html(days: int) -> str:
    body = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">
      Your referral paid off.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      Someone just signed up for <strong>Atlas Circular</strong> using your referral link — so
      we've added <strong>{days} days of Pro</strong> to your account. It's live right now; nothing to
      claim.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 16px;">
      Thanks for spreading the word. Keep sharing your link and the free days keep stacking up.</p>
    {_cta_button(f"{_DASHBOARD_URL}/compliance", "Open your dashboard →")}
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:18px 0 0;">
      Kind regards,<br>The Atlas Circular Team</p>"""
    return _lifecycle_shell(
        "Tracking circularity globally",
        body,
        "You're receiving this because a friend signed up using your Atlas Circular referral link.",
    )


async def send_referral_reward(email: str, days: int = 30) -> bool:
    """Best-effort 'you earned free Pro days' notice to a referrer (background-task entrypoint). Gated
    on enable_welcome_email + a SendGrid key + an email. Never raises."""
    if not settings.enable_welcome_email:
        log.info("referral_reward_email_skipped_flag_off", email=email)
        return False
    if not email or not settings.sendgrid_api_key:
        return False
    try:
        from app.alerts.sendgrid_sender import SendGridSender

        ok = await SendGridSender().send_html(
            email, render_referral_reward_subject(days), render_referral_reward_html(days)
        )
        log.info("referral_reward_email_sent", email=email, ok=ok, days=days)
        return ok
    except Exception as e:
        log.warning("referral_reward_email_failed", email=email, error=str(e))
        return False
