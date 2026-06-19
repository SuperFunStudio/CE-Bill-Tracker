"""Promote bills to reviewed=True after a human has verified them against the source.

This is the missing half of the stance-review loop: the public site only shows a red "weakens
circular economy" flag for bills where reviewed=True (see dashboard-next/src/lib/utils.ts
isWeakening — the AI call alone measured ~75% precision, too low to publish unguarded). A reviewer
works the /beta "Weakening Watch" queue, confirms a call against the full bill text, then runs this
to flip reviewed — which is what earns that bill its public flag.

Idempotent; only flips rows currently reviewed=False. Run against local (the authoritative store)
then sync to prod the same way stance was synced (scripts/sync_enacted_and_stance_to_prod.py).

Usage:
    venv/Scripts/python.exe scripts/mark_reviewed.py --ids 123,456,789
    venv/Scripts/python.exe scripts/mark_reviewed.py --ids 123 --dry-run
    venv/Scripts/python.exe scripts/mark_reviewed.py --unreview --ids 123   # undo a mistaken promote
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", required=True, help="Comma-separated bill ids to (un)mark reviewed.")
    ap.add_argument("--unreview", action="store_true", help="Set reviewed=False instead of True.")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = ap.parse_args()

    target = not args.unreview
    try:
        ids = [int(x) for x in args.ids.split(",") if x.strip()]
    except ValueError:
        ap.error("--ids must be comma-separated integers")
    if not ids:
        ap.error("no ids given")

    import asyncpg
    from app.config import settings

    dsn = settings.database_url.replace("postgresql+asyncpg", "postgresql")
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT id, state, bill_number, policy_stance, reviewed FROM bills WHERE id = ANY($1::int[]) ORDER BY id",
            ids,
        )
        found = {r["id"] for r in rows}
        missing = [i for i in ids if i not in found]
        to_flip = [r for r in rows if r["reviewed"] != target]

        for r in rows:
            mark = "-> flip" if r["reviewed"] != target else "(already)"
            print(f"  {r['id']} {r['state']} {r['bill_number']} stance={r['policy_stance']} "
                  f"reviewed={r['reviewed']} {mark}")
        if missing:
            print(f"  NOT FOUND: {missing}")

        # Safety: a public flag only matters for weakens bills. Warn if promoting a non-weakens row
        # (harmless, but usually means the wrong id was pasted from the queue).
        odd = [r["id"] for r in to_flip if target and r["policy_stance"] != "weakens"]
        if odd:
            print(f"  NOTE: {odd} are not policy_stance='weakens' — promoting them has no public effect.")

        if args.dry_run:
            print(f"DRY RUN: would set reviewed={target} on {len(to_flip)} bill(s).")
            return
        if not to_flip:
            print("Nothing to change.")
            return
        await conn.execute(
            "UPDATE bills SET reviewed=$2, updated_at=now() WHERE id = ANY($1::int[])",
            [r["id"] for r in to_flip], target,
        )
        print(f"APPLIED: set reviewed={target} on {len(to_flip)} bill(s).")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
