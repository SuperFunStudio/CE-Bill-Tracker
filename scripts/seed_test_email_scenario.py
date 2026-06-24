"""Seed a self-contained, synthetic scenario for previewing the bill-driven alert emails LOCALLY.

This inserts, into whatever DATABASE_URL points at:
  - one catch-all *test* subscriber (states/topics/materials = ALL, confidence floor 0),
  - one synthetic, relevant, not-yet-alerted Bill (so it satisfies _load_new_bills' window), and
  - one ComplianceDeadline tied to that bill, due inside the reminder lead window.

That's exactly what the new-bill alert and deadline-reminder dry-runs need to draft an email. Every
test row is tagged so this is idempotent and fully reversible:
  - the bill's title is prefixed with the SENTINEL,
  - the subscriber uses the dedicated TEST_EMAIL.

Usage:
    venv/Scripts/python scripts/seed_test_email_scenario.py            # (re)seed; prints IDs
    venv/Scripts/python scripts/seed_test_email_scenario.py --cleanup  # remove all test rows

Then preview (no email is sent; HTML is written to tmp/):
    venv/Scripts/python scripts/send_new_bill_alerts.py --email test+emailpreview@superfun.studio
    venv/Scripts/python scripts/send_deadline_alerts.py --email test+emailpreview@superfun.studio
"""
import argparse
import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SENTINEL = "[SYNTHETIC TEST]"
TEST_EMAIL = "test+emailpreview@superfun.studio"


async def cleanup(db) -> None:
    from sqlalchemy import delete, select

    from app.models import AlertSubscription, Bill, ComplianceDeadline

    test_bill_ids = (
        await db.execute(select(Bill.id).where(Bill.title.like(f"{SENTINEL}%")))
    ).scalars().all()
    if test_bill_ids:
        await db.execute(
            delete(ComplianceDeadline).where(ComplianceDeadline.bill_id.in_(test_bill_ids))
        )
        await db.execute(delete(Bill).where(Bill.id.in_(test_bill_ids)))
    await db.execute(delete(AlertSubscription).where(AlertSubscription.email == TEST_EMAIL))
    await db.commit()
    print(f"Removed {len(test_bill_ids)} test bill(s), their deadlines, and the test subscriber.")


async def seed(db) -> None:
    from app.models import AlertSubscription, Bill, ComplianceDeadline

    await cleanup(db)  # start clean so re-runs don't pile up

    today = date.today()

    sub = AlertSubscription(
        email=TEST_EMAIL,
        organization="Synthetic Test",
        scope="filter",
        states=["ALL"],
        instrument_types=["ALL"],
        material_categories=["ALL"],
        min_confidence=0.0,
        alert_on=["status_change", "new_bill", "deadline"],
        active=True,
    )
    db.add(sub)

    bill = Bill(
        # legiscan_bill_id / openstates_id left NULL so this can't collide with a real upsert.
        state="CA",
        bill_number="SB 999",
        title=f"{SENTINEL} Extended Producer Responsibility for Packaging and Paper Products",
        description=(
            "Establishes an EPR program requiring producers of covered packaging and paper to join "
            "a producer responsibility organization and fund collection and recycling."
        ),
        status="introduced",
        status_date=today,
        last_action_date=today,
        source_url="https://example.com/synthetic-test-bill",
        ce_relevant=True,            # required by _load_new_bills
        new_bill_alert_sent=False,   # eligible
        confidence_score=0.95,       # above any floor
        material_categories=["packaging", "paper"],
        instrument_type="epr",
        urgency="high",
        ai_summary=(
            "Synthetic test bill: producers of covered packaging must register with a PRO and fund "
            "recycling. Used to preview the alert emails; not real legislation."
        ),
        reviewed=False,
    )
    db.add(bill)
    await db.flush()  # get bill.id

    deadline = ComplianceDeadline(
        bill_id=bill.id,
        state="CA",
        deadline_type="compliance",
        deadline_date=today + timedelta(days=14),
        description=(
            "Producers of covered packaging must register with the selected PRO and submit an "
            "initial compliance plan."
        ),
        who_affected="Producers selling covered packaging or paper products into California.",
        source_url="https://example.com/synthetic-test-bill#deadline",
        reminder_sent=False,
    )
    db.add(deadline)
    await db.commit()

    print("Seeded synthetic scenario:")
    print(f"  subscriber : {TEST_EMAIL} (catch-all, active)")
    print(f"  bill       : id={bill.id}  CA SB 999  (ce_relevant, created today)")
    print(f"  deadline   : id={deadline.id}  due {deadline.deadline_date.isoformat()} (in 14 days)")
    print("\nPreview the drafts (nothing is sent):")
    print(f"  venv/Scripts/python scripts/send_new_bill_alerts.py --email {TEST_EMAIL}")
    print(f"  venv/Scripts/python scripts/send_deadline_alerts.py --email {TEST_EMAIL}")


async def main() -> int:
    from app.database import AsyncSessionLocal

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--cleanup", action="store_true", help="Remove the test rows and exit.")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        if args.cleanup:
            await cleanup(db)
        else:
            await seed(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
