"""Outbound email: the templates every alert/lifecycle message is rendered from, and the Postmark
transport that puts them on the wire.

Provider note: this used to talk to SendGrid. Postmark's send API is a single JSON POST, so there's
no SDK — just httpx and the server token. The only structural difference that leaks into callers is
message streams: Postmark keeps transactional and bulk traffic apart (see `_stream_for`)."""

import re
from datetime import date
from typing import Any

import httpx
import structlog

from app.alerts.applinks import bill_url, subscribe_url
from app.alerts.email_shell import (
    _ACCENT,
    _INK,
    _INK_SOFT,
    _MUTED,
    _RULE,
    _SERIF,
    cta_button,
    identity_text,
    render_shell,
)
from app.config import settings
from app.models import Bill, BillChange

log = structlog.get_logger()


POSTMARK_ENDPOINT = "https://api.postmarkapp.com/email"
# Postmark answers 200 with an ErrorCode of 0 on success; anything else is a failure described in
# the body. 406 is the one worth naming: the recipient is on the server's suppression list (hard
# bounce or spam complaint), so this is a deliberate refusal, not an outage — retrying won't help.
# Two other codes show up as whole-batch failures rather than per-address ones: 300 (unverified
# From-address) and 412 (account pending approval — every recipient must be on the From domain,
# observed 2026-08-12 during the SendGrid cutover). Both mean nobody gets mail, which is what the
# dispatcher's outage hold is for.
_INACTIVE_RECIPIENT = 406


def _stream_for(list_unsubscribe_url: str | None) -> str:
    """Pick the Postmark message stream for one send.

    Postmark refuses to mix transactional and bulk traffic on a single stream, and the separation is
    what keeps a digest opt-out from suppressing a password-reset email. Carrying a one-click
    unsubscribe URL is exactly what makes a send bulk here — the digest, new-bill alerts, the
    watchlist recap and the consolidated bill alerts all pass one; verification, welcome, receipts
    and access-request mail don't.
    """
    return settings.postmark_broadcast_stream if list_unsubscribe_url else settings.postmark_message_stream


def _from_header(from_email: str | None) -> str:
    """Render the From header, display name included.

    Everything ships from one address; the two voices differ only by display name (the brand for the
    automated cycles, a person for the templates that ask for a reply). So the name is chosen by what
    the CALLER asked for, not by the address: `from_email=settings.email_hello_from` means the
    founder voice even though that resolves to the same mailbox as the default. Checking the address
    first would collapse the two the moment they point at the same place — which is the default.

    An address that is neither identity (a genuine one-off override) goes out bare rather than
    borrowing a name that doesn't describe it.

    RFC 5322 quoted-string, always — a display name containing a comma or a period is otherwise a
    malformed header, and quoting unconditionally is one rule instead of a character class to get
    wrong.
    """
    address = from_email or settings.email_from
    if from_email is None:
        name = settings.email_from_name
    elif from_email == settings.email_hello_from:
        name = settings.email_hello_from_name
    elif from_email == settings.email_from:
        name = settings.email_from_name
    else:
        name = ""
    if not name:
        return address
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}" <{address}>'


def _build_payload(
    to_email: str,
    subject: str,
    html: str,
    text: str,
    from_email: str | None = None,
    list_unsubscribe_url: str | None = None,
) -> dict[str, Any]:
    """Assemble one Postmark /email request body.

    Always multipart: HtmlBody plus TextBody, because an HTML-only message scores worse with spam
    filters. Reply-To is set on every message — a reader hitting Reply expects to reach a human,
    whether or not that template invited it — and skipped when unconfigured so an unset deployment
    sends as before.
    """
    payload: dict[str, Any] = {
        "From": _from_header(from_email),
        "To": to_email,
        "Subject": subject,
        "HtmlBody": html,
        "TextBody": text,
        "MessageStream": _stream_for(list_unsubscribe_url),
        "TrackOpens": True,
        # Link tracking rewrites hrefs through the provider's click host. See email_click_tracking:
        # off until a branded click host is verified to load cleanly.
        "TrackLinks": "HtmlAndText" if settings.email_click_tracking else "None",
    }
    if settings.email_reply_to:
        payload["ReplyTo"] = settings.email_reply_to
    if list_unsubscribe_url:
        # RFC 8058 one-click, carrying the same token as the in-body button so the two unsubscribe
        # routes can't disagree. Postmark only injects its own List-Unsubscribe on a broadcast stream
        # when the message doesn't already have one, so setting it here keeps our endpoint in charge.
        payload["Headers"] = [
            {"Name": "List-Unsubscribe", "Value": f"<{list_unsubscribe_url}>"},
            {"Name": "List-Unsubscribe-Post", "Value": "List-Unsubscribe=One-Click"},
        ]
    return payload


