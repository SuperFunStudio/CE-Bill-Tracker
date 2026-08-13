"""The one shared Atlas Circular email shell — tokens + masthead/colophon wrapper.

Every outbound email should look like it came from the same publication and echo the web app's
"gazette" identity. Before this module each sender hand-rolled its own masthead HTML (the same
double-rule block copy-pasted across a dozen files) and one path — the real-time alert in
email_sender — used a different Arial/blue-bar aesthetic entirely. This centralises the look:

  - tokens (colors, fonts) live here, once;
  - `render_shell()` produces the masthead + optional dateline + body + colophon;
  - callers supply only the inner body HTML and a colophon line.

Type: email clients can't load web fonts reliably, so the body face is a Georgia serif stack (carries
the same newspaper feel the web gets from Playfair Display via `.font-serif`). The masthead heading
stack lists 'Playfair Display' first so the clients that DO honour it match the web display face
exactly, and everything else falls back to Georgia — the same graceful degradation the web uses.
"""
from __future__ import annotations

# Gazette palette — mirrors dashboard-next/src/app/globals.css light mode so email and web read as one
# system. RGB-equivalent hexes; email needs concrete colors.
_SERIF = "Georgia, 'Times New Roman', Times, serif"          # body face
_HEADING = "'Playfair Display', Georgia, 'Times New Roman', serif"  # masthead/display face (matches web)
_INK = "#1a1a2e"        # --text-primary
_INK_SOFT = "#495057"   # --text-secondary
_MUTED = "#6b7280"      # --text-muted
_PAPER = "#f8f9fa"      # --bg-primary
_RULE = "#dee2e6"       # --border-default
_ACCENT = "#1e6ae9"     # --green-accent (Atlas blue)

DASHBOARD_URL = "https://www.atlascircular.com"

TAGLINE = "Tracking the circular economy"

PUBLISHER_NAME = "SUPERFUN STUDIO"
PUBLISHER_URL = "https://www.superfun.studio"
PRIVACY_URL = f"{DASHBOARD_URL}/privacy"
TERMS_URL = f"{DASHBOARD_URL}/terms"

# The rule-bounded line above the wordmark. It used to read "SUPERFUN STUDIO · PRESENTS" on every
# email — publisher ego in the most expensive real estate we own. Worse, it was also the *preheader*:
# the snippet Gmail shows next to the subject in the inbox list read "SUPERFUN STU…", so the one line
# that decides whether a message gets opened said nothing about the message. It's now an edition line
# ("LITIGATION ALERT · 18 JUNE 2026") supplied per email — classification plus freshness, both
# scannable in a glance — and omitted entirely when a caller has nothing worth putting there.


def _masthead(tagline: str | None, kicker: str | None) -> str:
    kicker_html = (
        f"""
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      {kicker}
    </div>"""
        if kicker
        else ""
    )
    tagline_html = (
        f'\n    <p style="font:italic 15px {_SERIF};color:{_INK_SOFT};margin:0;">{tagline}</p>'
        if tagline
        else ""
    )
    # Tighter top padding when there's no kicker, so dropping the line doesn't leave a hole.
    pad_top = 26 if kicker else 22
    return f"""
  <div style="background:{_PAPER};padding:{pad_top}px 28px 18px;text-align:center;border-bottom:3px double {_INK};">{kicker_html}
    <h1 style="font:bold 40px {_HEADING};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:{16 if kicker else 0}px 0 6px;line-height:1.05;">Atlas Circular</h1>{tagline_html}
  </div>"""


def _preheader(text: str) -> str:
    """Hidden preview text — the snippet a mail client shows beside the subject in the inbox list.

    Invisible in the opened message (zero height, transparent, off-screen) but read by Gmail/Outlook
    when building the list row. Without one, clients grab whatever text comes first, which is how the
    masthead ended up as our preview copy. The trailing whitespace run stops the client from padding
    the snippet with the first words of the body.
    """
    return (
        f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;'
        f'font-size:1px;line-height:1px;color:{_PAPER};opacity:0;">{text}'
        f'{"&#847;&zwnj;&nbsp;" * 60}</div>'
    )


