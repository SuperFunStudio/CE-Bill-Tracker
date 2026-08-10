"""Take pre-filing docket shells out of scope (ce_relevant True -> False).

MA files every bill under a House/Senate Docket number (HD-3107 / SD-2101) and KY under a Bill
Request (BR-342); on referral the same text is renumbered to H-988 / an HB. OpenStates publishes both
records, so the corpus holds the shell and the filed bill twice. A shell that was never referred has
no actions, hence no status_date, so it also lands in the "N bills carry no date" bucket of every
year-bucketed view — reading as a coverage gap when it is really a duplicate.

Only ACTION-LESS docket rows are hidden. A docket number that carries real actions is a bill the
legislature is genuinely moving under that identifier (19 in-scope rows sit at passed_chamber /
in_committee with real dates) and is left alone. That rule lives in app/ingestion/docket.py and is
enforced at three points; this script is the one that applies it to rows already on disk:
  - app/ingestion/coordinator._upsert_openstates_bill  — refuses to store new shells;
  - app/classification/pipeline                        — drops them from the classifier's candidates;
  - scripts/backfill_relevance.py                      — excludes them from set-based promotion.

Same convention as hide_untracked_instruments.py: ce_relevant=False means "ingested but out of scope,
kept for audit, hidden from the API" — nothing is deleted, and the rows come back on their own if the
bill is later referred and picks up an action.

    venv/Scripts/python.exe scripts/hide_docket_shells.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5462/signalscout" [--dry-run]

Local default uses the app's DATABASE_URL.
"""
import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.docket import DOCKET_PREFIXES  # noqa: E402

# SQL mirror of docket.is_docket_shell — generated from the same prefix table so the two can't drift.
IS_DOCKET_SHELL = "last_action_date IS NULL AND (" + " OR ".join(
    f"(state = '{st}' AND bill_number ~ '^({'|'.join(pfx)})-[0-9]+$')"
    for st, pfx in sorted(DOCKET_PREFIXES.items())
) + ")"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    for prefix in ("postgresql+asyncpg://", "postgres://"):
        if dsn.startswith(prefix):
            dsn = "postgresql://" + dsn[len(prefix):]

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT b.state, b.bill_number, b.status_date, b.title, "
            "  (SELECT string_agg(o.bill_number, ', ') FROM bills o "
            "     WHERE o.state = b.state AND o.id <> b.id AND o.title = b.title "
            "       AND o.status_date IS NOT NULL) AS filed_as "
            f"FROM bills b WHERE b.ce_relevant AND {IS_DOCKET_SHELL} "
            "ORDER BY b.state, b.bill_number"
        )
        if not rows:
            print("No in-scope docket shells. Nothing to do.")
            return

        by_state: dict[str, int] = {}
        orphans = []
        for r in rows:
            by_state[r["state"]] = by_state.get(r["state"], 0) + 1
            if not r["filed_as"]:
                orphans.append(r)

        print(f"{len(rows)} in-scope docket shells: {by_state}")
        print(f"  {len(rows) - len(orphans)} have a dated same-title row under a filed number:")
        for r in rows[:10]:
            print(f"    {r['state']} {r['bill_number']:<10} -> {r['filed_as'] or '(none)'}")
        if orphans:
            # No filed twin found. Still an action-less shell (nothing has happened to it), but worth
            # printing by name: this is the only class where hiding costs coverage rather than
            # removing a duplicate, so the run is auditable if one later turns out to matter.
            print(f"  {len(orphans)} have NO filed twin — hidden as action-less shells:")
            for r in orphans:
                print(f"    {r['state']} {r['bill_number']:<10} {(r['title'] or '')[:60]}")

        if args.dry_run:
            print("\n[dry-run] no writes.")
            return

        result = await conn.execute(
            "UPDATE bills SET ce_relevant = false, updated_at = now() "
            f"WHERE ce_relevant AND {IS_DOCKET_SHELL}"
        )
        print(f"\napplied: {result}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
