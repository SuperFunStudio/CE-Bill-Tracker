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

# The masthead kicker + default tagline. Kept here so a single edit re-brands every email.
_KICKER = "Atlas Circular · EPR Legislative Intelligence"
TAGLINE = "Tracking sustainability across the globe"


def _masthead(tagline: str) -> str:
    return f"""
  <div style="background:{_PAPER};padding:26px 28px 18px;text-align:center;border-bottom:3px double {_INK};">
    <div style="border-top:1px solid {_INK};border-bottom:1px solid {_INK};padding:3px 0;
         font:11px {_SERIF};letter-spacing:0.18em;text-transform:uppercase;color:{_MUTED};">
      {_KICKER}
    </div>
    <h1 style="font:bold 40px {_HEADING};text-transform:uppercase;letter-spacing:0.06em;
        color:{_INK};margin:16px 0 6px;line-height:1.05;">Atlas Circular</h1>
    <p style="font:italic 15px {_SERIF};color:{_INK_SOFT};margin:0;">{tagline}</p>
  </div>"""


def render_shell(
    body_inner: str,
    *,
    colophon: str,
    tagline: str = TAGLINE,
    dateline: str | None = None,
    body_padding: str = "18px 28px 24px",
) -> str:
    """Wrap `body_inner` in the shared Atlas Circular masthead + colophon.

    - `colophon`: the footer line(s), fully formed by the caller (some carry an unsubscribe link, some
      don't) — rendered under a double rule.
    - `dateline`: optional italic dateline bar between masthead and body (digests/welcomes use it).
    """
    dateline_html = ""
    if dateline:
        dateline_html = (
            f'\n  <div style="padding:9px 28px;font:italic 13px {_SERIF};color:{_MUTED};'
            f'text-align:center;border-bottom:1px solid {_RULE};">{dateline}</div>'
        )
    return f"""
<html><body style="margin:0;padding:0;background:{_PAPER};">
 <div style="max-width:640px;margin:0 auto;background:#fff;">{_masthead(tagline)}{dateline_html}
  <div style="padding:{body_padding};">
    {body_inner}
  </div>
  <div style="padding:18px 28px;font:italic 12px {_SERIF};color:{_MUTED};text-align:center;
       border-top:3px double {_INK};">
    {colophon}
  </div>
 </div>
</body></html>
"""


def cta_button(href: str, label: str) -> str:
    """The standard accent CTA button used across the transactional emails."""
    return (
        f'<a href="{href}" style="display:inline-block;background:{_ACCENT};color:#fff;'
        f'text-decoration:none;font:bold 14px {_SERIF};padding:11px 24px;border-radius:4px;">{label}</a>'
    )