# The referral note's deep link. Points at the sitewide footer CTA (SiteFooter.tsx `id="refer"`), which
# already handles both cases — signed-in readers get their share link, signed-out get a sign-in prompt —
# so email doesn't need to embed a per-recipient code. The UTM tags are what make this measurable: GA's
# captureAttribution reads them on landing, so we can tell whether email is a viable referral channel at
# all. Without them the visit is indistinguishable from organic and the experiment answers nothing.
REFERRAL_URL = (
    f"{DASHBOARD_URL}/?utm_source=email&utm_medium=footer&utm_campaign=referral#refer"
)


def _referral_note(is_pro: bool) -> str:
    """The quiet referral line.

    Leads with what the reader GETS and states the condition in the same breath, so it reads as a
    reward rather than a request. The earlier "give a month, get a month" phrasing put the ask first
    and left "and it costs you nothing" implicit.

    Pro members still benefit (a referral extends their membership), so their variant shifts from
    "get a free month" to "add one to your membership" — offering Pro to someone already paying for
    it is the fastest way to make the whole line scan as boilerplate.
    """
    text = (
        "Add a free month of Pro to your membership when you share the Atlas with a friend using"
        " your link."
        if is_pro
        else "Get a free month of Pro when you share the Atlas with a friend using your link."
    )
    return (
        f'<p style="font:13px {_SERIF};color:{_MUTED};margin:0 0 10px;">{text} '
        f'<a href="{REFERRAL_URL}" style="color:{_ACCENT};text-decoration:underline;">'
        f"Get your link →</a></p>"
    )


def _footer_actions(
    unsubscribe_url: str | None,
    subscribe_url: str | None,
    referral: bool | None = None,
    referral_is_pro: bool = False,
) -> str:
    """The footer affordances: refer a colleague, leave, or — if this was forwarded — join.

    Deliberately below the colophon and visually quiet. The unsubscribe is a real button rather than
    a buried link: making it hard to leave is what earns spam complaints, which cost far more
    deliverability than the unsubscribe itself. The referral note is opt-in per caller for the same
    reason — see render_shell's `referral` arg for which emails should NOT carry it.
    """
    parts = []
    if referral:
        parts.append(_referral_note(referral_is_pro))
    if subscribe_url:
        parts.append(
            f'<p style="font:13px {_SERIF};color:{_MUTED};margin:0 0 10px;">'
            f"Was this forwarded to you? "
            f'<a href="{subscribe_url}" style="color:{_ACCENT};text-decoration:underline;">'
            f"Get these alerts for the jurisdictions and topics you follow →</a></p>"
        )
    if unsubscribe_url:
        parts.append(
            f'<a href="{unsubscribe_url}" style="display:inline-block;border:1px solid {_RULE};'
            f"border-radius:4px;padding:7px 16px;font:12px {_SERIF};color:{_MUTED};"
            f'text-decoration:none;">Unsubscribe from these alerts</a>'
        )
    if not parts:
        return ""
    return (
        f'<div style="padding:4px 28px 20px;text-align:center;">{"".join(parts)}</div>'
    )


def _business_address_lines() -> list[str]:
    """The configured postal address, split into display lines.

    Env-only (`BUSINESS_ADDRESS`) so the address isn't committed. Accepts newline- or `|`-separated
    lines; blank/absent yields `[]` and the address line is simply omitted rather than raising — a
    missing env var must not take down every outbound email.
    """
    from app.config import settings

    raw = (settings.business_address or "").replace("|", "\n")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _identity_block() -> str:
    """Sender identity: who sent this, from what postal address, under which policies.

    On **every** email, transactional included. CAN-SPAM §7704(a)(5) only compels the postal address
    on commercial mail, but the line SendGrid's compliance review draws is at the account, not the
    message — one bulk send lacking an identifiable sender risks the sending identity we've spent
    months warming. And the cost of carrying it on a password reset is four lines of grey 11px type.

    The wordmark is the brand; the publisher sits under it in smaller type and carries the link, so
    the reader sees "Atlas Circular" first and can still verify a real company stands behind it.
    """
    address = _business_address_lines()
    address_html = (
        f'<div style="margin:0 0 4px;">{" · ".join(address)}</div>' if address else ""
    )
    return f"""
  <div style="padding:0 28px 24px;text-align:center;font:11px {_SERIF};color:{_MUTED};
       line-height:1.6;">
    <div style="font:13px {_HEADING};letter-spacing:0.04em;color:{_INK_SOFT};margin:0 0 1px;">
      Atlas Circular</div>
    <div style="margin:0 0 6px;">a <a href="{PUBLISHER_URL}"
       style="color:{_MUTED};text-decoration:underline;">{PUBLISHER_NAME}</a> project</div>{address_html}
    <div><a href="{PRIVACY_URL}" style="color:{_MUTED};text-decoration:underline;">Privacy Policy</a>
      &nbsp;·&nbsp;
      <a href="{TERMS_URL}" style="color:{_MUTED};text-decoration:underline;">Terms</a></div>
  </div>"""


