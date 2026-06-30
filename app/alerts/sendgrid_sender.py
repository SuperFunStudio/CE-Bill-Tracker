import re

import structlog
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

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

    return f"""
<html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <div style="background: #1a4d2e; padding: 16px 24px;">
    <h1 style="color: white; margin: 0; font-size: 20px;">Battle of the Bills</h1>
    <p style="color: #a8d5b5; margin: 4px 0 0;">EPR Legislative Update</p>
  </div>
  <div style="padding: 24px; background: #f9fafb; border: 1px solid #e5e7eb;">
    <h2 style="color: #111827; font-size: 18px; margin-top: 0;">
      {state_name} — {bill_num}
    </h2>
    <p style="color: #374151; font-size: 15px;">{title}</p>
    <ul style="background: #fff; border: 1px solid #d1fae5; border-radius: 6px; padding: 12px 24px;">
      {change_lines}
    </ul>
    <table style="width: 100%; font-size: 13px; color: #6b7280; margin-top: 12px;">
      <tr>
        <td><strong>Materials:</strong> {categories}</td>
        <td><strong>Confidence:</strong> {confidence_pct}</td>
      </tr>
    </table>
    {'<p style="background:#fef9c3;padding:10px;border-radius:4px;font-size:13px;">' + (bill.ai_summary or '') + '</p>' if bill.ai_summary else ''}
    {('<div style="background:#1f1a1a;border:1px solid #7f1d1d;border-radius:6px;padding:10px 14px;margin-top:12px;font-size:13px;color:#fca5a5;white-space:pre-line;">' + litigation_context + '</div>') if litigation_context else ''}
    <a href="{source_url}" style="display:inline-block;margin-top:16px;padding:10px 20px;
       background:#1a4d2e;color:white;text-decoration:none;border-radius:4px;font-size:14px;">
      View Bill →
    </a>
  </div>
  <div style="padding: 12px 24px; font-size: 12px; color: #9ca3af; text-align: center;">
    Battle of the Bills — EPR Legislative Intelligence
  </div>
</body></html>
"""


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
        html = f"""
<html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <div style="background: #1a4d2e; padding: 16px 24px;">
    <h1 style="color: white; margin: 0; font-size: 20px;">Battle of the Bills</h1>
    <p style="color: #a8d5b5; margin: 4px 0 0;">EPR Litigation Update</p>
  </div>
  <div style="padding: 24px; background: #f9fafb; border: 1px solid #e5e7eb; white-space: pre-line;">
    {body_text}
  </div>
  <div style="padding: 12px 24px; font-size: 12px; color: #9ca3af; text-align: center;">
    Battle of the Bills — EPR Legislative Intelligence
  </div>
</body></html>"""
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
        subject = f"[Battle of the Bills] {bill.state} {bill_num} — Legislative Update"
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
