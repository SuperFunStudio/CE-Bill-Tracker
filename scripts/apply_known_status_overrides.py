"""Authoritative status overrides for enacted laws that automated sources can't match.

A few flagship laws can't be fixed by the LegiScan sweep (scripts/refresh_status_legiscan.py):
  - NY S-4104: the Digital Fair Repair Act was signed as S4104A (amended number), so the
    base number doesn't match in the session master list.
  - MN SF-1598: the Digital Fair Repair Act was enacted inside the 2023 commerce omnibus,
    so the standalone bill stays "introduced" in every source.

This applies a tiny, explicit override list. Match is by (state, bill_number). Keep this list
short — it's the manual escape hatch for genuine omnibus/amended-number exceptions only.

Usage (local by default; pass --dsn for prod via the Cloud SQL proxy):
    python scripts/apply_known_status_overrides.py [--dsn ...] [--dry-run]
"""
import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

# (state, bill_number, status, status_date, note)
OVERRIDES = [
    ("NY", "S-4104", "enacted", date(2022, 12, 28),
     "Digital Fair Repair Act — signed as S4104A (amended number)."),
    ("MN", "SF-1598", "enacted", date(2023, 5, 24),
     "Digital Fair Repair Act — enacted via 2023 commerce omnibus."),
]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    conn = await asyncpg.connect(dsn)
    try:
        for state, number, status, status_date, note in OVERRIDES:
            rows = await conn.fetch(
                "SELECT id, status FROM bills WHERE state=$1 AND bill_number=$2", state, number,
            )
            if not rows:
                print(f"  WARN no match: {state} {number} — {note}")
                continue
            cur = ", ".join(sorted({r["status"] or "(none)" for r in rows}))
            print(f"  {state} {number}: {cur} -> {status}  ({len(rows)} row(s))  [{note}]")
            if args.dry_run:
                continue
            await conn.execute(
                "UPDATE bills SET status=$1, status_date=$2, ce_relevant=true, updated_at=now() "
                "WHERE state=$3 AND bill_number=$4",
                status, status_date, state, number,
            )
        print("\n(dry run — no changes written)" if args.dry_run else "\noverrides applied")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
