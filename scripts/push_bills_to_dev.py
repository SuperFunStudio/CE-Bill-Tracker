"""Mirror the local bills corpus up to the DEV Cloud SQL database, region-scoped and safe for the
multi-region dev DB (EU/JP/… rows are never touched).

This is the local→dev half of the working model: bulk downloads + classification happen on LOCAL
Postgres first, then this pushes a region's corpus up to dev (signalscout_dev) so all regions can be
queried/compared together. It generalizes scripts/push_bills_to_prod.py with one critical change —
the "hide stale rows" step is scoped to the mirrored region, so mirroring US can't clobber the EU/JP
relevance flags that live only on dev.

Keyed on openstates_id (US's stable id), so re-runs update in place (FK refs preserved) and it never
overwrites the target's compliance_details (preserve any Sonnet output already there).

Usage (Cloud SQL Auth Proxy on 127.0.0.1:5434):
    venv/Scripts/python scripts/push_bills_to_dev.py \
        --dev-dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout_dev" [--dry-run]
    # default mirrors region US; --region for another local region that uses openstates_id.

Local source DSN defaults to the app's DATABASE_URL.
"""
import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

# Columns copied local -> dev. Excludes id (serial PK). compliance_details (the Sonnet extraction +
# management_model) is copied only with --with-compliance-details — needed so US pathways/deadlines +
# the covered_products comparison work on dev (the initial US load has none to preserve). Includes
# region so inserts land in the right jurisdiction family.
_BASE_COLS = [
    "openstates_id", "region", "state", "bill_number", "title", "description", "status",
    "status_date", "last_action_date", "source_url", "change_hash", "last_fetched_at",
    "ce_relevant", "confidence_score", "material_categories", "instrument_type",
    "urgency", "ai_summary",
]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dev-dsn", required=True, help="Dev Cloud SQL DSN (via the auth proxy).")
    ap.add_argument("--local-dsn", default=None, help="Source DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--region", default="US", help="Region to mirror (default US).")
    ap.add_argument("--with-compliance-details", action="store_true",
                    help="Also copy compliance_details (Sonnet detail + management_model).")
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing.")
    args = ap.parse_args()
    region = args.region.upper()
    cols = _BASE_COLS + (["compliance_details"] if args.with_compliance_details else [])
    update_cols = [c for c in cols if c != "openstates_id"]

    if args.local_dsn:
        local_dsn = args.local_dsn
    else:
        from app.config import settings
        local_dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

    local = await asyncpg.connect(local_dsn)
    dev = await asyncpg.connect(args.dev_dsn)
    try:
        # Local source set: this region's bills keyed on openstates_id (US's authoritative id).
        rows = await local.fetch(
            f"SELECT {', '.join(cols)} FROM bills "
            f"WHERE openstates_id IS NOT NULL AND region = $1",
            region,
        )
        local_os_ids = [r["openstates_id"] for r in rows]
        local_rel = sum(1 for r in rows if r["ce_relevant"])
        print(f"local {region}: {len(rows)} bills with openstates_id ({local_rel} ce_relevant)")

        before = await dev.fetchrow(
            "SELECT count(*) t, count(*) FILTER (WHERE ce_relevant) r FROM bills WHERE region=$1",
            region,
        )
        other = await dev.fetchrow(
            "SELECT count(*) t, count(*) FILTER (WHERE ce_relevant) r FROM bills WHERE region<>$1",
            region,
        )
        print(f"dev before: {region}={before['t']} ({before['r']} rel) | other-regions={other['t']} ({other['r']} rel)")

        if args.dry_run:
            overlap = await dev.fetchval(
                "SELECT count(*) FROM bills WHERE openstates_id = ANY($1::text[])", local_os_ids
            )
            print(f"DRY RUN: would upsert {len(rows)} ({overlap} update / {len(rows)-overlap} insert); "
                  f"hide-stale scoped to region={region} only")
            return

        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        insert_sql = (
            f"INSERT INTO bills ({', '.join(cols)}) "
            f"VALUES ({', '.join('$' + str(i + 1) for i in range(len(cols)))}) "
            f"ON CONFLICT (openstates_id) DO UPDATE SET {set_clause}"
        )
        async with dev.transaction():
            await dev.executemany(insert_sql, [[r[c] for c in cols] for r in rows])
        print(f"upserted {len(rows)} {region} bills into dev")

        # Hide stale rows — SCOPED TO THIS REGION so EU/JP (other regions) are never touched.
        hidden = await dev.execute(
            "UPDATE bills SET ce_relevant = false "
            "WHERE region = $1 AND ce_relevant AND legiscan_bill_id IS NULL "
            "AND NOT (openstates_id = ANY($2::text[]))",
            region, local_os_ids,
        )
        print(f"hid stale {region} rows: {hidden}")

        after = await dev.fetchrow(
            "SELECT count(*) t, count(*) FILTER (WHERE ce_relevant) r FROM bills WHERE region=$1",
            region,
        )
        other_after = await dev.fetchrow(
            "SELECT count(*) t, count(*) FILTER (WHERE ce_relevant) r FROM bills WHERE region<>$1",
            region,
        )
        print(f"dev after: {region}={after['t']} ({after['r']} rel) | "
              f"other-regions={other_after['t']} ({other_after['r']} rel) [must be unchanged]")
    finally:
        await local.close()
        await dev.close()


if __name__ == "__main__":
    asyncio.run(main())
