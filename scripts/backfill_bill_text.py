"""Backfill persisted full bill text into bill_texts — Layer B Step 3 of the full-text search plan.

For each in-scope bill it fetches the cleaned full text via the shared ladder
(app.ingestion.bill_text.fetch_clean_text: LegiScan → OpenStates → source_url, tag-stripped) and
upserts it into ``bill_texts`` (bill_id, text, char_len, source, indexed_change_hash, fetched_at).
The generated ``text_tsv`` column + GIN index (migration 028) are maintained by Postgres, so once a
row lands it is immediately FTS-searchable.

Idempotent / resumable: a bill is a candidate only when it has NO text row yet, or its
``change_hash`` differs from the row's ``indexed_change_hash`` (i.e. the bill changed since we last
indexed it). So a re-run continues where the last left off and only re-fetches genuinely-stale
bills. ``--all`` forces a re-fetch of everything in scope. Rows are written only on a successful
fetch; bills whose text is unreachable (~5%) simply get no row and are retried next run.

Scope: all ``ce_relevant`` bills (per plan decision D4 — the SB 707/footwear case is textiles, so a
plastics-only scope would miss the payoff). ``--materials`` narrows it for testing. Always
``--dry-run`` first to confirm reachability before spending OpenStates/LegiScan calls on a full run.

    python scripts/backfill_bill_text.py --dry-run --limit 15        # fetch + report, no writes
    python scripts/backfill_bill_text.py --limit 50                  # local, writes bill_texts
    python scripts/backfill_bill_text.py --dsn "postgresql://signalscout@127.0.0.1:5434/signalscout"

bill_texts is NOT copied by push_bills_to_prod.py, so to populate prod, point --dsn at prod via the
Cloud SQL Auth Proxy (same pattern as scan_bill_polymers.py / backfill_deadlines.py).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402
from app.ingestion.bill_text import SOURCE_NONE, fetch_clean_text  # noqa: E402
from app.ingestion.legiscan import LegiScanClient  # noqa: E402
from app.ingestion.nysenate import NYSenateClient  # noqa: E402
from app.ingestion.openstates import OpenStatesClient  # noqa: E402


def _normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return dsn if prefix == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(prefix):]
    return dsn


async def _candidates(db: AsyncSession, materials: list[str] | None, only_stale: bool,
                      limit: int) -> list:
    # Fetchable bills only: a stored LegiScan id, a non-historical OpenStates id, or a source_url.
    clauses = ["b.ce_relevant = true",
               "(b.legiscan_bill_id IS NOT NULL OR (b.openstates_id IS NOT NULL "
               "AND b.openstates_id NOT LIKE 'hist:%') OR b.source_url IS NOT NULL)"]
    params: dict = {"limit": limit}
    if materials:
        clauses.append("jsonb_exists_any(b.material_categories, :materials)")
        params["materials"] = materials
    if only_stale:
        # No row yet, OR the bill changed since we indexed it. IS DISTINCT FROM is NULL-safe, so a
        # bill with NULL change_hash and an existing row (also NULL) is correctly treated as current.
        clauses.append("(t.bill_id IS NULL OR t.indexed_change_hash IS DISTINCT FROM b.change_hash)")
    sql = ("SELECT b.id, b.state, b.bill_number, b.title, b.openstates_id, b.legiscan_bill_id, "
           "b.source_url, b.change_hash, b.status_date, b.last_action_date "
           "FROM bills b LEFT JOIN bill_texts t ON t.bill_id = b.id "
           f"WHERE {' AND '.join(clauses)} "
           "ORDER BY b.status_date DESC NULLS LAST LIMIT :limit")
    return list((await db.execute(text(sql), params)).all())


_UPSERT = text(
    "INSERT INTO bill_texts (bill_id, text, char_len, source, indexed_change_hash, fetched_at) "
    "VALUES (:id, :text, :clen, :src, :hash, now()) "
    "ON CONFLICT (bill_id) DO UPDATE SET "
    "text = EXCLUDED.text, char_len = EXCLUDED.char_len, source = EXCLUDED.source, "
    "indexed_change_hash = EXCLUDED.indexed_change_hash, fetched_at = EXCLUDED.fetched_at"
)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--materials", default="",
                    help="Comma-separated material_categories to target ('' = all relevant bills).")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--all", action="store_true",
                    help="Re-fetch bills already indexed at the current change_hash.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch + report; no writes.")
    ap.add_argument("--os-delay", type=float, default=settings.openstates_request_delay_seconds,
                    help="Seconds to wait before each OpenStates fallback call (free-tier throttle).")
    args = ap.parse_args()
    materials = [m.strip() for m in args.materials.split(",") if m.strip()] or None

    dsn = args.dsn or settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        bills = await _candidates(db, materials, only_stale=not args.all, limit=args.limit)
        print(f"{len(bills)} candidate bills (materials={materials or 'all relevant'}, "
              f"{'all in scope' if args.all else 'missing/stale only'}, limit={args.limit})\n")

        by_source: Counter = Counter()
        no_text = wrote = total_chars = 0
        async with (
            LegiScanClient() as ls_client,
            OpenStatesClient() as os_client,
            NYSenateClient() as ny_client,
        ):
            for b in bills:
                tag = f"{b.state} {b.bill_number or '?'}"
                try:
                    full_text, src = await fetch_clean_text(
                        ls_client, os_client, b, args.os_delay, ny_client=ny_client
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"  [fail] {tag}: {type(e).__name__}: {e}")
                    continue
                if not full_text or src == SOURCE_NONE:
                    no_text += 1
                    print(f"  [no-text] {tag}")
                    continue
                by_source[src] += 1
                total_chars += len(full_text)
                print(f"  [{src:10s}] {tag}: {len(full_text):>7}c")

                if args.dry_run:
                    continue
                try:
                    await db.execute(_UPSERT, {"id": b.id, "text": full_text, "clen": len(full_text),
                                              "src": src, "hash": b.change_hash})
                    await db.commit()
                    wrote += 1
                except Exception as e:  # noqa: BLE001 — one unstorable row must not abort the run
                    await db.rollback()
                    print(f"  [write-fail] {tag}: {type(e).__name__}: {e}")

        got = sum(by_source.values())
        print(f"\nfetched text for {got}/{len(bills)} ({no_text} no-text)")
        if got:
            avg_kb = (total_chars / got) / 1024
            print(f"by source: {dict(by_source)} · avg {avg_kb:.1f} KB/bill")
        if args.dry_run:
            print("\n(dry run — no writes)")
        else:
            print(f"wrote {wrote} bill_texts rows")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
