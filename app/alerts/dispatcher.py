import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.detector import ChangeDetector
from app.alerts.digest import load_watchlists, subscription_matches_bill
from app.alerts.retention import filter_retained_subscriptions
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

            # One notification per recipient per change: a subscriber who matches this bill via both
            # their watch list and their topic filters (two rows) should get a single email/Slack.
            emailed: set[str] = set()
            slacked: set[str] = set()
            for sub in subs:
                if not sub.active:
                    continue
                if change.change_type not in (sub.alert_on or []):
                    continue
                if (bill.confidence_score or 0) < (sub.min_confidence or 0):
                    continue

                # Send email
                if sub.email and settings.sendgrid_api_key and sub.email.lower() not in emailed:
                    await self.email_sender.send_alert(
                        sub.email, bill, [change], litigation_context=litigation_context
                    )
                    emailed.add(sub.email.lower())

                # Send Slack
                if sub.slack_webhook and sub.slack_webhook not in slacked:
                    await self.slack_sender.send_alert(
                        sub.slack_webhook, bill, [change], litigation_context=litigation_context
                    )
                    slacked.add(sub.slack_webhook)

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
        # Honour the retention promise: a lapsed-trial account's alerts stop after a year, while a
        # live Pro seat (and every anonymous newsletter sub) keeps flowing. See alerts/retention.py.
        all_subs = await filter_retained_subscriptions(db, list(result.scalars().all()))

        # Resolve watch-list membership for the owners of any watchlist subscriptions, so a starred
        # bill reaches its follower regardless of the filter columns. Loaded once per bill.
        watchlists = await load_watchlists(
            db, {s.firebase_uid for s in all_subs if s.scope == "watchlist" and s.firebase_uid}
        )

        # Single source of truth with the digest: filter subs match on states + instrument_types
        # (topics) + materials + confidence floor; watchlist subs match on the explicit bill set.
        # Previously this filtered only on states + materials — so it ignored the topic every real
        # subscriber actually picks, and an empty material list wrongly excluded every bill (an empty
        # filter should mean "all", which _matches_list handles).
        return [
            sub
            for sub in all_subs
            if subscription_matches_bill(
                sub,
                bill,
                watchlists.get(sub.firebase_uid) if sub.scope == "watchlist" else None,
            )
        ]
