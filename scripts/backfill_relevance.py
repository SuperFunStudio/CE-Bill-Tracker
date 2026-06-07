"""Backfill epr_relevant for bills already tagged with a tracked policy instrument.

The classifier historically set epr_relevant=False for right-to-repair / deposit-return /
etc. because they aren't EPR in the strict sense, so the EPR-only dashboard hid them
(e.g. CA SB-244 "Right to Repair Act"). The pipeline now treats any tracked instrument as
in scope (see app/classification/haiku_classifier.TRACKED_INSTRUMENTS); this script applies
the same rule to existing rows.

Purely additive: only flips epr_relevant False -> True for rows with a tracked
instrument_type and confidence_score >= 0.4. Never clears relevance.

Run against LOCAL first, then re-run push_bills_to_prod.py, OR point --dsn straight at prod
via the Cloud SQL Auth Proxy:
    python scripts/backfill_relevance.py --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" [--dry-run]

Local default uses the app's DATABASE_URL.
"""
import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.haiku_classifier import TRACKED_INSTRUMENTS  # noqa: E402

MIN_CONFIDENCE = 0.4


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    instruments = sorted(TRACKED_INSTRUMENTS)
    conn = await asyncpg.connect(dsn)
    try:
        where = (
            "epr_relevant = false "
            "AND confidence_score >= $1 "
            "AND instrument_type = ANY($2::text[])"
        )
        to_flip = await conn.fetch(
            f"SELECT state, instrument_type, count(*) AS n FROM bills WHERE {where} "
            "GROUP BY state, instrument_type ORDER BY n DESC",
            MIN_CONFIDENCE, instruments,
        )
        total = sum(r["n"] for r in to_flip)
        by_instr: dict[str, int] = {}
        for r in to_flip:
            by_instr[r["instrument_type"]] = by_instr.get(r["instrument_type"], 0) + r["n"]

        print(f"{total} bills would flip epr_relevant -> True")
        for instr, n in sorted(by_instr.items(), key=lambda x: -x[1]):
            print(f"  {instr:22s} {n}")

        if args.dry_run:
            print("\n(dry run — no changes written)")
            return

        updated = await conn.execute(
            f"UPDATE bills SET epr_relevant = true, updated_at = now() WHERE {where}",
            MIN_CONFIDENCE, instruments,
        )
        print(f"\napplied: {updated}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
