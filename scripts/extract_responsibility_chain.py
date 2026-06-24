"""Extract the heuristic "nearest chain of responsibility" for relevant bills (Tier 1).

For each bill it fetches full text (same path as scan_bill_polymers: LegiScan-primary →
throttled OpenStates → source_url), runs app.classification.responsibility.extract_chain, and
writes the result to bills.compliance_details['responsibility_chain'] (JSONB — no migration):

    {"links": ["producer","pro","stewardship_plan","agency_rule","needs_assessment",
               "advisory_review","enforcement"],
     "agency": {"name": "...", "abbr": "DEQ", "confirmed_in_text": true, "source": "curated"},
     "advisory_body": "Oregon Recycling System Advisory Council",
     "by_rule": true, "needs_assessment": false, "next_responsible": "pro"}

DO NOT run concurrently with scan_bill_polymers.py — both do read-modify-write on
compliance_details and would clobber each other's key.

    python scripts/extract_responsibility_chain.py --dry-run --limit 20
    python scripts/extract_responsibility_chain.py --materials "" --limit 2000     # full run, local
    python scripts/extract_responsibility_chain.py --dsn "postgresql://signalscout@127.0.0.1:5434/signalscout"
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

from app.classification.responsibility import extract_chain  # noqa: E402
from app.config import settings  # noqa: E402
from app.ingestion.legiscan import LegiScanClient  # noqa: E402
from app.ingestion.openstates import OpenStatesClient  # noqa: E402
from scripts.scan_bill_polymers import _fetch_full_text, _normalize_dsn  # noqa: E402


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
        clauses.append("(compliance_details IS NULL OR "
                       "NOT (compliance_details ? 'responsibility_chain'))")
    sql = ("SELECT id, state, bill_number, openstates_id, legiscan_bill_id, source_url, "
           "compliance_details "
           f"FROM bills WHERE {' AND '.join(clauses)} "
           "ORDER BY status_date DESC NULLS LAST LIMIT :limit")
    return list((await db.execute(text(sql), params)).all())


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--materials", default="",
                    help="Comma-separated material_categories to target ('' = all relevant bills).")
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--all", action="store_true",
                    help="Reprocess bills that already have a responsibility_chain.")
    ap.add_argument("--dry-run", action="store_true", help="Fetch + extract + report; no writes.")
    ap.add_argument("--os-delay", type=float, default=settings.openstates_request_delay_seconds)
    args = ap.parse_args()
    materials = [m.strip() for m in args.materials.split(",") if m.strip()] or None

    dsn = args.dsn or settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        bills = await _candidates(db, materials, only_missing=not args.all, limit=args.limit)
        print(f"{len(bills)} candidate bills (materials={materials or 'all relevant'}, "
              f"{'all' if args.all else 'missing-chain only'}, limit={args.limit})\n")

        link_tally: Counter = Counter()
        next_tally: Counter = Counter()
        no_text = with_chain = wrote = 0
        async with LegiScanClient() as ls_client, OpenStatesClient() as os_client:
            for b in bills:
                tag = f"{b.state} {b.bill_number or '?'}"
                try:
                    full_text, src = await _fetch_full_text(ls_client, os_client, b, args.os_delay)
                except Exception as e:  # noqa: BLE001
                    print(f"  [fail] {tag}: {type(e).__name__}: {e}")
                    continue
                if not full_text:
                    no_text += 1
                    print(f"  [no-text] {tag}")
                    continue
                chain = extract_chain(b.state, full_text)
                if not chain["links"]:
                    # No delegation structure found — record nothing rather than an empty chain.
                    print(f"  [{src:10s}] {tag}: no chain")
                    continue
                with_chain += 1
                for lk in chain["links"]:
                    link_tally[lk] += 1
                next_tally[chain["next_responsible"] or "none"] += 1
                ag = chain["agency"]["abbr"] if chain["agency"] else "?"
                print(f"  [{src:10s}] {tag}: next={chain['next_responsible']} agency={ag} "
                      f"links={len(chain['links'])}")

                if args.dry_run:
                    continue
                cd = b.compliance_details or {}
                if isinstance(cd, str):
                    cd = json.loads(cd)
                cd["responsibility_chain"] = chain
                await db.execute(
                    text("UPDATE bills SET compliance_details = CAST(:cd AS jsonb), "
                         "updated_at = now() WHERE id = :id"),
                    {"cd": json.dumps(cd), "id": b.id})
                await db.commit()
                wrote += 1

        print(f"\nchain found for {with_chain}/{len(bills)} ({no_text} no-text)")
        if link_tally:
            print("links present (bill counts):")
            for lk, n in link_tally.most_common():
                print(f"  {lk:18s} {n}")
            print("next-responsible (bill counts):")
            for nr, n in next_tally.most_common():
                print(f"  {nr:20s} {n}")
        if args.dry_run:
            print("\n(dry run — no writes)")
        else:
            print(f"wrote responsibility_chain to {wrote} bills")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
