"""Re-derive US bills.material_categories from a pristine source through the canonical normalizer.

One-off recovery: the first taxonomy pass folded mercury/HHW/auto_switches lossily on local+dev
before `hazardous_materials` existed, so the original slugs are gone there. Prod is untouched and
still carries the originals, so this re-pulls each US bill's material_categories from a source DB
(prod), runs it through app.classification.materials.normalize_materials (current canonical + alias
map), and writes the result to a target DB (local/dev), matched by openstates_id.

Usage (Cloud SQL Auth Proxy on :5434; prod DB = signalscout, dev = signalscout_dev):
    venv/Scripts/python scripts/resync_us_materials.py \
        --source-dsn "postgresql://signalscout:PW@127.0.0.1:5434/signalscout" \
        --target-dsn "postgresql://signalscout:PW@127.0.0.1:5434/signalscout_dev"   # prod -> dev
    # omit --target-dsn to write the app's local DATABASE_URL.
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
    ap.add_argument("--source-dsn", required=True, help="Pristine source (e.g. prod 'signalscout').")
    ap.add_argument("--target-dsn", default=None, help="Target (defaults to app DATABASE_URL = local).")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.target_dsn:
        target_dsn = args.target_dsn
    else:
        from app.config import settings
        target_dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

    src = await asyncpg.connect(args.source_dsn)
    tgt = await asyncpg.connect(target_dsn)
    try:
        rows = await src.fetch(
            "SELECT openstates_id, material_categories FROM bills "
            "WHERE openstates_id IS NOT NULL AND material_categories IS NOT NULL"
        )
        updates, into = [], Counter()
        for r in rows:
            cur = r["material_categories"]
            if isinstance(cur, str):
                cur = json.loads(cur)
            if not isinstance(cur, list):
                continue
            new = normalize_materials(cur)
            updates.append((r["openstates_id"], json.dumps(new)))
            for s in new:
                into[s] += 1
        print(f"source US rows: {len(rows)} | normalized -> {into.get('hazardous_materials',0)} "
              f"now tagged hazardous_materials")
        if args.dry_run:
            print("DRY RUN — no writes."); return
        async with tgt.transaction():
            n = await tgt.executemany(
                "UPDATE bills SET material_categories = $2::jsonb "
                "WHERE openstates_id = $1 AND region = 'US'",
                updates,
            )
        print(f"updated target US rows ({len(updates)} attempted).")
    finally:
        await src.close()
        await tgt.close()


if __name__ == "__main__":
    asyncio.run(main())