async def _post(payload: dict[str, Any], event: str) -> bool:
    """POST one message to Postmark. Returns whether it was accepted; never raises."""
    to_email = payload.get("To")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                POSTMARK_ENDPOINT,
                json=payload,
                headers={
                    "X-Postmark-Server-Token": settings.postmark_api_key,
                    "Accept": "application/json",
                },
            )
    except Exception as e:  # network/timeout — the send is lost, but the caller isn't
        log.error(f"{event}_exception", error=str(e), to=to_email)
        return False

    try:
        body = response.json()
    except ValueError:
        body = {}
    error_code = body.get("ErrorCode", -1)
    if response.status_code == 200 and error_code == 0:
        return True
    log.warning(
        f"{event}_failed",
        status=response.status_code,
        error_code=error_code,
        message=body.get("Message", response.text[:200]),
        suppressed=error_code == _INACTIVE_RECIPIENT,
        to=to_email,
        stream=payload.get("MessageStream"),
    )
    return False


def _linkify(text: str) -> str:
    """Turn bare URLs in channel-neutral alert prose into anchors.

    Bodies shared with Slack can't carry HTML (Slack would print the tags) and can't carry markdown
    (email would print the asterisks), so they carry bare URLs — which are inert inside an HTML
    email body. This is the email-side half of that trade-off.
    """
    return re.sub(
        r'(?<![">])(https?://[^\s<]+)',
        lambda m: f'<a href="{m.group(1)}" style="color:{_ACCENT};">{m.group(1)}</a>',
        text,
    )


