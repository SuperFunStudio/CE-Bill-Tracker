"""Hide bills that are only in scope because of an instrument we no longer track.

Some instrument_types used to flag bills as ce_relevant=True even though they aren't
circular-economy legislation:
  - chemical_restriction: chemical-safety/health bills like CA SB-236 (hair relaxer ingredients)
  - budget: generic appropriations

These are excluded from app/classification/haiku_classifier.TRACKED_INSTRUMENTS; this script
applies the same rule to existing rows. Inverse of backfill_relevance.py: only flips
ce_relevant True -> False for rows whose instrument_type is in the target set. Every other
instrument is untouched.

Run against LOCAL first, then re-run push_bills_to_prod.py, OR point --dsn straight at prod
via the Cloud SQL Auth Proxy:
    python scripts/hide_untracked_instruments.py --dsn "postgresql://signalscout@127.0.0.1:5434/signalscout" [--dry-run]

Local default uses the app's DATABASE_URL.
"""
import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

DEFAULT_INSTRUMENTS = ["chemical_restriction", "budget"]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument(
        "--instruments",
        default=",".join(DEFAULT_INSTRUMENTS),
        help="Comma-separated instrument_types to hide.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing.")
    args = ap.parse_args()

    instruments = [s.strip() for s in args.instruments.split(",") if s.strip()]

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    where = "ce_relevant = true AND instrument_type = ANY($1::text[])"
    conn = await asyncpg.connect(dsn)
    try:
        to_hide = await conn.fetch(
            f"SELECT instrument_type, count(*) AS n FROM bills WHERE {where} "
            "GROUP BY instrument_type ORDER BY n DESC",
            instruments,
        )
        total = sum(r["n"] for r in to_hide)
        print(f"{total} bills would flip ce_relevant -> False (instruments={instruments})")
        for r in to_hide:
            print(f"  {r['instrument_type']:22s} {r['n']}")

        if args.dry_run:
            print("\n(dry run — no changes written)")
            return

        updated = await conn.execute(
            f"UPDATE bills SET ce_relevant = false, updated_at = now() WHERE {where}",
            instruments,
        )
        print(f"\napplied: {updated}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
