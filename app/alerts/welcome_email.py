"""One-time welcome email sent when someone subscribes.

Distinct from both the real-time per-change alerts (dispatcher.py) and the periodic digest
(digest.py). Where the digest is *window-based* — "what moved in the last 30 days" — this is a
*cumulative snapshot*: "here's where things stand right now" across exactly the states + topics the
new subscriber picked. It confirms what they signed up for and orients them with the current state
of play, so the first thing they get isn't an empty inbox waiting on the next bill to move.

Two layers:
  - Structured standings (build_state_of_play): deterministic counts pulled straight from the DB —
    enacted vs. active bills, broken out by jurisdiction, plus the landmark laws and what's live now.
  - An optional one-paragraph recap (render_recap_paragraph): Claude writing the standings up in a
    championship-recap voice, on-brand with the "Battle of the Bills" masthead. Flag-gated
    (enable_welcome_recap) and best-effort — the email renders fine without it. The prose is anchored
    to the structured counts so it can't drift far from the numbers (classifier noise can still leak
    a mis-tagged bill into the list, same caveat as the digest).

send_welcome_email() is best-effort and gated on enable_welcome_email; the API fires it from a
background task on signup, and scripts/send_welcome.py previews/sends it manually.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
from app.alerts.unsubscribe import unsubscribe_url
from app.config import settings
from app.models import AlertSubscription, Bill

log = structlog.get_logger()

_DASHBOARD_URL = "https://ce-bill-tracker.web.app"

# Status buckets for the cumulative snapshot. "Enacted" = signed into law; "dead" = no longer moving;
# everything else in between is "active". Mirrors the enacted/pending split in /bills/map-summary.
_ENACTED_STATUSES = {"enacted", "signed"}
_DEAD_STATUSES = {"failed", "vetoed"}

# Keep the landmark / active-now lists to a digestible handful.
_MAX_LANDMARK = 5
_MAX_ACTIVE = 5
_MAX_STANDING_ROWS = 8


def _is_enacted(b: Bill) -> bool:
    return (b.status or "") in _ENACTED_STATUSES


def _is_dead(b: Bill) -> bool:
    return (b.status or "") in _DEAD_STATUSES


def _is_active(b: Bill) -> bool:
    return not _is_enacted(b) and not _is_dead(b)


@dataclass
class StandingRow:
    """Enacted vs. active tally for one jurisdiction (or topic)."""
    label: str
    enacted: int = 0
    active: int = 0

    @property
    def total(self) -> int:
        return self.enacted + self.active


@dataclass
class StateOfPlay:
    total_bills: int = 0
    enacted_total: int = 0
    active_total: int = 0
    by_state: list[StandingRow] = field(default_factory=list)
    by_topic: list[StandingRow] = field(default_factory=list)
    landmark_bills: list[Bill] = field(default_factory=list)  # enacted, most actionable first
    active_now: list[Bill] = field(default_factory=list)      # live bills, most recent action first

    @property
    def has_content(self) -> bool:
        return self.total_bills > 0


def _recent_action_key(b: Bill):
    """Most recent action first; bills with no date sort last."""
    action = b.last_action_date or b.status_date
    return -(action.toordinal() if action else 0)


async def build_state_of_play(db: AsyncSession, sub: AlertSubscription) -> StateOfPlay:
    """Build the cumulative snapshot of EPR-relevant bills within a subscriber's scope.

    Unlike the digest there is no date window — this is the standing position across everything the
    subscriber follows. Bills are loaded once and filtered in memory with the same
    subscription_matches_bill() the digest uses, so scope semantics stay identical.
    """
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

    sop = StateOfPlay(total_bills=len(matched))
    if not matched:
        return sop

    state_rows: dict[str, StandingRow] = {}
    topic_rows: dict[str, StandingRow] = {}
    for b in matched:
        enacted = _is_enacted(b)
        active = _is_active(b)
        if enacted:
            sop.enacted_total += 1
        elif active:
            sop.active_total += 1

        srow = state_rows.setdefault(b.state, StandingRow(label=b.state))
        trow = topic_rows.setdefault(
            b.instrument_type or "other", StandingRow(label=topic_label(b.instrument_type))
        )
        for row in (srow, trow):
            if enacted:
                row.enacted += 1
            elif active:
                row.active += 1

    sop.by_state = sorted(state_rows.values(), key=lambda r: (-r.total, r.label))[:_MAX_STANDING_ROWS]
    sop.by_topic = sorted(topic_rows.values(), key=lambda r: (-r.total, r.label))[:_MAX_STANDING_ROWS]

    enacted_bills = sorted((b for b in matched if _is_enacted(b)), key=_bill_sort_key)
    active_bills = sorted((b for b in matched if _is_active(b)), key=_recent_action_key)
    sop.landmark_bills = enacted_bills[:_MAX_LANDMARK]
    sop.active_now = active_bills[:_MAX_ACTIVE]
    return sop


# --- LLM recap paragraph -------------------------------------------------------------------------

RECAP_MODEL = "claude-sonnet-4-6"

_RECAP_SYSTEM = """\
You are the ringside correspondent for "Battle of the Bills", a newsletter covering U.S. \
circular-economy and Extended Producer Responsibility (EPR) legislation. Keep the fight-night \
voice — but the fight has a point. In this ring the states are fighting FOR their citizens' future \
against corporate interests that profit from waste and disposability: every EPR law, every \
right-to-repair win clawed back from big tech in the courts, is a round won for a more egalitarian \
economy that uses materials and resources efficiently and lets a regenerative ecosystem stand — \
because without that ecosystem there is no economy at all. States are the contenders, bills are the \
bouts, enactment is a win on the cards, a veto or a dead bill is a loss.

