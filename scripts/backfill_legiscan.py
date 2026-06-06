"""
Search LegiScan for each seeded law to attach legiscan_bill_id for ongoing change tracking.

Usage:
    python scripts/backfill_legiscan.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    from app.database import AsyncSessionLocal
    from app.ingestion.legiscan import LegiScanClient
    from app.models import Bill
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Bill).where(
                Bill.legiscan_bill_id.is_(None),
                Bill.epr_relevant == True,
            )
        )
        bills = result.scalars().all()
        print(f"Found {len(bills)} seeded bills without LegiScan IDs")

        async with LegiScanClient() as legiscan:
            for bill in bills:
                if not bill.bill_number or bill.bill_number.startswith("PaintCare"):
                    continue  # Skip non-LegiScan entries
                query = f"{bill.state} {bill.bill_number}"
                try:
                    results = await legiscan.search(query, state=bill.state)
                    if results:
                        first = results[0]
                        bill_id = first.get("bill_id")
                        if bill_id:
                            bill.legiscan_bill_id = int(bill_id)
                            print(f"  Matched {bill.state} {bill.bill_number} → LegiScan ID {bill_id}")
                except Exception as e:
                    print(f"  Failed for {bill.bill_number}: {e}")

        await db.commit()
        print("Backfill complete")


if __name__ == "__main__":
    asyncio.run(main())
