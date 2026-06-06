import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.detector import ChangeDetector
from app.alerts.sendgrid_sender import SendGridSender
from app.alerts.slack_sender import SlackSender
from app.config import settings
from app.models import AlertSubscription, Bill, BillChange, LitigationCase

log = structlog.get_logger()


async def _get_litigation_context(db: AsyncSession, bill_id: int) -> str:
    """Return a litigation context block if active cases exist for this bill."""
    result = await db.execute(
        select(LitigationCase).where(
            LitigationCase.related_law_id == bill_id,
            LitigationCase.case_status.in_(["active", "injunction_granted", "appealed"]),
        )
    )
    cases = result.scalars().all()
    if not cases:
        return ""

    lines = []
    for case in cases:
        injunction_flag = ""
        if case.case_status == "injunction_granted":
            injunction_flag = " 🚨 ENFORCEMENT STAYED"
        cl_link = f" — {case.cl_url}" if case.cl_url else ""
        lines.append(
            f"• {case.case_name}{injunction_flag} "
            f"[{case.court_id.upper() if case.court_id else 'Federal Court'}]{cl_link} "
            f"(Risk: {case.preemption_risk or 0}/100)"
        )

    return "\n\n⚖️ Active Federal Litigation:\n" + "\n".join(lines)


class AlertDispatcher:
    def __init__(self):
        self.detector = ChangeDetector()
        self.email_sender = SendGridSender()
        self.slack_sender = SlackSender()

    async def dispatch_changes(
        self, db: AsyncSession, changes: list[BillChange]
    ) -> None:
        for change in changes:
            # Load the associated bill
            bill_result = await db.execute(
                select(Bill).where(Bill.id == change.bill_id)
            )
            bill = bill_result.scalar_one_or_none()
            if not bill:
                continue

            if not self.detector.is_alert_worthy(change, bill):
                change.alert_sent = True  # Mark as handled (not worth alerting)
                continue

            # Find matching subscriptions
            subs = await self._subscriptions_for_bill(db, bill)
            if not subs:
                change.alert_sent = True
                continue

            # Gather litigation context once per bill
            litigation_context = await _get_litigation_context(db, bill.id)

            for sub in subs:
                if not sub.active:
                    continue
                if change.change_type not in (sub.alert_on or []):
                    continue
                if (bill.confidence_score or 0) < (sub.min_confidence or 0):
                    continue

                # Send email
                if sub.email and settings.sendgrid_api_key:
                    await self.email_sender.send_alert(
                        sub.email, bill, [change], litigation_context=litigation_context
                    )

                # Send Slack
                if sub.slack_webhook:
                    await self.slack_sender.send_alert(
                        sub.slack_webhook, bill, [change], litigation_context=litigation_context
                    )

            change.alert_sent = True
            log.info(
                "alert_dispatched",
                bill_id=bill.id,
                change_type=change.change_type,
                subscriber_count=len(subs),
            )

        await db.commit()

    async def _subscriptions_for_bill(
        self, db: AsyncSession, bill: Bill
    ) -> list[AlertSubscription]:
        result = await db.execute(
            select(AlertSubscription).where(AlertSubscription.active == True)
        )
        all_subs = result.scalars().all()

        matching = []
        for sub in all_subs:
            states = sub.states or []
            if "ALL" not in states and bill.state not in states:
                continue
            mat_cats = sub.material_categories or []
            bill_cats = bill.material_categories or []
            if "ALL" not in mat_cats and not any(c in mat_cats for c in bill_cats):
                continue
            matching.append(sub)
        return matching