def identity_text() -> str:
    """The plain-text twin of `_identity_block`, for hand-written `text/plain` parts.

    Bodies derived from the HTML pick the identity up automatically via `html_to_text`; the two
    senders that hand-build their text part append this instead, so both MIME parts carry the same
    sender identity. A spam filter comparing the parts is one more reason not to let them diverge.
    """
    lines = [f"Atlas Circular — a {PUBLISHER_NAME} project ({PUBLISHER_URL})"]
    lines.extend(_business_address_lines())
    lines.append(f"Privacy Policy: {PRIVACY_URL}")
    lines.append(f"Terms: {TERMS_URL}")
    return "\n\n--\n" + "\n".join(lines)


def render_shell(
    body_inner: str,
    *,
    colophon: str,
    tagline: str | None = TAGLINE,
    kicker: str | None = None,
    preheader: str | None = None,
    dateline: str | None = None,
    unsubscribe_url: str | None = None,
    subscribe_url: str | None = None,
    referral: bool = False,
    referral_is_pro: bool = False,
    body_padding: str = "18px 28px 24px",
) -> str:
    """Wrap `body_inner` in the shared Atlas Circular masthead + colophon.

    - `colophon`: the footer line(s), fully formed by the caller (some carry an unsubscribe link, some
      don't) — rendered under a double rule.
    - `kicker`: the edition line above the wordmark ("LITIGATION ALERT · 18 JUNE 2026"). Omitted when
      None — better no line than a line that says nothing.
    - `preheader`: inbox preview text. Pass one on anything a recipient chooses whether to open; it's
      the highest-leverage copy in the message. Falls back to the client scraping the masthead.
    - `tagline`: the italic line under the wordmark. Pass None to drop it when the kicker already
      says what this email is (two labels for one message is one too many).
    - `dateline`: optional italic dateline bar between masthead and body (digests/welcomes use it).
    - `unsubscribe_url` / `subscribe_url`: footer actions — see _footer_actions.
    - `referral`: add the "give a month, get a month" note. Opt-in, and deliberately NOT default-on:
      it belongs on engagement mail (digest, alerts, welcomes) but not on anything transactional or
      adversarial — a failed payment, a cancellation, or a password reset is the wrong moment to ask
      for a favour, and on the security mails any extra link is a phishing-shaped thing to teach.
    - `referral_is_pro`: flips the copy from "get a month" to "give a month / extend yours", so the
      offer reads honestly to someone who already subscribes.
    """
    dateline_html = ""
    if dateline:
        dateline_html = (
            f'\n  <div style="padding:9px 28px;font:italic 13px {_SERIF};color:{_MUTED};'
            f'text-align:center;border-bottom:1px solid {_RULE};">{dateline}</div>'
        )
    # Preheader must be the first thing inside <body> — clients read forward from the top.
    preheader_html = _preheader(preheader) if preheader else ""
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">{preheader_html}
 <div style="max-width:640px;margin:0 auto;background:#fff;">{_masthead(tagline, kicker)}{dateline_html}
  <div style="padding:{body_padding};">
    {body_inner}
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    {colophon}
  </div>{_footer_actions(unsubscribe_url, subscribe_url, referral, referral_is_pro)}{_identity_block()}
 </div>
</body></html>
"""


def cta_button(href: str, label: str) -> str:
    """The standard accent CTA button used across the transactional emails."""
    return (
        f'<a href="{href}" style="display:inline-block;background:{_ACCENT};color:#fff;'
        f'text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">{label}</a>'
    )
