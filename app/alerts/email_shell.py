"""The one shared Atlas Circular email shell — tokens + masthead/colophon wrapper.

Every outbound email should look like it came from the same publication and echo the web app's
"gazette" identity. Before this module each sender hand-rolled its own masthead HTML (the same
double-rule block copy-pasted across a dozen files) and one path — the real-time alert in
sendgrid_sender — used a different Arial/blue-bar aesthetic entirely. This centralises the look:

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


def _footer_actions(unsubscribe_url: str | None, subscribe_url: str | None) -> str:
    """The two footer affordances: leave, or — if this was forwarded to you — join.

    Deliberately below the colophon and visually quiet. The unsubscribe is a real button rather than
    a buried link: making it hard to leave is what earns spam complaints, which cost far more
    deliverability than the unsubscribe itself.
    """
    parts = []
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
  </div>{_footer_actions(unsubscribe_url, subscribe_url)}
 </div>
</body></html>
"""


def cta_button(href: str, label: str) -> str:
    """The standard accent CTA button used across the transactional emails."""
    return (
        f'<a href="{href}" style="display:inline-block;background:{_ACCENT};color:#fff;'
        f'text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">{label}</a>'
    )
