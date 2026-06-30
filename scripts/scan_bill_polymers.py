"""Scan full bill text for named polymers/resins and (optionally) record what's found.

Why
---
`bills.material_categories` is category-level (``plastic_packaging``) and the resin a bill
names (EVA / HDPE / expanded polystyrene …) lives only in the full text, which we don't
store. This script fetches each candidate bill's full text via the SAME proven path the
deadlines backfill uses — ``OpenStatesClient.get_text_from_source(source_url)`` first (a
direct state-site scrape, no API key / quota), then ``get_bill_text(openstates_id)``, then
LegiScan ``getBillText`` as a last resort — runs the controlled detector in
``app.classification.polymers``, and writes the resin codes to
``bills.compliance_details['polymers']`` (JSONB — no migration needed).

DEFAULT TARGET: ce_relevant bills tagged plastic_packaging / plastic_products (override with
--materials). Always start with --dry-run to confirm text is reachable and see what the
detector finds before spending OpenStates/LegiScan calls on a full run.

    python scripts/scan_bill_polymers.py --dry-run --limit 15        # fetch + detect, no writes
    python scripts/scan_bill_polymers.py --limit 50                  # local, writes polymers
    python scripts/scan_bill_polymers.py --dsn "postgresql://signalscout@127.0.0.1:5434/signalscout"

compliance_details is NOT copied by push_bills_to_prod.py, so to populate prod, point --dsn
at prod via the Cloud SQL Auth Proxy (same as backfill_deadlines.py).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.polymers import BY_CODE, detect_polymers  # noqa: E402
from app.config import settings  # noqa: E402
# Shared fetch ladder (LegiScan → OpenStates → source_url, returns clean tag-free text).
from app.ingestion.bill_text import fetch_clean_text  # noqa: E402
from app.ingestion.legiscan import LegiScanClient  # noqa: E402
from app.ingestion.openstates import OpenStatesClient  # noqa: E402

DEFAULT_MATERIALS = ["plastic_packaging", "plastic_products"]


def _normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return dsn if prefix == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(prefix):]
    return dsn


async def _candidates(db: AsyncSession, materials: list[str] | None, only_missing: bool,
                      limit: int) -> list:
    clauses = ["ce_relevant = true",
               "(legiscan_bill_id IS NOT NULL OR (openstates_id IS NOT NULL "
               "AND openstates_id NOT LIKE 'hist:%') OR source_url IS NOT NULL)"]
    params: dict = {"limit": limit}
    if materials:
        clauses.append("jsonb_exists_any(material_categories, :materials)")
        params["materials"] = materials
    if only_missing:
        # Skip bills already carrying a polymers key (so re-runs are incremental). NULL-safe:
        # `NULL ? 'polymers'` is NULL and `NOT NULL` is NULL (not TRUE), which would silently
        # drop every bill with no compliance_details yet — i.e. most of them.
        clauses.append("(compliance_details IS NULL OR NOT (compliance_details ? 'polymers'))")
    sql = ("SELECT id, state, bill_number, title, openstates_id, legiscan_bill_id, "
           "source_url, compliance_details "
           f"FROM bills WHERE {' AND '.join(clauses)} "
           "ORDER BY status_date DESC NULLS LAST LIMIT :limit")
    return list((await db.execute(text(sql), params)).all())


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--materials", default=",".join(DEFAULT_MATERIALS),
                    help="Comma-separated material_categories to target ('' = all relevant bills).")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--all", action="store_true",
                    help="Reprocess bills that already have a polymers key.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch + detect + report; no writes.")
    ap.add_argument("--os-delay", type=float, default=settings.openstates_request_delay_seconds,
                    help="Seconds to wait before each OpenStates fallback call (free-tier throttle).")
    args = ap.parse_args()
    materials = [m.strip() for m in args.materials.split(",") if m.strip()] or None

    dsn = args.dsn
    if not dsn:
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        bills = await _candidates(db, materials, only_missing=not args.all, limit=args.limit)
        print(f"{len(bills)} candidate bills (materials={materials or 'all relevant'}, "
              f"{'all' if args.all else 'missing-polymers only'}, limit={args.limit})\n")

        tally: Counter = Counter()
        no_text = with_text = wrote = 0
        async with LegiScanClient() as ls_client, OpenStatesClient() as os_client:
            for b in bills:
                tag = f"{b.state} {b.bill_number or '?'}"
                try:
                    full_text, src = await fetch_clean_text(ls_client, os_client, b, args.os_delay)
                except Exception as e:  # noqa: BLE001
                    print(f"  [fail] {tag}: {type(e).__name__}: {e}")
                    continue
                if not full_text:
                    no_text += 1
                    print(f"  [no-text] {tag}")
                    continue
                with_text += 1
                codes = detect_polymers(full_text)
                for c in codes:
                    tally[c] += 1
                shown = ", ".join(f"{c} ({BY_CODE[c].name})" for c in codes) or "—"
                print(f"  [{src:10s}] {tag}: {len(full_text):>6}c  ->  {shown}")

                if args.dry_run or not codes:
                    continue
                cd = b.compliance_details or {}
                if isinstance(cd, str):
                    cd = json.loads(cd)
                cd["polymers"] = codes
                await db.execute(
                    text("UPDATE bills SET compliance_details = CAST(:cd AS jsonb), "
                         "updated_at = now() WHERE id = :id"),
                    {"cd": json.dumps(cd), "id": b.id})
                await db.commit()
                wrote += 1

        print(f"\nfetched text for {with_text}/{len(bills)} ({no_text} no-text)")
        if tally:
            print("polymers detected (bill counts):")
            for code, n in tally.most_common():
                print(f"  {code:5s} {BY_CODE[code].name:34s} {n}")
        if args.dry_run:
            print("\n(dry run — no writes)")
        else:
            print(f"wrote polymers to {wrote} bills")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
