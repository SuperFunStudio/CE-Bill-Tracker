"""Backfill `state` with namespaced sub-national codes for foreign federations (CA, AU).

Every foreign law was ingested with state == region (an Ontario reg landed as region="CA", state="CA"),
because sync_foreign hardcoded state = region regardless of which province/state client fetched it. Now
each sub-national client carries a `subnational` code (app/ingestion/foreign.py: CanadaBcLawsClient ->
"CA-BC", AustraliaNswClient -> "AU-NSW", …), and the forward ingest path stamps it. This script applies
the SAME mapping to rows already in the corpus so Canada's provincial laws (BC/Ontario) and Australia's
state laws (NSW/QLD/TAS) break out of the flat national bucket.

The map is derived FROM the registry (FOREIGN_CLIENTS) — not re-typed here — so it can never drift from
the adapters and auto-covers any sub-national client added later. Each bill's `source` is read straight
off its foreign_id ("<REGION>:<source>:<id>"), so the mapping is deterministic, not a title guess.

Requires migration 041 (widens bills.state VARCHAR(2)->VARCHAR(16)) — namespaced codes don't fit the
old width. Idempotent: only rows whose state differs from the derived code are touched; national laws
(sources with no sub-national code) are left as state == region.

    # against prod via the Cloud SQL Auth Proxy (prod is source of truth — run here, then sync down):
    venv/Scripts/python.exe scripts/backfill_subnational_state.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" [--dry-run]

Local default uses the app's DATABASE_URL. --dry-run reports the reclassification without writing.
"""
import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

# Single source of truth: the same registry the ingest path uses. Any client that declares a
# `subnational` code contributes {source -> namespaced code}; national clients (subnational=None) don't.
from app.ingestion.foreign import FOREIGN_CLIENTS  # noqa: E402

SOURCE_TO_SUBNATIONAL: dict[str, str] = {
    cls.source: cls.subnational
    for cls in FOREIGN_CLIENTS.values()
    if getattr(cls, "subnational", None)
}


def _source_of(foreign_id: str) -> str | None:
    # foreign_id == "<REGION>:<source>:<source_id>"; source_id may itself contain ':', so split max 2.
    parts = (foreign_id or "").split(":", 2)
    return parts[1] if len(parts) >= 2 else None


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    print("source -> sub-national map (from FOREIGN_CLIENTS):", SOURCE_TO_SUBNATIONAL)
    if not SOURCE_TO_SUBNATIONAL:
        print("no sub-national clients registered — nothing to do.")
        return

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT id, region, state, foreign_id FROM bills WHERE foreign_id IS NOT NULL"
        )
        updates: list[tuple[str, int]] = []
        target_dist = Counter()
        mismatched: list[tuple[int, str, str]] = []  # (id, region, target) where region prefix disagrees
        for r in rows:
            source = _source_of(r["foreign_id"])
            target = SOURCE_TO_SUBNATIONAL.get(source or "")
            if not target:
                continue  # national source → leave state == region
            # Sanity: the namespaced code's region prefix must match the bill's region (CA-BC under CA).
            if target.split("-", 1)[0] != (r["region"] or "").upper():
                mismatched.append((r["id"], r["region"], target))
                continue
            if r["state"] != target:
                updates.append((target, r["id"]))
                target_dist[target] += 1

        print(f"foreign rows scanned: {len(rows)}   to re-tier: {len(updates)}")
        print("  target distribution:", dict(target_dist.most_common()))
        if mismatched:
            print(f"  ⚠ {len(mismatched)} rows skipped (region/target prefix mismatch):", mismatched[:10])

        if args.dry_run:
            print("\n[dry-run] no writes. Re-run without --dry-run to apply.")
            return

        # Guarded by state <> target so a re-run is a no-op and a concurrent correct write isn't clobbered.
        await conn.executemany(
            "UPDATE bills SET state = $1 WHERE id = $2 AND state <> $1", updates)
        print(f"\napplied: set namespaced sub-national state on {len(updates)} rows.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
