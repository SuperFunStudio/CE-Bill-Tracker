"""Mirror the NON-US region corpus (EU + foreign national law) from a source DB (dev) to a target DB
(prod), so the multi-region product can graduate to prod without re-paying for LLM classification.

Why non-US only: prod already holds the *pristine, fuller* US corpus (more relevant bills + ~89% text
coverage than dev's partial US mirror). The EU/foreign bills key on celex_id/foreign_id and never on
openstates_id, so they can NEVER collide with prod's US rows — this script inserts a disjoint set and
leaves every US row untouched.

What it copies: `bills` (all columns except the serial id) + their `bill_texts`. compliance_details
(Sonnet detail + management_model) rides along as a bills column. Compliance pathways/deadlines are
rebuilt separately on the target via scripts/build_compliance_pathways.py --region, the same way they
were built on dev.

Idempotent: within one transaction it deletes the target's existing non-US rows (dependents first,
then bills) and re-inserts from source. On a first run the target has zero non-US rows, so the delete
is a no-op. Mapping is by source bill.id -> new target id (per-row INSERT ... RETURNING), which is
robust regardless of which natural key a given foreign row uses.

Usage (both DBs reachable via Cloud SQL Auth Proxy):
    venv/Scripts/python scripts/mirror_regions_to_prod.py \
        --source-dsn "postgresql://signalscout:PW@127.0.0.1:5434/signalscout_dev" \
        --target-dsn "postgresql://signalscout:PW@127.0.0.1:5436/signalscout" [--regions EU,FR,JP] [--dry-run]
"""
import argparse
import asyncio

import asyncpg

# Tables that FK-reference bills(bill_id) and may hold non-US rows from a prior run. Deleted (scoped to
# the non-US bill set) before the bills themselves so the bills delete doesn't trip an FK. bill_outcome
# is handled specially (two FK columns). On a first run all of these are empty for non-US bills.
_BILL_DEPENDENTS = [
    "bill_texts", "compliance_deadlines", "compliance_pathway", "classification_changes",
    "bill_changes", "bill_fee_citation", "bill_design_signal", "bill_product_coverage",
    "exposure_brief", "impact_score", "user_watchlist",
]


