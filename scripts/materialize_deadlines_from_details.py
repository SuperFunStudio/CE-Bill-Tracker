"""Materialize compliance_deadlines rows from ALREADY-STORED compliance_details JSON.

This is the free (no-LLM) counterpart to scripts/backfill_deadlines.py. That script runs a
fresh Sonnet extraction per bill; this one reuses the extraction already sitting in
bills.compliance_details, so it costs nothing and is safe to re-run.

Why it's needed: the Sonnet dimension backfill populated compliance_details for thousands of
bills, but the compliance_deadlines TABLE (what the "Upcoming Deadlines" page reads) was only
materialized for a small subset. The dated deadlines are already in the JSON — they just were
never written out as rows on this DB.

For each bill with compliance_details it rebuilds that bill's deadline rows (DELETE then INSERT,
same replace-semantics as backfill_deadlines.py) from three sources in the stored JSON:
  - compliance_details.deadlines[]  -> one row each ({date,type,description})
  - compliance_details.effective_date -> an 'effective' row
  - compliance_details.compliance_date -> a 'compliance' row
Rows are deduped per (date, type). region is set from bills.region (so EU/foreign deadlines are
tagged correctly, not left at the US default).

Usage (via the Cloud SQL Auth Proxy):
    venv/Scripts/python scripts/materialize_deadlines_from_details.py \
        --dsn "postgresql://signalscout:PW@127.0.0.1:5462/signalscout" --dry-run
    venv/Scripts/python scripts/materialize_deadlines_from_details.py --dsn "..."   # apply
"""
import argparse
import asyncio
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))


def _parse_date(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _rows_for(details, bill_number):
    """Return deduped [(deadline_type, date, description)] from one bill's compliance_details."""
    out = []
    for dl in (details.get("deadlines") or []):
        if not isinstance(dl, dict):
            continue
        d = _parse_date(dl.get("date"))
        if d:
            out.append((dl.get("type") or "compliance", d, dl.get("description") or ""))
    eff = _parse_date(details.get("effective_date"))
    if eff:
        out.append(("effective", eff, f"{bill_number or 'Bill'} takes effect"))
    comp = _parse_date(details.get("compliance_date"))
    if comp:
        out.append(("compliance", comp, f"{bill_number or 'Bill'} compliance date"))
    seen, deduped = set(), []
    for dtype, ddate, desc in out:
        k = (ddate, dtype)
        if k in seen:
            continue
        seen.add(k)
        deduped.append((dtype, ddate, desc))
    return deduped


async def main():
    import json
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True, help="Target DSN via the auth proxy.")
    ap.add_argument("--dry-run", action="store_true", help="Report the delta; no writes.")
    args = ap.parse_args()

    c = await asyncpg.connect(args.dsn)
    try:
        before_total = await c.fetchval("select count(*) from compliance_deadlines")
        before_future = await c.fetchval("select count(*) from compliance_deadlines where deadline_date>=current_date")

        bills = await c.fetch(
            "select id, region, state, bill_number, source_url, compliance_details "
            "from bills where compliance_details is not null")

        would_insert = 0
        would_delete = 0
        by_region = Counter()
        future_rows = 0
        touched_bills = 0

        # In dry-run we just tally. In apply mode we do per-bill DELETE+INSERT in one transaction.
        tx = None if args.dry_run else c.transaction()
        if tx:
            await tx.start()
        try:
            for b in bills:
                details = b["compliance_details"]
                if isinstance(details, str):
                    details = json.loads(details)
                if not isinstance(details, dict):  # stored jsonb 'null' passes IS NOT NULL
                    details = {}
                rows = _rows_for(details, b["bill_number"])
                existing = await c.fetchval(
                    "select count(*) from compliance_deadlines where bill_id=$1", b["id"])
                if not rows and not existing:
                    continue
                touched_bills += 1
                would_delete += existing
                would_insert += len(rows)
                for dtype, ddate, desc in rows:
                    by_region[b["region"]] += 1
                    if ddate >= date.today():
                        future_rows += 1
                if not args.dry_run:
                    await c.execute("delete from compliance_deadlines where bill_id=$1", b["id"])
                    for dtype, ddate, desc in rows:
                        await c.execute(
                            "insert into compliance_deadlines "
                            "(bill_id,state,deadline_type,deadline_date,description,source_url,region) "
                            "values ($1,$2,$3,$4,$5,$6,$7)",
                            b["id"], b["state"], dtype, ddate, desc, b["source_url"], b["region"])
            if tx:
                await tx.commit()
        except Exception:
            if tx:
                await tx.rollback()
            raise

        print(f"bills with compliance_details: {len(bills)}")
        print(f"bills touched (had rows or produced rows): {touched_bills}")
        print(f"rows deleted (rebuild): {would_delete}")
        print(f"rows inserted: {would_insert}  (of which future-dated: {future_rows})")
        print("inserted rows by region:")
        for reg, n in by_region.most_common():
            print(f"  {reg:4} {n}")
        if args.dry_run:
            print(f"\nDRY RUN — no writes. Table would go {before_total} -> {would_insert} total "
                  f"({before_future} -> {future_rows} future).")
        else:
            after_total = await c.fetchval("select count(*) from compliance_deadlines")
            after_future = await c.fetchval("select count(*) from compliance_deadlines where deadline_date>=current_date")
            print(f"\nAPPLIED. compliance_deadlines: {before_total} -> {after_total} total "
                  f"({before_future} -> {after_future} future).")
    finally:
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
