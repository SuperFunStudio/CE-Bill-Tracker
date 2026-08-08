import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.applinks import litigation_case_url
from app.alerts.detector import ChangeDetector
from app.alerts.digest import load_watchlists, subscription_matches_bill
from app.alerts.retention import filter_retained_subscriptions
from app.alerts.sendgrid_sender import SendGridSender
from app.alerts.slack_sender import SlackSender
from app.alerts.unsubscribe import unsubscribe_url
from app.config import settings
from app.models import AlertSubscription, Bill, BillChange, LitigationCase

log = structlog.get_logger()


async def _get_litigation_context(db: AsyncSession, bill_id: int) -> str:
    """Return a litigation context block if active cases exist for this bill."""
    result = await db.execute(
        select(LitigationCase).where(
            LitigationCase.related_law_id == bill_id,
            LitigationCase.case_status.in_(["active", "injunction_granted", "appealed"]),
            # Only cases the relevance gate cleared — a bill alert must not tell a compliance team
            # their law is being litigated on the strength of an unrelated docket.
            LitigationCase.ce_relevant.is_(True),
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
        # The case's Atlas Circular page, not case.cl_url: it carries the docket timeline, the
        # preemption analysis and an onward CourtListener link. Bare URL because this block is shared
        # verbatim with Slack; the email sender linkifies it. See applinks.litigation_case_url.
        lines.append(
            f"• {case.case_name}{injunction_flag} "
            f"[{case.court_id.upper() if case.court_id else 'Federal Court'}] "
            f"(Risk: {case.preemption_risk or 0}/100)\n"
            f"  {litigation_case_url(case.id)}"
        )

    return "\n\n⚖️ Active Federal Litigation:\n" + "\n".join(lines)


class _Bundle:
    """Accumulates the bills — and the specific changes — one recipient should hear about this cycle.

    Deduped by bill id so two matching subscription rows for the same address (e.g. a filter row and a
    watch-list row) don't list a bill twice; changes are unioned by object identity so a recipient
    whose subscriptions asked for different change types on the same bill gets all of them once. `sub`
    is the first contributing subscription row — used for the recipient address and unsubscribe id.
    """

    def __init__(self, sub: AlertSubscription):
        self.sub = sub
        self._order: list[int] = []
        self._by_bill: dict[int, tuple[Bill, dict[int, BillChange], str]] = {}

    def add(self, bill: Bill, changes: list[BillChange], litigation: str) -> None:
        entry = self._by_bill.get(bill.id)
        if entry is None:
            entry = (bill, {}, litigation)
            self._by_bill[bill.id] = entry
            self._order.append(bill.id)
        change_map = entry[1]
        for c in changes:
            change_map[id(c)] = c  # BillChange may be unpersisted (id None); dedup by identity

    def items(self) -> list[tuple[Bill, list[BillChange], str]]:
        return [
            (bill, list(change_map.values()), litigation)
            for bid in self._order
            for bill, change_map, litigation in (self._by_bill[bid],)
        ]


class AlertDispatcher:
    def __init__(self):
        self.detector = ChangeDetector()
        self.email_sender = SendGridSender()
        self.slack_sender = SlackSender()

    async def dispatch_changes(
        self, db: AsyncSession, changes: list[BillChange]
    ) -> None:
        """Consolidate a cycle's alert-worthy changes into ONE message per recipient.

        Previously this sent one email/Slack per BillChange, so a subscriber whose watch list saw ten
        bills move in a single cycle got ten separate emails. Now we group the alert-worthy changes by
        bill, match each bill to its subscribers once, accumulate every (bill, changes) a recipient
        should hear about, and send a single consolidated message — the same one-message-per-recipient
        shape the digest and new-bill cycles already use. Every processed change is marked
        alert_sent regardless of send outcome (as before), so a transient send failure can't loop it.
        """
        # 1) Keep only alert-worthy changes, grouped by bill. Non-worthy changes are marked handled.
        changes_by_bill: dict[int, list[BillChange]] = {}
        bills_by_id: dict[int, Bill] = {}
        for change in changes:
            bill = (
                await db.execute(select(Bill).where(Bill.id == change.bill_id))
            ).scalar_one_or_none()
            if not bill:
                continue
            if not self.detector.is_alert_worthy(change, bill):
                change.alert_sent = True  # not worth alerting
                continue
            changes_by_bill.setdefault(bill.id, []).append(change)
            bills_by_id[bill.id] = bill

        if not changes_by_bill:
            await db.commit()
            return

        # 2) Build per-recipient bundles. A bundle collects, per bill, the changes this recipient's
        #    filters actually asked for (alert_on) — keyed by email (case-insensitively) and by Slack
        #    webhook, so two matching subscription rows for one address still yield a single message.
        email_bundles: dict[str, _Bundle] = {}
        slack_bundles: dict[str, _Bundle] = {}
        litigation_by_bill: dict[int, str] = {}

        for bill_id, bill_changes in changes_by_bill.items():
            bill = bills_by_id[bill_id]
            subs = await self._subscriptions_for_bill(db, bill)
            if not subs:
                continue
            for sub in subs:
                if not sub.active:
                    continue
                # Per-change: only the change types this subscriber opted into, above their floor.
                if (bill.confidence_score or 0) < (sub.min_confidence or 0):
                    continue
                wanted = [c for c in bill_changes if c.change_type in (sub.alert_on or [])]
                if not wanted:
                    continue

                if bill_id not in litigation_by_bill:
                    litigation_by_bill[bill_id] = await _get_litigation_context(db, bill_id)
                litigation = litigation_by_bill[bill_id]

                if sub.email and settings.sendgrid_api_key:
                    email_bundles.setdefault(sub.email.lower(), _Bundle(sub)).add(
                        bill, wanted, litigation
                    )
                if sub.slack_webhook:
                    slack_bundles.setdefault(sub.slack_webhook, _Bundle(sub)).add(
                        bill, wanted, litigation
                    )

        # 3) One consolidated send per recipient.
        for bundle in email_bundles.values():
            await self.email_sender.send_consolidated_alert(
                bundle.sub.email,
                bundle.items(),
                list_unsubscribe_url=unsubscribe_url(bundle.sub.id),
            )
        for webhook, bundle in slack_bundles.items():
            await self.slack_sender.send_consolidated_alert(webhook, bundle.items())

        # 4) Mark every processed change handled and persist.
        for bill_changes in changes_by_bill.values():
            for change in bill_changes:
                change.alert_sent = True
        await db.commit()
        log.info(
            "alert_dispatched",
            bills=len(changes_by_bill),
            changes=sum(len(v) for v in changes_by_bill.values()),
            email_recipients=len(email_bundles),
            slack_recipients=len(slack_bundles),
        )

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
