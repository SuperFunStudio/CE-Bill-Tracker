"""Backfill bills from a restored OpenStates PostgreSQL dump.

See app/ingestion/openstates_pgdump.py for the restore runbook. Quick version:

    createdb openstates_dump
    pg_restore --no-owner --no-acl -d openstates_dump 2026-06-public.pgdump

Usage:
    python scripts/import_openstates_pgdump.py --inspect
    python scripts/import_openstates_pgdump.py --dry-run --states TX,CA
    python scripts/import_openstates_pgdump.py --since-year 2023
    python scripts/import_openstates_pgdump.py --states CA,OR,WA,NY,ME,CO,CT --since-year 2021

--dump-dsn defaults to the local restored DB; override for a different host/name.
After importing, classify with:  python scripts/import_openstates_pgdump.py --classify
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dump-dsn",
        # The OpenStates dump is archive format 1.16 (pg_dump 17/18) so it must be restored
        # with PG18 tools into the PG18 server on port 5433; the app's own DB stays on 5432.
        default="postgresql://postgres:dev@localhost:5433/openstates_dump",
        help="DSN of the restored OpenStates dump database.",
    )
    parser.add_argument("--since-year", type=int, default=2023,
                        help="Only import bills from legislative sessions starting this year or later.")
    parser.add_argument("--states", default=None,
                        help="Comma-separated state codes to restrict to (e.g. TX,CA). Default: all.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after scanning this many bills (testing).")
    parser.add_argument("--inspect", action="store_true",
                        help="List opencivicdata tables + row counts and exit.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be imported without writing.")
    parser.add_argument("--no-keyword-filter", action="store_true",
                        help="Import ALL bills, not just EPR keyword matches "
                             "(use for full-corpus / other-topic extraction).")
    parser.add_argument("--classify", action="store_true",
                        help="After import, run the keyword/LLM classification cycle.")
    args = parser.parse_args()

    from app.ingestion.openstates_pgdump import import_from_dump, inspect_dump

    if args.inspect:
        info = await inspect_dump(args.dump_dsn)
        print("Tables in dump:")
        for t, c in info["tables"].items():
            print(f"  {t}: {c:,}")
        if not info["tables"]:
            print("  (none found — did pg_restore complete into this database?)")
        return

    states = [s.strip() for s in args.states.split(",")] if args.states else None
    summary = await import_from_dump(
        dump_dsn=args.dump_dsn,
        since_year=args.since_year,
        states=states,
        dry_run=args.dry_run,
        limit=args.limit,
        keyword_filter=not args.no_keyword_filter,
    )
    print("Result:")
    for k, v in summary.items():
        if k == "sample" and v:
            print("  sample_bill:")
            for sk, sv in v.items():
                print(f"      {sk}: {sv}")
        else:
            print(f"  {k}: {v}")

    if args.classify and not args.dry_run:
        print("Running classification cycle...")
        from app.scheduler.jobs import run_classification_cycle
        await run_classification_cycle()
        print("Classification complete.")


if __name__ == "__main__":
    asyncio.run(main())
