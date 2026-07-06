"""Backfill the v2 compliance dimensions (eco_modulation / recycled_content / penalties) across bills.

Why
---
These three dimensions are currently prose buried in ``bills.compliance_details`` (or not extracted at
all). Promoting them to structured envelopes — each with an explicit
``status`` (present|absent|not_applicable) + a verbatim ``source_excerpt`` — turns "does this measure
eco-modulate?" from a per-query LLM guess into a queryable, citable field. The extractor schema bump
lives in ``app.classification.sonnet_extractor.EXTRACTION_VERSION``; this script re-runs Sonnet on any
bill below the current version and MERGES the new envelopes into its existing compliance_details
(preserving polymers, deadlines, etc.).

Idempotent + resumable: candidates are bills whose stored ``extraction_version`` is behind the code's
(so a re-run continues where it stopped), text comes from ``bill_texts.text`` (no re-fetch), and each
bill commits on its own. Phase the rollout with --region (the non-English regions are 100% text-ready).

    python scripts/extract_dimensions.py --dry-run --limit 8 --region FR       # extract, no writes
    python scripts/extract_dimensions.py --limit 40 --region FR,DE,JP,CN,ES     # language spike
    python scripts/extract_dimensions.py --region US --limit 200                # US phase
    python scripts/extract_dimensions.py --dsn "postgresql://signalscout@127.0.0.1:5434/signalscout"

compliance_details is NOT copied by push_bills_to_prod.py, so to populate prod point --dsn at prod via
the Cloud SQL Auth Proxy (same as scan_bill_polymers.py / backfill_deadlines.py).
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

from app.classification.sonnet_extractor import EXTRACTION_VERSION, SonnetExtractor  # noqa: E402
from app.config import settings  # noqa: E402

# The envelope fields this backfill writes (must match SonnetResult attrs). Kept in one place so the
# merge + reporting stay in sync; v3 added collection_targets/pro_structure/bans_restrictions, v4
# added fee_amounts/labeling.
ENVELOPES = ("eco_modulation", "recycled_content", "penalties",
             "collection_targets", "pro_structure", "bans_restrictions",
             "fee_amounts", "labeling")
# Short labels for the per-bill progress line so all envelopes fit on one row.
_SHORT = {"eco_modulation": "eco", "recycled_content": "rc", "penalties": "pen",
          "collection_targets": "coll", "pro_structure": "pro", "bans_restrictions": "ban",
          "fee_amounts": "fee", "labeling": "lbl"}


def _normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return dsn if prefix == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(prefix):]
    return dsn


async def _candidates(db: AsyncSession, regions: list[str] | None, only_stale: bool,
                      limit: int) -> list:
    # JOIN bill_texts so we extract from stored full text (no re-fetch); this also means a bill with
    # no stored text is simply not a candidate yet (its text backfill has to land first).
    clauses = ["b.ce_relevant = true", "bt.text IS NOT NULL"]
    params: dict = {"limit": limit, "ver": EXTRACTION_VERSION}
    if regions:
        clauses.append("b.region = ANY(:regions)")
        params["regions"] = regions
    if only_stale:
        # COALESCE handles both NULL compliance_details and a missing extraction_version key (→ 0),
        # so freshly-classified and never-extracted bills alike are picked up until they reach v{ver}.
        clauses.append("COALESCE((b.compliance_details->>'extraction_version')::int, 0) < :ver")
    sql = ("SELECT b.id, b.region, b.state, b.bill_number, b.title, b.compliance_details, "
           "bt.text AS full_text "
           f"FROM bills b JOIN bill_texts bt ON bt.bill_id = b.id WHERE {' AND '.join(clauses)} "
           "ORDER BY b.status_date DESC NULLS LAST LIMIT :limit")
    return list((await db.execute(text(sql), params)).all())


def _status(env: dict | None) -> str:
    return (env or {}).get("status", "—") if isinstance(env, dict) else "—"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--region", default=None,
                    help="Comma-separated region codes to target (e.g. FR,DE,JP). Omit = all regions.")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=6,
                    help="How many extractions to run at once. LLM latency (~25s/bill) dominates, so "
                    "overlapping calls cuts a ~1000-bill run from hours to ~1h. DB writes stay serial.")
    ap.add_argument("--all", action="store_true",
                    help="Reprocess bills already at the current extraction_version.")
    ap.add_argument("--dry-run", action="store_true", help="Extract + report; no writes.")
    args = ap.parse_args()
    regions = [r.strip().upper() for r in (args.region or "").split(",") if r.strip()] or None

    # pool_pre_ping so a connection dropped by a transient network blip / Cloud SQL idle-disconnect is
    # detected and replaced on the next checkout, instead of surfacing mid-write on a long run.
    engine = create_async_engine(_normalize_dsn(args.dsn or settings.database_url), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    extractor = SonnetExtractor()

    async with Session() as db:
        bills = await _candidates(db, regions, only_stale=not args.all, limit=args.limit)
        print(f"{len(bills)} candidate bills (regions={regions or 'all'}, "
              f"{'all' if args.all else f'below v{EXTRACTION_VERSION}'}, limit={args.limit})\n")

        async def _do_extract(b):
            # Extract only (no DB) so a whole chunk's slow LLM calls overlap; caller writes serially.
            try:
                ex = await extractor.extract(
                    state=b.state, bill_number=b.bill_number or "", title=b.title or "",
                    full_text=b.full_text, region=b.region,
                )
                return b, ex, None
            except Exception as e:  # noqa: BLE001
                return b, None, e

        tallies = {e: Counter() for e in ENVELOPES}
        wrote = failed = 0
        step = max(1, args.concurrency)
        for i in range(0, len(bills), step):
            chunk = bills[i:i + step]
            for b, ex, err in await asyncio.gather(*[_do_extract(x) for x in chunk]):
                tag = f"{b.region}/{b.state} {b.bill_number or '?'}"
                if err is not None:
                    print(f"  [fail]  {tag}: {type(err).__name__}: {err}", flush=True)
                    failed += 1
                    continue
                if not ex.raw_json:
                    print(f"  [empty] {tag}: parse failed, left unversioned for retry", flush=True)
                    failed += 1
                    continue
                envs = {e: getattr(ex, e) or {} for e in ENVELOPES}
                for e in ENVELOPES:
                    tallies[e][_status(envs[e])] += 1
                # Compact one-line status for all six (p=present, a=absent, n/a=not_applicable, -=missing).
                compact = " ".join(f"{_SHORT[e]}={_status(envs[e])[:3]}" for e in ENVELOPES)
                print(f"  {tag:22s} {compact}", flush=True)

                if args.dry_run:
                    continue
                cd = b.compliance_details or {}
                if isinstance(cd, str):
                    cd = json.loads(cd)
                cd.update(envs)
                cd["extraction_version"] = EXTRACTION_VERSION
                # A dropped connection here must skip this bill (it stays below-version for the next
                # run), not crash the whole batch — pool_pre_ping hands the next bill a live connection.
                try:
                    await db.execute(
                        text("UPDATE bills SET compliance_details = CAST(:cd AS jsonb), "
                             "updated_at = now() WHERE id = :id"),
                        {"cd": json.dumps(cd, ensure_ascii=False), "id": b.id})
                    await db.commit()
                    wrote += 1
                except Exception as e:  # noqa: BLE001
                    print(f"  [db-fail] {tag}: {type(e).__name__}: {e}", flush=True)
                    await db.rollback()
                    failed += 1
            print(f"  … {min(i + step, len(bills))}/{len(bills)} processed "
                  f"({wrote} written, {failed} failed)", flush=True)

        print(f"\nprocessed {len(bills)} ({failed} failed/empty)")
        for e in ENVELOPES:
            summary = ", ".join(f"{k}={n}" for k, n in tallies[e].most_common())
            print(f"  {e:18s} {summary or '—'}")
        print("\n(dry run — no writes)" if args.dry_run else f"wrote v{EXTRACTION_VERSION} to {wrote} bills")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
