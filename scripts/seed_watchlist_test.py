"""Set up a LOCAL *watchlist* subscription and fire a status-change so you can see the real-time
watch-list alert email (the dispatcher path) — distinct from the new-bill / deadline Gazette emails.

What it sets up in the local DB:
  - a watchlist-scope AlertSubscription (firebase_uid=TEST_UID, your email, min_confidence 0,
    alert_on includes "status_change") — the delivery row for a Pro personal watch list,
  - a user_watchlist row putting one real bill on that watch list,
  - a BillChange (status_change, e.g. in_committee -> passed) on the watched bill, alert_sent=False.

A watchlist subscription matches ONLY its starred bills (its empty filter columns are NOT match-all),
so this is the clean way to see a single watched bill trigger an alert.

Safe by default: with no flags it is a DRY RUN — it renders the alert HTML to
tmp/watchlist_alert_<email>.html, prints the subject, and sends NOTHING. Pass --send to run the real
AlertDispatcher, which delivers to your inbox via SendGrid and marks the change alert_sent.

    venv/Scripts/python scripts/seed_watchlist_test.py                 # dry run (writes HTML)
    venv/Scripts/python scripts/seed_watchlist_test.py --send          # actually email me
    venv/Scripts/python scripts/seed_watchlist_test.py --bill-id 47742 # watch a different bill
    venv/Scripts/python scripts/seed_watchlist_test.py --cleanup       # remove all test rows
"""
import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_UID = "test-watchlist-uid"
DEFAULT_EMAIL = "kenny@superfun.studio"
DEFAULT_BILL_ID = 47725  # CA AB-1343 — PaintCare (recognizable CA EPR program)
SENTINEL = "_synthetic_test"  # tags the BillChange rows this script creates, for clean teardown
SYNTH_BILL_PREFIX = "[SYNTHETIC TEST]"  # the seed_test_email_scenario.py marker, cleared too


def _slug(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", email)


async def cleanup(db) -> None:
    """Reset to a clean slate: remove both this script's rows AND the new-bill/deadline scenario's,
    so a --send dispatch can only ever reach the one watchlist subscriber we just created."""
    from sqlalchemy import delete, or_, select

    from app.models import AlertSubscription, Bill, BillChange, ComplianceDeadline, WatchlistItem

    # Our synthetic status-change rows (tagged in new_value).
    await db.execute(
        delete(BillChange).where(BillChange.new_value[SENTINEL].astext == "true")
    )
    await db.execute(delete(WatchlistItem).where(WatchlistItem.firebase_uid == TEST_UID))

    # The other script's synthetic bill + deadline, so no stray match remains.
    synth_bill_ids = (
        await db.execute(select(Bill.id).where(Bill.title.like(f"{SYNTH_BILL_PREFIX}%")))
    ).scalars().all()
    if synth_bill_ids:
        await db.execute(
            delete(ComplianceDeadline).where(ComplianceDeadline.bill_id.in_(synth_bill_ids))
        )
        await db.execute(delete(Bill).where(Bill.id.in_(synth_bill_ids)))

    # Every test subscriber (this watchlist sub + the catch-all filter sub).
    await db.execute(
        delete(AlertSubscription).where(
            or_(
                AlertSubscription.firebase_uid == TEST_UID,
                AlertSubscription.email == "test+emailpreview@superfun.studio",
            )
        )
    )
    await db.commit()
    print("Cleaned up all local test subscriptions, watch-list rows, and synthetic bills/changes.")


async def setup(db, email: str, bill_id: int, old_status: str, new_status: str):
    from sqlalchemy import select

    from app.models import AlertSubscription, Bill, BillChange, WatchlistItem

    await cleanup(db)  # start from a clean slate so re-runs don't pile up

    bill = (await db.execute(select(Bill).where(Bill.id == bill_id))).scalar_one_or_none()
    if bill is None:
        print(f"ERROR: no bill with id={bill_id}.", file=sys.stderr)
        return None

    db.add(
        AlertSubscription(
            firebase_uid=TEST_UID,
            email=email,
            organization="Watchlist Test",
            scope="watchlist",
            states=[],            # watchlist scope ignores these
            instrument_types=[],
            material_categories=[],
            min_confidence=0.0,   # a starred bill alerts regardless of classifier score
            alert_on=["status_change", "new_bill", "deadline"],
            active=True,
        )
    )
    db.add(WatchlistItem(firebase_uid=TEST_UID, bill_id=bill.id))

    change = BillChange(
        bill_id=bill.id,
        change_type="status_change",
        old_value={"status": old_status, SENTINEL: True},
        new_value={"status": new_status, SENTINEL: True},
        alert_sent=False,
    )
    db.add(change)
    await db.commit()
    await db.refresh(change)

    print("Set up watch-list scenario:")
    print(f"  subscriber : {email}  (scope=watchlist, firebase_uid={TEST_UID})")
    print(f"  watching   : id={bill.id}  {bill.state} {bill.bill_number}  ({(bill.title or '')[:60]})")
    print(f"  triggered  : status_change {old_status} -> {new_status}  (change id={change.id})")
    return bill, change


async def run(email: str, bill_id: int, old_status: str, new_status: str, send: bool) -> int:
    from app.alerts.sendgrid_sender import _build_email_html
    from app.config import settings
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await setup(db, email, bill_id, old_status, new_status)
        if result is None:
            return 1
        bill, change = result
        subject = f"[SignalScout] {bill.state} {bill.bill_number or 'Bill'} — Legislative Update"

        if not send:
            out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
            os.makedirs(out_dir, exist_ok=True)
            html = _build_email_html(bill, [change])
            path = os.path.join(out_dir, f"watchlist_alert_{_slug(email)}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"\nDRY RUN — subject: {subject}")
            print(f"Wrote preview to {os.path.relpath(path)}. Re-run with --send to email it.")
            return 0

        if not settings.sendgrid_api_key:
            print("ERROR: --send given but SENDGRID_API_KEY is not set.", file=sys.stderr)
            return 1

        # Run the REAL dispatcher over just our change, so it exercises is_alert_worthy + watch-list
        # matching exactly as the cron would. After cleanup, the only active sub is ours, so this can
        # only reach `email`.
        from app.alerts.dispatcher import AlertDispatcher

        await AlertDispatcher().dispatch_changes(db, [change])
        await db.refresh(change)
        status = "sent (alert_sent=True)" if change.alert_sent else "NOT sent"
        print(f"\nSENT via dispatcher — subject: {subject}")
        print(f"Dispatch result for change id={change.id}: {status}. Check {email}.")
        return 0


async def main() -> int:
    from app.database import AsyncSessionLocal

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--email", default=DEFAULT_EMAIL, help="Recipient (default: %(default)s).")
    ap.add_argument("--bill-id", type=int, default=DEFAULT_BILL_ID,
                    help="Bill to put on the watch list (default: %(default)s = CA AB-1343).")
    ap.add_argument("--old-status", default="in_committee", help="Prior status for the change.")
    ap.add_argument("--new-status", default="passed",
                    help="New status (must be a significant status to alert; default: passed).")
    ap.add_argument("--send", action="store_true",
                    help="Actually run the dispatcher and email (default is a dry run).")
    ap.add_argument("--cleanup", action="store_true", help="Remove the test rows and exit.")
    args = ap.parse_args()

    if args.cleanup:
        async with AsyncSessionLocal() as db:
            await cleanup(db)
        return 0
    return await run(args.email, args.bill_id, args.old_status, args.new_status, args.send)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
