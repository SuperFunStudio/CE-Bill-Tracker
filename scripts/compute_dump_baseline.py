"""Compute the all-bills passage-rate baseline + CE champion roster from a restored OpenStates dump.

Both are READ-ONLY over the dump and run NO classification (see app/ingestion/dump_analytics.py).
Restore the dump first (selective restore is enough — see app/ingestion/openstates_pgdump.py):

    createdb openstates_dump
    pg_restore --no-owner --no-acl -d openstates_dump \
      -t opencivicdata_bill -t opencivicdata_legislativesession \
      -t opencivicdata_billsponsorship -t opencivicdata_person \
      -t opencivicdata_membership -t opencivicdata_organization \
      "2026-06-public.pgdump"

Usage:
    python scripts/compute_dump_baseline.py --inspect                 # verify tables/columns FIRST
    python scripts/compute_dump_baseline.py --baseline-only           # just the passage-rate table
    python scripts/compute_dump_baseline.py --roster-only             # just the champion roster
    python scripts/compute_dump_baseline.py --since-year 2019         # both -> data/analysis/*.json
    python scripts/compute_dump_baseline.py --states CA,OR,WA,NY      # restrict baseline states

Writes data/analysis/passage_rate_baseline.json and ce_champion_roster.json.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dump-dsn",
        # Same default as scripts/import_openstates_pgdump.py — the dump restores into a PG18 server
        # on :5433; the app's own DB stays on :5432.
        default="postgresql://postgres:dev@localhost:5433/openstates_dump",
        help="DSN of the restored OpenStates dump database.",
    )
    parser.add_argument("--since-year", type=int, default=2019,
                        help="Only count sessions starting this year or later (matches our CE cohort window).")
    parser.add_argument("--states", default=None,
                        help="Comma-separated state codes to restrict the baseline to (default: all).")
    parser.add_argument("--out-dir", default="data/analysis", help="Where to write the JSON outputs.")
    parser.add_argument("--inspect", action="store_true",
                        help="List the tables + columns + row counts this reads, then exit. Run this FIRST.")
    parser.add_argument("--baseline-only", action="store_true", help="Compute only the passage-rate baseline.")
    parser.add_argument("--roster-only", action="store_true", help="Compute only the champion roster.")
    args = parser.parse_args()

    from app.ingestion.dump_analytics import inspect_schema, run

    if args.inspect:
        info = await inspect_schema(args.dump_dsn)
        for t, meta in info.items():
            if meta is None:
                print(f"{t}: MISSING (not in this restore)")
                continue
            print(f"{t}: {meta['rows']:,} rows")
            for name, dtype in meta["columns"]:
                print(f"    {name}: {dtype}")
        return

    states = [s.strip() for s in args.states.split(",")] if args.states else None
    summary = await run(
        dsn=args.dump_dsn,
        since_year=args.since_year,
        states=states,
        out_dir=args.out_dir,
        baseline=not args.roster_only,
        roster=not args.baseline_only,
    )
    print("Done:")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
