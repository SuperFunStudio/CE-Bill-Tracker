import re

import structlog
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.alerts.email_shell import (
    _ACCENT,
    _INK,
    _INK_SOFT,
    _MUTED,
    _RULE,
    _SERIF,
    cta_button,
    render_shell,
)
from app.config import settings
from app.models import Bill, BillChange

log = structlog.get_logger()


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


def _build_email_html(bill: Bill, changes: list[BillChange], litigation_context: str = "") -> str:
    state_name = bill.state
    bill_num = bill.bill_number or "Unknown"
    title = bill.title or "Untitled"
    source_url = bill.source_url or "#"

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
        f"{litigation_context}</div>"
        if litigation_context else ""
    )
    body = f"""
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
    <p style="margin:18px 0 0;">{cta_button(source_url, "View bill →")}</p>"""
    return render_shell(
        body,
        tagline="EPR Legislative Update",
        colophon="You're receiving this because you subscribed to Atlas Circular bill alerts.",
    )


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
    ) -> bool:
        """Send a fully-rendered HTML email (e.g. the monthly digest).

        Always multipart/alternative: pass `text` for a hand-written plain-text part, otherwise one is
        derived from the HTML (an HTML-only body scores worse with spam filters). Pass
        `list_unsubscribe_url` for the recurring/marketing emails so mail clients render a native
        unsubscribe control and Gmail/Outlook honour one-click (RFC 8058)."""
        message = Mail(
            from_email=settings.sendgrid_from_email,
            to_emails=to_email,
            subject=subject,
            plain_text_content=text or html_to_text(html),
            html_content=html,
        )
        if list_unsubscribe_url:
            from sendgrid.helpers.mail import Header

            message.header = Header("List-Unsubscribe", f"<{list_unsubscribe_url}>")
            message.header = Header("List-Unsubscribe-Post", "List-Unsubscribe=One-Click")
        try:
            response = self._sg.send(message)
            success = response.status_code in (200, 202)
            if not success:
                log.warning("sendgrid_html_failed", status=response.status_code, to=to_email)
            return success
        except Exception as e:
            log.error("sendgrid_html_exception", error=str(e), to=to_email)
            return False

    async def send_text_alert(self, to_email: str, subject: str, body_text: str) -> bool:
        """Send a plain-text/HTML alert not tied to a Bill object (e.g., litigation events)."""
        body = (
            f'<div style="font:15px {_SERIF};color:{_INK_SOFT};line-height:1.65;'
            f'white-space:pre-line;">{body_text}</div>'
        )
        html = render_shell(
            body,
            tagline="EPR Litigation Update",
            colophon="You're receiving this because you subscribed to Atlas Circular litigation alerts.",
        )
        message = Mail(
            from_email=settings.sendgrid_from_email,
            to_emails=to_email,
            subject=subject,
            plain_text_content=body_text,
            html_content=html,
        )
        try:
            response = self._sg.send(message)
            return response.status_code in (200, 202)
        except Exception as e:
            log.error("sendgrid_text_alert_failed", error=str(e), to=to_email)
            return False

    async def send_alert(
        self,
        to_email: str,
        bill: Bill,
        changes: list[BillChange],
        litigation_context: str = "",
    ) -> bool:
        bill_num = bill.bill_number or "Bill"
        subject = f"[Atlas Circular] {bill.state} {bill_num} — Legislative Update"
        html_content = _build_email_html(bill, changes, litigation_context=litigation_context)

        message = Mail(
            from_email=settings.sendgrid_from_email,
            to_emails=to_email,
            subject=subject,
            plain_text_content=html_to_text(html_content),
            html_content=html_content,
        )
        try:
            response = self._sg.send(message)
            success = response.status_code in (200, 202)
            if not success:
                log.warning("sendgrid_send_failed", status=response.status_code, to=to_email)
            return success
        except Exception as e:
            log.error("sendgrid_exception", error=str(e), to=to_email)
            return False
