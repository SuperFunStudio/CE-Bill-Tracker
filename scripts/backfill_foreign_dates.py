"""Backfill status_date for dateless foreign bills by deriving a YEAR from data we already hold.

Every non-US bill in the corpus is dateless (100% of EU/FR/JP/UK/… rows have status_date IS NULL):
the foreign adapters in app/ingestion/foreign.py + eurlex.py never mapped a source date into the
column, even though the year is recoverable from what we already store. That leaves the by-year charts
(Insights momentum, /research/ask "over time") blind to foreign law — see memory federated-expansion
and the /research year-aggregate work.

This is a METADATA backfill, not a reclassification: it touches ONLY status_date and never re-runs any
LLM. The date is derived, in priority order, from:
  0. DAY-precision date in the title — most civil-law titles state the adoption date as part of the
     formal name ("… of 5 June 2019 on …", "Décret n° 2025-73 du 28 janvier 2025", "Ustawa z dnia
     6 grudnia 2024 r."). This is the only basis that yields a real day, and it is authoritative;
  1. CELEX id      — an EU bill_number like 32023R1542 encodes the year in chars [1:5] (=> 2023);
  2. year in title — the enactment/name year, e.g. "Waste Management Act 2002" (~59% of the gap);
  3. year in bill_number — AU-style ids carry it: F2020L01627, C2004A00697, act-2011-031.
A derived YEAR is stored as status_date = Jan 1 of that year. We deliberately set ONLY status_date
(the column that drives year-bucketed charts and is never rendered as a precise date in the UI) and
leave last_action_date NULL — the UI shows last_action_date as "Last Action: <date>", so a fabricated
precise date there would be misleading. A Jan-1 status_date with a NULL last_action_date is itself the
soft signal that the date is year-only / derived (Bill.date_precision reads exactly that).

--upgrade-precision is a SECOND pass for rows an earlier run already dated year-only: where the title
names a day, it replaces the Jan-1 placeholder with the real date. Two guards make that safe:
  - rows with a non-Jan-1 status_date are never touched (those are real adapter dates); and
  - a cross-YEAR change is applied only when it is the known EU mechanism — an act adopted late in year
    N but numbered in the Official Journal of year N+1 (CELEX 32025R0040, the PPWR, was adopted
    19 December 2024). So stored_year - title_year == 1 with a title month >= October is applied;
    any other disagreement is REPORTED for review and left alone.
That second guard is load-bearing: prod row 52020DC0098 (the Circular Economy Action Plan) has a title
field holding a citation of Directive 2009/125/EC "of 21 October 2009", so an unguarded title-date
overwrite would move it back eleven years. Validated against the 8 non-US rows that carry a real
adapter-sourced date: the parser agrees with 7 and disagrees only on that mis-titled row.

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
from app.ingestion.law_dates import derive_law_year, derive_title_date  # noqa: E402


def _upgrade_verdict(stored: datetime.date, title_date: datetime.date) -> str:
    """'apply' | 'review' for replacing a Jan-1 placeholder with a day-precision title date."""
    if stored.year == title_date.year:
        return "apply"  # pure precision gain
    # An act adopted late in year N is often numbered in the OJ of year N+1; that is the only cross-year
    # disagreement we trust. Anything else means the title is describing some OTHER instrument.
    if stored.year - title_date.year == 1 and title_date.month >= 10:
        return "apply"
    return "review"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing.")
    ap.add_argument("--include-us", action="store_true",
                    help="Also derive for the 51 dateless US rows (default: foreign only).")
    ap.add_argument("--upgrade-precision", action="store_true",
                    help="Second pass: replace an earlier run's Jan-1 year-only placeholder with the "
                         "day-precision date named in the title, where one exists.")
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
            # A day-precision date in the title outranks any year heuristic (and can correct the CELEX
            # numbering year) — see the module docstring in app/ingestion/law_dates.py.
            precise = derive_title_date(r["title"])
            if precise is not None:
                by_source["title-date (day)"] += 1
                by_year[precise.year] += 1
                by_region_hit[r["region"]] += 1
                updates.append((precise, r["id"]))
                continue
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
        pct = f"{hit / total * 100:.0f}%" if total else "n/a"
        print(f"dateless target rows: {total}   derivable: {hit} ({pct})   residual: {total - hit}")
        print("  by source:", dict(by_source.most_common()))
        print("  derived-year distribution (top 12):",
              [(y, n) for y, n in sorted(by_year.items(), reverse=True)][:12])
        print("  residual (still dateless) by region:", dict(by_region_miss.most_common(12)))

        # Second pass: sharpen rows an earlier run left at Jan-1 year-only precision.
        upgrades: list[tuple[datetime.date, int]] = []
        if args.upgrade_precision:
            dated = await conn.fetch(
                f"SELECT id, region, bill_number, title, status_date FROM bills "
                f"WHERE ce_relevant AND status_date IS NOT NULL {where_region} "
                f"AND EXTRACT(MONTH FROM status_date) = 1 AND EXTRACT(DAY FROM status_date) = 1"
            )
            review: list[tuple] = []
            by_region_up = Counter()
            for r in dated:
                precise = derive_title_date(r["title"])
                if precise is None or precise == r["status_date"]:
                    continue
                if _upgrade_verdict(r["status_date"], precise) == "apply":
                    by_region_up[r["region"]] += 1
                    upgrades.append((precise, r["id"]))
                else:
                    review.append((r["region"], r["bill_number"], r["status_date"], precise, r["title"]))

            print(f"\nyear-only (Jan-1) rows scanned: {len(dated)}   "
                  f"upgradable to a day: {len(upgrades)}   held for review: {len(review)}")
            print("  upgrades by region:", dict(by_region_up.most_common()))
            for reg, num, stored, precise, title in review[:15]:
                print(f"  [review] {reg} {num}: {stored} vs title {precise} — {(title or '')[:90]}")
            if review:
                print("  ^ title date disagrees by more than the OJ-numbering slip; left unchanged. "
                      "Usually the title field holds a citation of a DIFFERENT instrument.")

        if args.dry_run:
            print("\n[dry-run] no writes. Re-run without --dry-run to apply.")
            return

        # Guarded by status_date IS NULL so a concurrent write / re-run can't clobber a real date.
        await conn.executemany(
            "UPDATE bills SET status_date = $1 WHERE id = $2 AND status_date IS NULL", updates)
        print(f"\napplied: set status_date on {hit} rows.")
        if upgrades:
            # Re-checks the Jan-1 shape at write time so a real date landing in between is never lost.
            await conn.executemany(
                "UPDATE bills SET status_date = $1 WHERE id = $2 AND status_date IS NOT NULL "
                "AND EXTRACT(MONTH FROM status_date) = 1 AND EXTRACT(DAY FROM status_date) = 1",
                upgrades)
            print(f"applied: upgraded {len(upgrades)} rows from year-only to day precision.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
