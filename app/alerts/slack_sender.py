import httpx
import structlog

from app.models import Bill, BillChange
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()


def _build_slack_blocks(bill: Bill, changes: list[BillChange], litigation_context: str = "") -> list[dict]:
    bill_num = bill.bill_number or "Unknown"
    title = bill.title or "Untitled"
    state = bill.state
    categories = ", ".join(bill.material_categories or []) or "Unclassified"
    source_url = bill.source_url or ""

    change_text = ""
    for c in changes:
        if c.change_type == "status_change":
            old = (c.old_value or {}).get("status", "?")
            new = (c.new_value or {}).get("status", "?")
            change_text += f"• Status: *{old}* → *{new}*\n"
        elif c.change_type == "text_update":
            change_text += "• Bill text updated\n"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📋 {state} {bill_num} — Legislative Update"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{title}*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": change_text or "No changes"},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Materials: {categories}"},
                {"type": "mrkdwn", "text": f"Confidence: {int((bill.confidence_score or 0) * 100)}%"},
            ],
        },
    ]
    if litigation_context:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": litigation_context},
        })
    if source_url:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Bill"},
                    "url": source_url,
                    "style": "primary",
                }
            ],
        })
    return blocks


class SlackSender:
    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    async def send_text_alert(self, webhook_url: str, text: str) -> bool:
        """Send a plain-text Slack message not tied to a Bill object (e.g., litigation events)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
            if resp.status_code != 200:
                log.warning("slack_text_alert_failed", status=resp.status_code)
                return False
            return True

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    async def send_alert(
        self,
        webhook_url: str,
        bill: Bill,
        changes: list[BillChange],
        litigation_context: str = "",
    ) -> bool:
        blocks = _build_slack_blocks(bill, changes, litigation_context=litigation_context)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json={"blocks": blocks})
            if resp.status_code != 200:
                log.warning("slack_send_failed", status=resp.status_code)
                return False
            return True
