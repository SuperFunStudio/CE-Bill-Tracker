import httpx
import structlog

from app.alerts.applinks import bill_url
from app.models import Bill, BillChange
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

# One (bill, its changes, litigation block) tuple in a consolidated alert.
AlertItem = tuple[Bill, list[BillChange], str]


def _bill_blocks(bill: Bill, changes: list[BillChange], litigation_context: str = "") -> list[dict]:
    """Slack blocks for one bill. The button lands in the in-app bill panel (bill_url), consistent
    with the email alerts and the rest of the notification surface."""
    bill_num = bill.bill_number or "Unknown"
    title = bill.title or "Untitled"
    state = bill.state
    categories = ", ".join(bill.material_categories or []) or "Unclassified"

    change_text = ""
    for c in changes:
        if c.change_type == "status_change":
            old = (c.old_value or {}).get("status", "?")
            new = (c.new_value or {}).get("status", "?")
            change_text += f"• Status: *{old}* → *{new}*\n"
        elif c.change_type == "text_update":
            diff = (c.new_value or {}).get("diff")
            if isinstance(diff, dict) and diff.get("hunks"):
                change_text += (
                    f"• Bill text amended (+{diff.get('added', 0)} / −{diff.get('removed', 0)} lines)\n"
                )
            else:
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
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Bill"},
                "url": bill_url(bill.id),
                "style": "primary",
            }
        ],
    })
    return blocks


def _build_slack_blocks(bill: Bill, changes: list[BillChange], litigation_context: str = "") -> list[dict]:
    return _bill_blocks(bill, changes, litigation_context=litigation_context)


def _build_consolidated_blocks(items: list[AlertItem]) -> list[dict]:
    """One Slack message covering every bill that moved for this webhook this cycle, bills separated
    by a divider."""
    blocks: list[dict] = []
    for i, (bill, changes, litigation) in enumerate(items):
        if i:
            blocks.append({"type": "divider"})
        blocks.extend(_bill_blocks(bill, changes, litigation_context=litigation))
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
    async def send_consolidated_alert(self, webhook_url: str, items: list[AlertItem]) -> bool:
        """Post ONE Slack message covering every bill that moved for this webhook this cycle."""
        if not items:
            return False
        blocks = _build_consolidated_blocks(items)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json={"blocks": blocks})
            if resp.status_code != 200:
                log.warning("slack_send_failed", status=resp.status_code)
                return False
            return True

    async def send_alert(
        self,
        webhook_url: str,
        bill: Bill,
        changes: list[BillChange],
        litigation_context: str = "",
    ) -> bool:
        """Single-bill alert — thin wrapper over the consolidated path."""
        return await self.send_consolidated_alert(
            webhook_url, [(bill, changes, litigation_context)]
        )
