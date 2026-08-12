import re
from datetime import date

import structlog
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

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


def _apply_reply_to(message: Mail) -> None:
    """Route replies to a monitored human mailbox instead of the sending identity.

    Applied to every outbound message: a reader hitting Reply on a transactional email expects to
    reach someone, whether or not that template invited it. Skipped when unconfigured so a deployment
    without the setting sends exactly as before.
    """
    if not settings.sendgrid_reply_to:
        return
    from sendgrid.helpers.mail import ReplyTo

    message.reply_to = ReplyTo(settings.sendgrid_reply_to)


def _apply_tracking(message: Mail) -> None:
    """Turn SendGrid's link rewriting off unless it's explicitly re-enabled.

    Click tracking replaces every href with a redirect through the branded click host
    (url7082.atlascircular.com). That host is serving a certificate that doesn't cover it, so a
    recipient clicking ANY link — "Open your dashboard", a bill deep link, a verification button —
    lands on Chrome's full-page "Your connection is not private" warning instead. Until that cert is
    fixed in SendGrid, sending the real href is strictly better than sending a tracked one: the link
    works, and the message carries no host mismatch for a spam filter to notice.

    Applied to every outbound message, so no send path can quietly keep the rewrite.
    """
    if settings.sendgrid_click_tracking:
        return
    from sendgrid.helpers.mail import ClickTracking, TrackingSettings

    tracking = TrackingSettings()
    # enable_text=False as well — otherwise the plain-text part keeps the rewritten URLs.
    tracking.click_tracking = ClickTracking(enable=False, enable_text=False)
    message.tracking_settings = tracking


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
        return f"[Atlas Circular] {bill.state} {bill.bill_number or 'Bill'} — Legislative Update"
    return f"[Atlas Circular] {len(items)} bills you follow moved"


class SendGridSender:
    def __init__(self):
        self._sg = SendGridAPIClient(api_key=settings.sendgrid_api_key)

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
        hello@. Domain authentication covers every local-part on atlascircular.com, so no new DNS or
        SendGrid setup is needed. Use it sparingly: the automated cycles should stay on the default
        alerts@, which is the address with the warmed reputation. Replies go to sendgrid_reply_to
        regardless of who the mail is from."""
        message = Mail(
            from_email=from_email or settings.sendgrid_from_email,
            to_emails=to_email,
            subject=subject,
            # A caller-supplied text part skips the HTML, so it'd otherwise ship without the sender
            # identity the HTML footer carries; derived parts already include it via html_to_text.
            plain_text_content=(text + identity_text()) if text else html_to_text(html),
            html_content=html,
        )
        if list_unsubscribe_url:
            from sendgrid.helpers.mail import Header

            message.header = Header("List-Unsubscribe", f"<{list_unsubscribe_url}>")
            message.header = Header("List-Unsubscribe-Post", "List-Unsubscribe=One-Click")
        _apply_reply_to(message)
        _apply_tracking(message)
        try:
            response = self._sg.send(message)
            success = response.status_code in (200, 202)
            if not success:
                log.warning("sendgrid_html_failed", status=response.status_code, to=to_email)
            return success
        except Exception as e:
            log.error("sendgrid_html_exception", error=str(e), to=to_email)
            return False

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
        message = Mail(
            from_email=from_email or settings.sendgrid_from_email,
            to_emails=to_email,
            subject=subject,
            plain_text_content=text_part,
            html_content=html,
        )
        if unsubscribe_url:
            # RFC 8058 one-click, matching the body's button — same as the digest/new-bill cycles.
            # Bulk-ish mail without it is penalised by Gmail/Outlook.
            from sendgrid.helpers.mail import Header

            message.header = Header("List-Unsubscribe", f"<{unsubscribe_url}>")
            message.header = Header("List-Unsubscribe-Post", "List-Unsubscribe=One-Click")
        _apply_reply_to(message)
        _apply_tracking(message)
        try:
            response = self._sg.send(message)
            return response.status_code in (200, 202)
        except Exception as e:
            log.error("sendgrid_text_alert_failed", error=str(e), to=to_email)
            return False

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