Write a vivid, momentum-aware recap of the current state of play for a new subscriber. Be BRIEF: \
TWO short paragraphs, roughly 90-140 words total.

  1. Open on who's landing the biggest laws and where the energy is — and keep sight of why these \
bills are brought in the first place: citizens' future over corporate wellbeing.
  2. Name one or two live bouts worth watching, and close on the stakes — what's still undecided and \
why this reader is ringside for it.

Be theatrical but DISCIPLINED: every factual claim — every state, count, bill name, or status — must \
come straight from the standings you are given. Do NOT invent bill numbers, vote tallies, dates, \
sponsors, or outcomes, and do not imply a bill passed or failed unless its status says so. Don't \
overload the prose with slogans — let the framing carry through one or two sharp lines, not every \
sentence. Separate paragraphs with a blank line. No markdown, no headings, no lists, no preamble — \
just the prose.\
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
    landmarks = "\n".join(
        f"  - {b.state} {b.bill_number or 'bill'} ({_status_label(b.status)}): {(b.title or '')[:100]}"
        for b in sop.landmark_bills
    ) or "  (none enacted yet)"
    active = "\n".join(
        f"  - {b.state} {b.bill_number or 'bill'} ({_status_label(b.status)}): {(b.title or '')[:100]}"
        for b in sop.active_now
    ) or "  (nothing currently live)"
    return f"""\
{scope}

Overall: {sop.enacted_total} enacted laws and {sop.active_total} bills still in play across \
{len(sop.by_state)} jurisdiction(s) the reader follows.

Standings by state (enacted / active):
{standings}

Landmark laws on the books:
{landmarks}

Live right now:
{active}

Write the recap paragraph now."""


async def render_recap_paragraph(sub: AlertSubscription, sop: StateOfPlay) -> str | None:
    """Optional flourish: a one-paragraph championship-style recap of the standings. Returns None if
    disabled, unconfigured, the snapshot is empty, or the call fails — callers render without it."""
    if not settings.enable_welcome_recap or not settings.anthropic_api_key or not sop.has_content:
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
    return "Welcome to Battle of the Bills — your opening state of play"