async def _columns(conn, table):
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name=$1 ORDER BY ordinal_position",
        table,
    )
    return [r["column_name"] for r in rows]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dsn", required=True, help="Source DB DSN (dev), via the auth proxy.")
    ap.add_argument("--target-dsn", required=True, help="Target DB DSN (prod), via the auth proxy.")
    ap.add_argument("--regions", default=None,
                    help="CSV of non-US regions to mirror (default: every region except US present in source).")
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing.")
    args = ap.parse_args()

    src = await asyncpg.connect(args.source_dsn)
    tgt = await asyncpg.connect(args.target_dsn)
    try:
        # Guard: never allow US into the set — this script is non-US only by contract.
        if args.regions:
            regions = [r.strip().upper() for r in args.regions.split(",") if r.strip() and r.strip().upper() != "US"]
            region_pred = "region = ANY($1::text[])"
            region_arg = [regions]
        else:
            region_pred = "region <> 'US'"
            region_arg = []

        bill_cols = await _columns(src, "bills")
        assert bill_cols == await _columns(tgt, "bills"), "bills schema mismatch between source and target"
        insert_cols = [c for c in bill_cols if c != "id"]

        src_bills = await src.fetch(
            f"SELECT id, {', '.join(insert_cols)} FROM bills WHERE {region_pred} ORDER BY id",
            *region_arg,
        )
        src_ids = [b["id"] for b in src_bills]
        by_region = {}
        for b in src_bills:
            by_region.setdefault(b["region"], [0, 0])
            by_region[b["region"]][0] += 1
            if b["ce_relevant"]:
                by_region[b["region"]][1] += 1
        print(f"source: {len(src_bills)} non-US bills across {len(by_region)} regions")
        for r in sorted(by_region, key=lambda k: -by_region[k][1]):
            print(f"  {r:4} total={by_region[r][0]:5} relevant={by_region[r][1]:5}")

        # text_tsv is a GENERATED ALWAYS column (derived from text) — Postgres recomputes it on the
        # target, so it must be excluded from both the SELECT and the INSERT.
        bt_cols = [c for c in await _columns(src, "bill_texts") if c != "text_tsv"]
        src_texts = await src.fetch(
            f"SELECT bt.{', bt.'.join(bt_cols)} FROM bill_texts bt "
            f"JOIN bills b ON bt.bill_id=b.id WHERE b.{region_pred}",
            *region_arg,
        ) if src_ids else []
        print(f"source: {len(src_texts)} bill_texts rows for those bills")

        tgt_us_before = await tgt.fetchval("SELECT count(*) FROM bills WHERE region='US'")
        tgt_nonus_before = await tgt.fetchval("SELECT count(*) FROM bills WHERE region<>'US'")
        print(f"target before: US={tgt_us_before} non-US={tgt_nonus_before}")

        if args.dry_run:
            print("DRY RUN: would delete target non-US rows then insert the above. US rows untouched.")
            return

        bt_placeholders = ", ".join(f"${i+1}" for i in range(len(bt_cols)))

        async with tgt.transaction():
            # Delete existing non-US rows (dependents first), scoped to the non-US bill set only.
            nonus_ids = [r["id"] for r in await tgt.fetch(f"SELECT id FROM bills WHERE {region_pred}", *region_arg)]
            if nonus_ids:
                for t in _BILL_DEPENDENTS:
                    await tgt.execute(f"DELETE FROM {t} WHERE bill_id = ANY($1::int[])", nonus_ids)
                await tgt.execute(
                    "DELETE FROM bill_outcome WHERE bill_id = ANY($1::int[]) OR remediated_by_bill_id = ANY($1::int[])",
                    nonus_ids,
                )
                await tgt.execute("DELETE FROM litigation_cases WHERE related_law_id = ANY($1::int[])", nonus_ids)
                await tgt.execute(f"DELETE FROM bills WHERE {region_pred}", *region_arg)

            # Insert bills one-by-one, mapping source id -> new target id.
            insert_sql = (
                f"INSERT INTO bills ({', '.join(insert_cols)}) "
                f"VALUES ({', '.join('$' + str(i + 1) for i in range(len(insert_cols)))}) RETURNING id"
            )
            id_map = {}
            for b in src_bills:
                new_id = await tgt.fetchval(insert_sql, *[b[c] for c in insert_cols])
                id_map[b["id"]] = new_id
            print(f"inserted {len(id_map)} non-US bills")

            # Insert bill_texts, remapping bill_id.
            bid_i = bt_cols.index("bill_id")
            bt_sql = f"INSERT INTO bill_texts ({', '.join(bt_cols)}) VALUES ({bt_placeholders})"
            n_texts = 0
            for row in src_texts:
                vals = [row[c] for c in bt_cols]
                vals[bid_i] = id_map.get(row["bill_id"])
                if vals[bid_i] is None:
                    continue
                await tgt.execute(bt_sql, *vals)
                n_texts += 1
            print(f"inserted {n_texts} bill_texts rows")

        # Post-checks (outside the txn).
        us_after = await tgt.fetchval("SELECT count(*) FROM bills WHERE region='US'")
        nonus_after = await tgt.fetchval("SELECT count(*) FROM bills WHERE region<>'US'")
        regs = await tgt.fetch(
            "SELECT region, count(*) n, count(*) FILTER (WHERE ce_relevant) r FROM bills WHERE region<>'US' GROUP BY region ORDER BY r DESC")
        print(f"target after: US={us_after} (must equal {tgt_us_before}) non-US={nonus_after}")
        assert us_after == tgt_us_before, "US row count changed — aborting expectation!"
        for r in regs:
            print(f"  {r['region']:4} total={r['n']:5} relevant={r['r']:5}")
    finally:
        await src.close()
        await tgt.close()


if __name__ == "__main__":
    asyncio.run(main())
