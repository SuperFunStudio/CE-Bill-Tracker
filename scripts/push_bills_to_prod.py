"""One-off / repeatable sync of the local bills table up to production Cloud SQL.

Reads the locally-built, classified bills (correct OpenStates URLs) and upserts them into
the production database by `openstates_id`. This is keyed on openstates_id (a stable string),
NOT the integer PK, so it:
  - updates existing prod rows in place -> their `id` is preserved -> FK references
    (compliance_deadlines, impact_score, exposure_brief, litigation_cases) stay intact;
  - inserts bills prod doesn't have yet;
  - does NOT overwrite prod's `compliance_details` (prod has Sonnet extractions we didn't
    re-run locally), and never touches LegiScan rows.

After upserting, any prod bill that is NOT in our clean set is marked ce_relevant=false so
the dashboard shows exactly our curated set (no stale, bad-URL rows leaking through).

Usage (with the Cloud SQL Auth Proxy running on some local port):
    python scripts/push_bills_to_prod.py \
        --prod-dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" \
        [--dry-run]

Local source DSN defaults to the app's DATABASE_URL.
"""
import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

# Columns copied local -> prod. Deliberately excludes id (serial PK) and compliance_details
# (preserve prod's Sonnet output).
_COLS = [
    "openstates_id", "state", "bill_number", "title", "description", "status",
    "status_date", "last_action_date", "source_url", "change_hash", "last_fetched_at",
    "ce_relevant", "confidence_score", "material_categories", "instrument_type",
    "urgency", "ai_summary",
]
_UPDATE_COLS = [c for c in _COLS if c != "openstates_id"]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prod-dsn", required=True, help="Cloud SQL DSN (via the auth proxy).")
    ap.add_argument("--local-dsn", default=None, help="Source DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing.")
    args = ap.parse_args()

    if args.local_dsn:
        local_dsn = args.local_dsn
    else:
        from app.config import settings
        local_dsn = settings.database_url

    local = await asyncpg.connect(local_dsn)
    prod = await asyncpg.connect(args.prod_dsn)
    try:
        # Pull every locally-built bill that has an openstates_id (our authoritative set).
        rows = await local.fetch(
            f"SELECT {', '.join(_COLS)} FROM bills WHERE openstates_id IS NOT NULL"
        )
        local_os_ids = [r["openstates_id"] for r in rows]
        local_relevant = sum(1 for r in rows if r["ce_relevant"])
        print(f"local: {len(rows)} bills with openstates_id ({local_relevant} ce_relevant)")

        prod_before = await prod.fetchrow(
            "SELECT count(*) total, count(*) FILTER (WHERE ce_relevant) rel, "
            "count(*) FILTER (WHERE legiscan_bill_id IS NULL AND openstates_id IS NULL) seed "
            "FROM bills"
        )
        print(f"prod before: total={prod_before['total']} ce_relevant={prod_before['rel']} "
              f"seed={prod_before['seed']}")

        if args.dry_run:
            overlap = await prod.fetchval(
                "SELECT count(*) FROM bills WHERE openstates_id = ANY($1::text[])", local_os_ids
            )
            print(f"DRY RUN: would upsert {len(rows)} bills "
                  f"({overlap} already exist on prod -> update, {len(rows) - overlap} -> insert)")
            stale = await prod.fetchval(
                "SELECT count(*) FROM bills WHERE ce_relevant AND legiscan_bill_id IS NULL "
                "AND NOT (openstates_id = ANY($1::text[]))", local_os_ids
            )
            print(f"DRY RUN: would hide {stale} stale ce_relevant prod rows not in our set")
            return

        # Upsert by openstates_id.
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in _UPDATE_COLS)
        insert_sql = (
            f"INSERT INTO bills ({', '.join(_COLS)}) "
            f"VALUES ({', '.join('$' + str(i + 1) for i in range(len(_COLS)))}) "
            f"ON CONFLICT (openstates_id) DO UPDATE SET {set_clause}"
        )
        upserted = 0
        async with prod.transaction():
            for r in rows:
                await prod.execute(insert_sql, *[r[c] for c in _COLS])
                upserted += 1
        print(f"upserted {upserted} bills into prod")

        # Hide any stale prod EPR rows that aren't in our clean set (keep LegiScan untouched —
        # there are none on prod anyway).
        hidden = await prod.execute(
            "UPDATE bills SET ce_relevant = false "
            "WHERE ce_relevant AND legiscan_bill_id IS NULL "
            "AND NOT (openstates_id = ANY($1::text[]))",
            local_os_ids,
        )
        print(f"hid stale prod rows: {hidden}")

        prod_after = await prod.fetchrow(
            "SELECT count(*) total, count(*) FILTER (WHERE ce_relevant) rel, "
            "count(*) FILTER (WHERE ce_relevant AND (source_url IS NULL OR source_url='' "
            "OR source_url LIKE 'ftp://%' OR source_url LIKE '%.xml')) bad_url FROM bills"
        )
        print(f"prod after: total={prod_after['total']} ce_relevant={prod_after['rel']} "
              f"ce_relevant_with_bad_url={prod_after['bad_url']}")
    finally:
        await local.close()
        await prod.close()


if __name__ == "__main__":
    asyncio.run(main())