def _bill_line(b: Bill, badge: str = "") -> str:
    url = b.source_url or "#"
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
    """Render the welcome email body: confirmation of scope + cumulative state of play."""
    greeting_name = (sub.organization or "").strip()
    hello = f"Welcome, {greeting_name}" if greeting_name else "Welcome"

    sections: list[str] = []

    # Headline scoreboard.
    sections.append(f"""
  <table style="width:100%;border-collapse:collapse;margin:6px 0 2px;">
    <tr>
      <td style="text-align:center;padding:12px;border:1px solid {_RULE};">
        <div style="font:bold 34px {_SERIF};color:{_ACCENT};">{sop.enacted_total}</div>
        <div style="font:12px {_SERIF};text-transform:uppercase;letter-spacing:0.08em;color:{_MUTED};">
          enacted laws</div>
      </td>
      <td style="text-align:center;padding:12px;border:1px solid {_RULE};border-left:0;">
        <div style="font:bold 34px {_SERIF};color:{_INK};">{sop.active_total}</div>
        <div style="font:12px {_SERIF};text-transform:uppercase;letter-spacing:0.08em;color:{_MUTED};">
          bills still in play</div>
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

    # Standings: show jurisdiction and topic breakdowns independently. A subscriber who follows
    # multiple states gets the geographic scoreboard; one who follows multiple (or all) topics gets
    # the topical one — the all/all subscriber sees both, which is how "all topics" gets distilled
    # into something legible rather than just the words "all policy topics".
    if sop.by_state and len(sop.by_state) > 1:
        sections.append(_section("Standings by Jurisdiction", _standings_table(sop.by_state)))
    if sop.by_topic and len(sop.by_topic) > 1:
        sections.append(_section("Standings by Topic", _standings_table(sop.by_topic)))

    if sop.landmark_bills:
        rows = "".join(_bill_line(b) for b in sop.landmark_bills)
        sections.append(
            _section("Landmark Laws on the Books",
                     f'<table style="width:100%;border-collapse:collapse;">{rows}\n  </table>')
        )

    if sop.active_now:
        rows = "".join(_bill_line(b) for b in sop.active_now)
        sections.append(
            _section("Live Right Now",
                     f'<table style="width:100%;border-collapse:collapse;">{rows}\n  </table>')
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
       border-bottom:1px solid {_RULE};">State of play as of {as_of_label} · {scope_line}</div>
  <!-- Body -->
  <div style="padding:14px 28px 24px;">
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 4px;font-weight:bold;">{hello} to the ring.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 10px;">
      You're following <strong>{_topics_summary(sub)}</strong>{mat_html} across
      <strong>{_jurisdictions_summary(sub)}</strong>. From here on you'll get a heads-up whenever a
      bill in that scope makes a move — here's where the fight stands today.</p>
    {body}
    <!-- What you'll get -->
    <h2 style="font:bold 15px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;color:{_INK};
        border-bottom:1px solid rgba(26,26,46,0.25);padding-bottom:6px;margin:28px 0 8px;">
      What lands in your inbox next</h2>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 14px;">
      Topical updates scoped to <strong>{_topics_summary(sub)}</strong>{mat_html} in
      <strong>{_jurisdictions_summary(sub)}</strong> — a note when a matching bill is introduced or
      changes status on its way to becoming law, plus a periodic digest rounding up the month's
      movement. Explore the full picture any time at
      <a href="{_DASHBOARD_URL}" style="color:{_ACCENT};">the dashboard</a>.</p>
  </div>
  <!-- Colophon -->
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    You're receiving this because you just subscribed to SignalScout updates.<br>
    <a href="{unsubscribe_url(sub.id)}" style="color:{_MUTED};text-decoration:underline;">Unsubscribe</a>
    · or reply to this email.
  </div>
 </div>
</body></html>
"""


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
        sop = await build_state_of_play(db, sub)
        recap = await render_recap_paragraph(sub, sop)
        html = render_welcome_html(sub, sop, _as_of_label(now), recap=recap)
        subject = render_welcome_subject(sub)
        ok = await SendGridSender().send_html(sub.email, subject, html)
        log.info("welcome_email_sent", email=sub.email, ok=ok, bills=sop.total_bills)
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
    return "Welcome to SignalScout — your 7-day Pro trial is live"


def render_account_welcome_html() -> str:
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
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
  <div style="padding:18px 28px 24px;">
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">Welcome to the ring.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 14px;">
      You've just created a free SignalScout account — and the next <strong>7 days are on us</strong>.
      Your Pro trial is live right now, no card required:</p>
    <ul style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 16px;padding-left:20px;">
      <li>The full <strong>Upcoming Deadlines</strong> timeline — every EPR compliance date, all 50 states</li>
      <li>Personal &amp; shared <strong>watch lists</strong> with alerts</li>
      <li>The complete dynamic <strong>Design Guide</strong></li>
      <li><strong>CSV export</strong> of bills &amp; deadlines</li>
    </ul>
    <a href="{_DASHBOARD_URL}/compliance" style="display:inline-block;background:{_ACCENT};color:#fff;
       text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">
      Open your dashboard →</a>
    <p style="font:14px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">
      When your 7 days are up, keep Pro at <strong>founding 50% off for life</strong> (closes Nov 30),
      or stay on Free. Want a heads-up when bills move?
      <a href="{_DASHBOARD_URL}" style="color:{_ACCENT};">Set up alerts →</a></p>
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    You're receiving this because you just created a SignalScout account.
  </div>
 </div>
</body></html>
"""


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
    return "Your complimentary access to Battle of the Bills"


def render_comp_grant_html(duration_label: str, name: str | None = None) -> str:
    greeting = f"Dear {name}," if name else "Hello,"
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
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
  <div style="padding:18px 28px 24px;">
    <p style="font:16px {_SERIF};color:{_INK};margin:6px 0 14px;font-weight:bold;">{greeting}</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      Thank you for being an early user of <strong>Battle of the Bills</strong>. You've been granted
      complimentary access for <strong>{duration_label}</strong>. Enjoy all of the features as we
      continue to develop this product.</p>
    <a href="{_DASHBOARD_URL}/compliance" style="display:inline-block;background:{_ACCENT};color:#fff;
       text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">
      Open your dashboard →</a>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:22px 0 0;">
      Kind regards,<br>
      The SignalScout Team</p>
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    You're receiving this because you were granted complimentary access to SignalScout.
  </div>
 </div>
</body></html>
"""


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
        "Your SignalScout Pro trial is live"
        if is_trial
        else "Welcome to SignalScout Pro — your purchase is confirmed"
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
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
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
  <div style="padding:18px 28px 24px;">
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">Welcome to Pro.</p>
    {founding_badge}
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      Thank you for subscribing to <strong>SignalScout Pro</strong>. {confirm}</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 10px;">
      You now have the full toolkit:</p>
    <ul style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 16px;padding-left:20px;">
      <li>The full <strong>Upcoming Deadlines</strong> timeline — every EPR compliance date, all 50 states</li>
      <li>Personal &amp; shared <strong>watch lists</strong> with alerts</li>
      <li>The complete dynamic <strong>Design Guide</strong></li>
      <li><strong>CSV export</strong> of bills &amp; deadlines</li>
    </ul>
    <a href="{_DASHBOARD_URL}/compliance" style="display:inline-block;background:{_ACCENT};color:#fff;
       text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">
      Open your dashboard →</a>
    <p style="font:14px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">
      Manage your subscription, update payment details, or download invoices any time from
      <a href="{_DASHBOARD_URL}/account" style="color:{_ACCENT};">your account</a>.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:18px 0 0;">
      Kind regards,<br>
      The SignalScout Team</p>
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    You're receiving this because you subscribed to SignalScout Pro.
  </div>
 </div>
</body></html>
"""


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
    """The shared Gazette masthead + colophon wrapper, so the lifecycle notices stay on-brand without
    each re-pasting the masthead. `body_inner` is the inner HTML between masthead and colophon."""
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">
  <div style="background:{_PAPER};padding:26px 28px 18px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      SignalScout · EPR Legislative Intelligence
    </div>
    <h1 style="font:bold 40px {_SERIF};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:16px 0 6px;line-height:1.05;">Battle of the Bills</h1>
    <p style="font:italic 15px {_SERIF};color:{_INK_SOFT};margin:0;">{title_line}</p>
  </div>
  <div style="padding:18px 28px 24px;">
    {body_inner}
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    {colophon}
  </div>
 </div>
</body></html>
"""


def _cta_button(href: str, label: str) -> str:
    return (
        f'<a href="{href}" style="display:inline-block;background:{_ACCENT};color:#fff;'
        f'text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">{label}</a>'
    )


# --- Payment failed (dunning) --------------------------------------------------------------------
# Fired from the Stripe invoice.payment_failed webhook. A Pro whose renewal card fails would otherwise
# be silently downgraded to free; this is the warning + path back. NOTE: requires the Stripe dashboard
# webhook to be subscribed to invoice.payment_failed (the endpoint historically only took 4 events).


def render_payment_failed_subject() -> str:
    return "Action needed — your SignalScout Pro payment didn't go through"


def render_payment_failed_html() -> str:
    body = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">
      A quick heads-up about your subscription.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      We tried to process the payment for your <strong>SignalScout Pro</strong> subscription, but it
      didn't go through. This is most often an expired or replaced card — nothing's lost yet.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 16px;">
      Update your payment details to keep your Pro access uninterrupted. If the payment isn't resolved,
      your account will drop back to the free plan.</p>
    {_cta_button(f"{_DASHBOARD_URL}/account", "Update payment details →")}
    <p style="font:14px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">
      Already fixed it, or want to check your status? Manage everything from
      <a href="{_DASHBOARD_URL}/account" style="color:{_ACCENT};">your account</a>.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:18px 0 0;">
      Kind regards,<br>The SignalScout Team</p>"""
    return _lifecycle_shell(
        "Tracking circularity-aligned legislation across the USA",
        body,
        "You're receiving this because a payment on your SignalScout Pro subscription needs attention.",
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
    return "Your SignalScout Pro subscription has been canceled"


def render_subscription_canceled_html() -> str:
    body = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">
      Your Pro subscription has ended.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      We've canceled your <strong>SignalScout Pro</strong> subscription and your account is back on the
      free plan. You won't be billed again. You'll keep free access to the bill explorer and public
      pages — the Pro tools (full deadlines timeline, watch-list alerts, the Design Guide and CSV
      export) are paused.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 16px;">
      Changed your mind, or canceled by accident? You can pick Pro back up any time.</p>
    {_cta_button(f"{_DASHBOARD_URL}/account", "Reactivate Pro →")}
    <p style="font:14px {_SERIF};color:{_MUTED};line-height:1.6;margin:18px 0 0;">
      We'd genuinely value a line on what we could have done better — just reply to this email.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:18px 0 0;">
      Kind regards,<br>The SignalScout Team</p>"""
    return _lifecycle_shell(
        "Tracking circularity-aligned legislation across the USA",
        body,
        "You're receiving this because your SignalScout Pro subscription was canceled.",
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
    return f"You just earned {days} free days of SignalScout Pro"


def render_referral_reward_html(days: int) -> str:
    body = f"""
    <p style="font:18px {_SERIF};color:{_INK};margin:6px 0 10px;font-weight:bold;">
      Your referral paid off.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 14px;">
      Someone just signed up for <strong>Battle of the Bills</strong> using your referral link — so
      we've added <strong>{days} days of Pro</strong> to your account. It's live right now; nothing to
      claim.</p>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:0 0 16px;">
      Thanks for spreading the word. Keep sharing your link and the free days keep stacking up.</p>
    {_cta_button(f"{_DASHBOARD_URL}/compliance", "Open your dashboard →")}
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;margin:18px 0 0;">
      Kind regards,<br>The SignalScout Team</p>"""
    return _lifecycle_shell(
        "Tracking circularity-aligned legislation across the USA",
        body,
        "You're receiving this because a friend signed up using your SignalScout referral link.",
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
