"""Backfill status_date for dateless foreign bills by deriving a YEAR from data we already hold.

Every non-US bill in the corpus is dateless (100% of EU/FR/JP/UK/… rows have status_date IS NULL):
the foreign adapters in app/ingestion/foreign.py + eurlex.py never mapped a source date into the
column, even though the year is recoverable from what we already store. That leaves the by-year charts
(Insights momentum, /research/ask "over time") blind to foreign law — see memory federated-expansion
and the /research year-aggregate work.

This is a METADATA backfill, not a reclassification: it touches ONLY status_date and never re-runs any
LLM. Year is derived, in priority order, from:
  1. CELEX id      — an EU bill_number like 32023R1542 encodes the year in chars [1:5] (=> 2023);
  2. year in title — the enactment/name year, e.g. "Waste Management Act 2002" (~59% of the gap);
  3. year in bill_number — AU-style ids carry it: F2020L01627, C2004A00697, act-2011-031.
The derived value is stored as status_date = Jan 1 of that year. We deliberately set ONLY status_date
(the column that drives year-bucketed charts and is never rendered as a precise date in the UI) and
leave last_action_date NULL — the UI shows last_action_date as "Last Action: <date>", so a fabricated
precise date there would be misleading. A Jan-1 status_date with a NULL last_action_date is itself the
soft signal that the date is year-only / derived.

Heuristic guards: a candidate year must fall in [MIN_YEAR, current year] — this excludes future TARGET
years ("...by 2030/2035"), which is why title/bill_number scanning takes the FIRST in-range 4-digit
token (the name year normally precedes any target year). US rows are skipped by default (their
status_date means "last action"; the 51 dateless US rows are edge cases better fixed at the source).

Idempotent: only rows with status_date IS NULL are ever touched.

    # via the Cloud SQL Auth Proxy (prod is the source of truth — run here first, then sync down):
    venv/Scripts/python.exe scripts/backfill_foreign_dates.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" [--dry-run] [--include-us]

Local default uses the app's DATABASE_URL. --dry-run reports the derived-year distribution and the
residual (still-dateless) rows without writing.
"""
import argparse
import asyncio
import datetime
import sys
from collections import Counter
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

# Single source of truth for the derivation — shared with the forward ingest path (foreign.sync_foreign
# + eurlex.sync_eurlex), so backfilled and newly-ingested dates agree. See app/ingestion/law_dates.py.
from app.ingestion.law_dates import derive_law_year  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing.")
    ap.add_argument("--include-us", action="store_true",
                    help="Also derive for the 51 dateless US rows (default: foreign only).")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    where_region = "" if args.include_us else "AND region <> 'US'"
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            f"SELECT id, region, bill_number, title FROM bills "
            f"WHERE ce_relevant AND status_date IS NULL {where_region}"
        )
        by_source = Counter()
        by_year = Counter()
        by_region_hit = Counter()
        by_region_miss = Counter()
        updates: list[tuple[datetime.date, int]] = []
        for r in rows:
            got = derive_law_year(r["bill_number"], r["title"])
            if got is None:
                by_region_miss[r["region"]] += 1
                continue
            year, src = got
            by_source[src] += 1
            by_year[year] += 1
            by_region_hit[r["region"]] += 1
            updates.append((datetime.date(year, 1, 1), r["id"]))

        total = len(rows)
        hit = len(updates)
        print(f"dateless target rows: {total}   derivable: {hit} ({hit/total*100:.0f}%)   "
              f"residual: {total - hit}")
        print("  by source:", dict(by_source.most_common()))
        print("  derived-year distribution (top 12):",
              [(y, n) for y, n in sorted(by_year.items(), reverse=True)][:12])
        print("  residual (still dateless) by region:", dict(by_region_miss.most_common(12)))

        if args.dry_run:
            print("\n[dry-run] no writes. Re-run without --dry-run to apply.")
            return

        # Guarded by status_date IS NULL so a concurrent write / re-run can't clobber a real date.
        await conn.executemany(
            "UPDATE bills SET status_date = $1 WHERE id = $2 AND status_date IS NULL", updates)
        print(f"\napplied: set status_date on {hit} rows.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