def html_to_text(html: str) -> str:
    """Cheap HTML→plain-text for the multipart/alternative part. A mail with *only* an HTML body
    scores worse with spam filters; every send gets a text alternative, either one a caller supplied
    or this stripped-down fallback. Not a full renderer — drops markup, keeps link targets, collapses
    whitespace."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    # Surface href targets so links survive as readable URLs in the text part.
    text = re.sub(r'(?i)<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|h1|h2|h3|li)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


# One (bill, its changes) tuple in a consolidated alert. `litigation_context` is the pre-rendered
# per-bill litigation block (may be empty).
AlertItem = tuple[Bill, list[BillChange], str]

_ALERT_COLOPHON = "You're receiving this because you subscribed to Atlas Circular bill alerts."


def _bill_block(bill: Bill, changes: list[BillChange], litigation_context: str = "") -> str:
    """Render one bill's section (heading, changes, metadata, CTA) — no shell. Shared by the single
    and consolidated alert builders. The CTA lands in the in-app bill panel (bill_url), consistent
    with the new-bill / welcome / onboarding emails, rather than the external legislature page."""
    state_name = bill.state
    bill_num = bill.bill_number or "Unknown"
    title = bill.title or "Untitled"

    change_lines = ""
    for c in changes:
        if c.change_type == "status_change":
            old = (c.old_value or {}).get("status", "unknown")
            new = (c.new_value or {}).get("status", "unknown")
            change_lines += f"<li><strong>Status changed:</strong> {old} → <strong>{new}</strong></li>"
        elif c.change_type == "text_update":
            change_lines += "<li><strong>Bill text updated</strong></li>"

    categories = ", ".join(bill.material_categories or []) or "Not classified"
    confidence_pct = f"{int((bill.confidence_score or 0) * 100)}%"

    summary_html = (
        f'<p style="font:14px {_SERIF};color:{_INK_SOFT};line-height:1.6;background:#fbf7e9;'
        f'border-left:3px solid {_ACCENT};padding:10px 14px;margin:14px 0 0;">{bill.ai_summary}</p>'
        if bill.ai_summary else ""
    )
    litigation_html = (
        f'<div style="font:14px {_SERIF};color:#7f1d1d;background:#fdf1f1;border:1px solid #f3c9c9;'
        f'border-radius:4px;padding:10px 14px;margin:14px 0 0;white-space:pre-line;">'
        f"{_linkify(litigation_context)}</div>"
        if litigation_context else ""
    )
    # Primary CTA in-app; the external legislature link rides along as a muted secondary link.
    source_link = (
        f'<a href="{bill.source_url}" style="color:{_MUTED};text-decoration:underline;font:13px {_SERIF};'
        f'margin-left:14px;">View on the legislature site</a>'
        if bill.source_url else ""
    )
    return f"""
    <h2 style="font:bold 18px {_SERIF};color:{_INK};margin:6px 0 4px;">{state_name} — {bill_num}</h2>
    <p style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.6;margin:0 0 12px;">{title}</p>
    <ul style="font:15px {_SERIF};color:{_INK};line-height:1.7;margin:0 0 4px;padding-left:20px;">
      {change_lines}
    </ul>
    <table style="width:100%;border-collapse:collapse;font:13px {_SERIF};color:{_MUTED};margin-top:10px;
        border-top:1px solid {_RULE};padding-top:8px;">
      <tr>
        <td style="padding-top:8px;"><strong>Materials:</strong> {categories}</td>
        <td style="padding-top:8px;text-align:right;"><strong>Confidence:</strong> {confidence_pct}</td>
      </tr>
    </table>
    {summary_html}
    {litigation_html}
    <p style="margin:18px 0 0;">{cta_button(bill_url(bill.id), "View bill →")}{source_link}</p>"""


DEFAULT_TEXT_ALERT_CTA = "Read more at Atlas Circular →"


def build_text_alert_html(
    body_text: str,
    cta_url: str | None = None,
    cta_label: str = DEFAULT_TEXT_ALERT_CTA,
    kicker: str | None = None,
    preheader: str | None = None,
    unsubscribe_url: str | None = None,
    subscribe_url: str | None = None,
) -> str:
    """The HTML body for a non-bill alert (litigation events). Module-level so the sample/preview
    script and tests can render it without going near SendGrid.

    No tagline: the kicker already classifies the message, and "Tracking the circular economy" under
    a wordmark the reader has just read is a third label for the same thing.
    """
    cta = f'<p style="margin:20px 0 0;">{cta_button(cta_url, cta_label)}</p>' if cta_url else ""
    body = (
        f'<div style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;'
        f'white-space:pre-line;">{_linkify(body_text)}</div>{cta}'
    )
    return render_shell(
        body,
        tagline=None,
        kicker=kicker,
        preheader=preheader,
        colophon="You're receiving this because you subscribed to Atlas Circular litigation alerts.",
        unsubscribe_url=unsubscribe_url,
        subscribe_url=subscribe_url,
    )


def _build_email_html(bill: Bill, changes: list[BillChange], litigation_context: str = "") -> str:
    return render_shell(
        _bill_block(bill, changes, litigation_context=litigation_context),
        tagline="EPR Legislative Update",
        colophon=_ALERT_COLOPHON,
    )


def _alert_kicker(today: date | None = None) -> str:
    """Edition line for the bill alerts — same shape as the litigation one."""
    stamp = (today or date.today()).strftime("%d %B %Y").lstrip("0").upper()
    return f"LEGISLATIVE UPDATE · {stamp}"


def _alert_preheader(items: list[AlertItem]) -> str:
    """Inbox preview text: name the movement, not the publication.

    The subject says how many bills moved; this says WHICH one and what happened to it, because that
    is what decides whether the reader opens now or later.
    """
    bill = items[0][0]
    lead = f"{bill.state} {bill.bill_number or 'bill'}"
    status = (bill.status or "").replace("_", " ") or "updated"
    if len(items) == 1:
        return f"{lead} is now {status} — the change, the materials it covers, and what's next."
    return f"{lead} is now {status}, plus {len(items) - 1} more in your scope."


def _build_consolidated_html(
    items: list[AlertItem], unsubscribe_url: str | None = None
) -> str:
    """One email covering every bill that moved for a single recipient this cycle. Blocks are joined
    by a rule so the recipient gets one message, not one per bill."""
    divider = f'<div style="border-top:1px solid {_RULE};margin:22px 0 0;"></div>'
    body = divider.join(_bill_block(b, ch, lit) for b, ch, lit in items)
    return render_shell(
        body,
        tagline=None,
        kicker=_alert_kicker(),
        preheader=_alert_preheader(items),
        colophon=_ALERT_COLOPHON,
        unsubscribe_url=unsubscribe_url,
        subscribe_url=subscribe_url("bill_alert_forward"),
        referral=True,
    )


def _consolidated_subject(items: list[AlertItem]) -> str:
    if len(items) == 1:
        bill = items[0][0]
        return f"{bill.state} {bill.bill_number or 'Bill'} — Legislative Update"
    return f"{len(items)} bills you follow moved"


class EmailSender:
    """Every outbound message goes through here. Stateless — the token is read per send, so a
    settings change (or a test monkeypatching it) takes effect without re-instantiating."""

    async def send_html(
        self,
        to_email: str,
        subject: str,
        html: str,
        list_unsubscribe_url: str | None = None,
        text: str | None = None,
        from_email: str | None = None,
    ) -> bool:
        """Send a fully-rendered HTML email (e.g. the monthly digest).

        Always multipart/alternative: pass `text` for a hand-written plain-text part, otherwise one is
        derived from the HTML (an HTML-only body scores worse with spam filters). Pass
        `list_unsubscribe_url` for the recurring/marketing emails so mail clients render a native
        unsubscribe control and Gmail/Outlook honour one-click (RFC 8058).

        `from_email` overrides the sending identity for one send — e.g. a founder-voice broadcast as
        hello@. A verified DOMAIN in Postmark covers every local-part on atlascircular.com, so no new
        DNS is needed; a single verified sender signature would not. Use it sparingly: the automated
        cycles should stay on the default identity, which is the one with the warmed reputation.
        Replies go to email_reply_to regardless of who the mail is from."""
        payload = _build_payload(
            to_email,
            subject,
            html,
            # A caller-supplied text part skips the HTML, so it'd otherwise ship without the sender
            # identity the HTML footer carries; derived parts already include it via html_to_text.
            (text + identity_text()) if text else html_to_text(html),
            from_email=from_email,
            list_unsubscribe_url=list_unsubscribe_url,
        )
        return await _post(payload, "email_html")

    async def send_text_alert(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        cta_url: str | None = None,
        cta_label: str = DEFAULT_TEXT_ALERT_CTA,
        kicker: str | None = None,
        preheader: str | None = None,
        unsubscribe_url: str | None = None,
        subscribe_url: str | None = None,
        from_email: str | None = None,
    ) -> bool:
        """Send a plain-text/HTML alert not tied to a Bill object (e.g., litigation events).

        `body_text` is channel-neutral prose — the same string goes to Slack — so any URL in it
        arrives as bare text. Email needs anchors, hence _linkify. `cta_url` renders the primary
        in-app button; litigation alerts pass the case's Atlas Circular page so the reader lands on
        our analysis and follows the CourtListener link from there, rather than being handed straight
        to an external docket. `kicker`/`preheader`/`unsubscribe_url`/`subscribe_url` pass through to
        the shell — see render_shell.
        """
        html = build_text_alert_html(
            body_text,
            cta_url=cta_url,
            cta_label=cta_label,
            kicker=kicker,
            preheader=preheader,
            unsubscribe_url=unsubscribe_url,
            subscribe_url=subscribe_url,
        )
        # The plain-text part keeps the bare URL so the CTA isn't lost on a text-only client.
        text_part = f"{body_text}\n\n{cta_label.rstrip(' →')}: {cta_url}" if cta_url else body_text
        if unsubscribe_url:
            text_part += f"\n\nUnsubscribe: {unsubscribe_url}"
        text_part += identity_text()
        # An unsubscribe URL both sets the RFC 8058 one-click header (matching the body's button —
        # bulk-ish mail without it is penalised by Gmail/Outlook) and routes the send to the
        # broadcast stream. See _stream_for.
        payload = _build_payload(
            to_email,
            subject,
            html,
            text_part,
            from_email=from_email,
            list_unsubscribe_url=unsubscribe_url,
        )
        return await _post(payload, "email_text_alert")

    async def send_consolidated_alert(
        self,
        to_email: str,
        items: list[AlertItem],
        list_unsubscribe_url: str | None = None,
    ) -> bool:
        """Send ONE email covering every bill that moved for this recipient this cycle. `items` is a
        list of (bill, changes, litigation_context). Passes the List-Unsubscribe header so the
        real-time channel matches the digest/new-bill emails' one-click unsubscribe."""
        if not items:
            return False
        subject = _consolidated_subject(items)
        # The header and the in-body button carry the same token, so the two unsubscribe routes can't
        # disagree.
        html_content = _build_consolidated_html(items, unsubscribe_url=list_unsubscribe_url)
        return await self.send_html(
            to_email, subject, html_content, list_unsubscribe_url=list_unsubscribe_url
        )

    async def send_alert(
        self,
        to_email: str,
        bill: Bill,
        changes: list[BillChange],
        litigation_context: str = "",
        list_unsubscribe_url: str | None = None,
    ) -> bool:
        """Single-bill alert — thin wrapper over the consolidated path so both share one renderer."""
        return await self.send_consolidated_alert(
            to_email,
            [(bill, changes, litigation_context)],
            list_unsubscribe_url=list_unsubscribe_url,
        )
