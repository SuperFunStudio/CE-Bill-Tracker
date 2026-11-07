"""Run the LegiScan status sync by hand (the scheduler runs it nightly when
ENABLE_LEGISCAN_STATUS_SYNC is on). Dry-run by default: prints the status moves it would make.

    venv/Scripts/python scripts/legiscan_status_sync.py --dsn "postgresql://signalscout:PW@127.0.0.1:5436/signalscout"
    venv/Scripts/python scripts/legiscan_status_sync.py --dsn ... --states CA,RI --apply

Without --dsn it uses DATABASE_URL from settings. Needs LEGISCAN_API_KEY.
See app/ingestion/legiscan_status.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402
from app.ingestion.legiscan import LegiScanClient  # noqa: E402
from app.ingestion.legiscan_status import run_legiscan_status_sync  # noqa: E402


def _normalize_dsn(dsn: str) -> str:
    for p in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(p):
            return dsn if p == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(p):]
    return dsn


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--states", default=None, help="comma-separated, e.g. CA,RI")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    engine = create_async_engine(_normalize_dsn(args.dsn or settings.database_url),
                                 connect_args={"ssl": False} if args.dsn else {})
    states = [s.strip().upper() for s in args.states.split(",")] if args.states else None
    async with async_sessionmaker(engine, expire_on_commit=False)() as db, LegiScanClient() as ls:
        summary = await run_legiscan_status_sync(db, ls, states=states, dry_run=not args.apply)
    await engine.dispose()

    planned = summary.pop("planned_changes")
    print(json.dumps(summary, indent=2))
    print(f"\n{'APPLIED' if args.apply else 'WOULD APPLY'} {len(planned)} status changes:")
    for p in planned:
        print(f"  {p['state']} {p['bill']:<12} {p['old'] or '-':>15} -> {p['new']:<14} "
              f"{p['status_date']}  {(p['last_action'] or '')[:70]}")


if __name__ == "__main__":
    asyncio.run(main())
