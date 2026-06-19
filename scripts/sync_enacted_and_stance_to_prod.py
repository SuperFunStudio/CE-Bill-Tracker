"""One bundled, surgical prod write: the reconciled enacted corrections + the policy_stance sync.

Two targeted updates, matched by openstates_id, in a single transaction — deliberately NOT a blanket
push_bills_to_prod (that overwrites every prod status with local's, which would regress any bill the
live daily incremental updated more recently than our local snapshot):

  1. enacted corrections — the 87 bills the OpenStates dump confirms were signed but prod's status
     missed (from data/analysis/enacted_reconciliation_prod.json). Only flips rows still != 'enacted'.
  2. policy_stance / stance_source — copied from local (authoritative; we backfilled stance there) so
     the live Insights "policy momentum" chart actually populates (prod had only ~165 of ~1,537).

Usage (Cloud SQL Auth Proxy running to prod):
    python scripts/sync_enacted_and_stance_to_prod.py --prod-dsn "postgresql://signalscout:PW@127.0.0.1:5434/signalscout" [--dry-run]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prod-dsn", required=True, help="Prod Cloud SQL DSN via the auth proxy.")
    ap.add_argument("--local-dsn", default=None, help="Source DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--corrections", default="data/analysis/enacted_reconciliation_prod.json")
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing.")
    args = ap.parse_args()

    if args.local_dsn:
        local_dsn = args.local_dsn
    else:
        from app.config import settings
        local_dsn = settings.database_url

    from app.ingestion.coordinator import _parse_date

    corrections = json.load(open(args.corrections))["corrections"]
    enacted = [(c["openstates_id"], _parse_date(c.get("enacted_date"))) for c in corrections if c.get("openstates_id")]

    local = await asyncpg.connect(local_dsn)
    prod = await asyncpg.connect(args.prod_dsn)
    try:
        stance_rows = await local.fetch(
            "SELECT openstates_id, policy_stance, stance_source FROM bills "
            "WHERE openstates_id IS NOT NULL AND policy_stance IS NOT NULL"
        )
        print(f"enacted corrections to apply: {len(enacted)}")
        print(f"local stance rows to sync:    {len(stance_rows)}")

        if args.dry_run:
            os_ids = [r["openstates_id"] for r in stance_rows]
            would_enact = await prod.fetchval(
                "SELECT count(*) FROM bills WHERE openstates_id = ANY($1::text[]) AND status <> 'enacted'",
                [e[0] for e in enacted],
            )
            stance_now = await prod.fetchval("SELECT count(*) FROM bills WHERE policy_stance IS NOT NULL")
            stance_match = await prod.fetchval(
                "SELECT count(*) FROM bills WHERE openstates_id = ANY($1::text[])", os_ids
            )
            print(f"DRY RUN: would flip {would_enact} prod bills to enacted")
            print(f"DRY RUN: prod policy_stance now {stance_now} -> would set on {stance_match} matched rows")
            return

        async with prod.transaction():
            enacted_applied = 0
            for osid, d in enacted:
                if d is not None:
                    res = await prod.execute(
                        "UPDATE bills SET status='enacted', status_date=$2 "
                        "WHERE openstates_id=$1 AND status <> 'enacted'", osid, d)
                else:
                    res = await prod.execute(
                        "UPDATE bills SET status='enacted' WHERE openstates_id=$1 AND status <> 'enacted'", osid)
                if res.endswith("1"):
                    enacted_applied += 1

            stance_applied = 0
            for r in stance_rows:
                res = await prod.execute(
                    "UPDATE bills SET policy_stance=$2, stance_source=$3 WHERE openstates_id=$1",
                    r["openstates_id"], r["policy_stance"], r["stance_source"])
                if res.endswith("1"):
                    stance_applied += 1

        print(f"APPLIED: {enacted_applied} enacted corrections, {stance_applied} stance updates")
        en = await prod.fetchval("SELECT count(*) FROM bills WHERE ce_relevant AND status='enacted'")
        st = await prod.fetchval("SELECT count(*) FROM bills WHERE ce_relevant AND policy_stance IS NOT NULL")
        print(f"prod after: ce_relevant enacted={en}, with policy_stance={st}")
    finally:
        await local.close()
        await prod.close()


if __name__ == "__main__":
    asyncio.run(main())
