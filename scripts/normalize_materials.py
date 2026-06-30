"""Normalize bills.material_categories to the canonical taxonomy across ALL regions.

Folds drift/synonym slugs (paper→paper_packaging, plastics→plastic_packaging, thermostats→
electronics, mercury→other, …) into app.classification.materials.CANONICAL_MATERIALS so US/EU/JP/…
compare apples-to-apples. Idempotent — re-running is a no-op once clean. The classification pipeline
also normalizes at write time, so this is the one-time cleanup of existing rows.

Usage (Cloud SQL Auth Proxy on 127.0.0.1:5434 for dev):
    venv/Scripts/python scripts/normalize_materials.py                       # local DB
    venv/Scripts/python scripts/normalize_materials.py --dsn "<dev DSN>"     # dev
    venv/Scripts/python scripts/normalize_materials.py --dsn "<dsn>" --dry-run
"""
import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.materials import normalize_materials


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
    args = ap.parse_args()

    if args.dsn:
        dsn = args.dsn
    else:
        from app.config import settings
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

    c = await asyncpg.connect(dsn)
    try:
        rows = await c.fetch(
            "SELECT id, material_categories FROM bills WHERE material_categories IS NOT NULL"
        )
        changed = []
        folded = Counter()  # which slugs got rewritten, for the report
        for r in rows:
            cur = r["material_categories"]
            if isinstance(cur, str):
                cur = json.loads(cur)
            if not isinstance(cur, list):
                continue
            new = normalize_materials(cur)
            if new != cur:
                changed.append((r["id"], new))
                for s in cur:
                    if s not in new:  # slug was rewritten/removed by normalization
                        folded[s] += 1
        print(f"rows scanned: {len(rows)} | rows needing normalization: {len(changed)}")
        if folded:
            print("slugs folded (count of rows where the slug was rewritten):")
            for s, n in folded.most_common():
                print(f"   {s:28} {n}")
        if args.dry_run:
            print("DRY RUN — no writes.")
            return
        async with c.transaction():
            await c.executemany(
                "UPDATE bills SET material_categories = $2::jsonb WHERE id = $1",
                [(bid, json.dumps(new)) for bid, new in changed],
            )
        print(f"normalized {len(changed)} rows.")
    finally:
        await c.close()


if __name__ == "__main__":
    main_coro = main()
    asyncio.run(main_coro)
