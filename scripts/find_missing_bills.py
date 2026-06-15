"""Sweep LegiScan for in-scope bills the DB is missing (ingestion keyword-filter gaps).

The OpenStates dump + keyword filter drop in-scope bills whose titles lack EPR keywords —
especially title-based instruments like right-to-repair, bottle/deposit, recycled-content,
and product-stewardship. This searches LegiScan for those topics across recent sessions,
diffs the results against our bills table (by legiscan_bill_id and state+bill_number), keeps
the gaps whose title carries an in-scope signal, and writes the candidate list for review.

No writes to bills. Output -> data/seed/_missing_bill_candidates.json. Add confirmed ones with
scripts/add_bill_from_legiscan.py (which runs the real Haiku classifier).

Run:
    python scripts/find_missing_bills.py                 # local DB diff
    python scripts/find_missing_bills.py --dsn "postgresql://...@127.0.0.1:55432/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.coordinator import _normalize_bill_number  # noqa: E402
from app.ingestion.legiscan import LegiScanClient  # noqa: E402
from scripts.backfill_deadlines_legiscan import _canon  # noqa: E402

OUT = Path(__file__).parent.parent / "data" / "seed" / "_missing_bill_candidates.json"

QUERIES = [
    "right to repair", "fair repair act", "digital electronic equipment repair",
    "extended producer responsibility", "producer responsibility packaging",
    "beverage container deposit", "bottle deposit return",
    "recycled content", "minimum recycled content",
    "product stewardship", "battery stewardship", "paint stewardship",
    "mattress stewardship", "textile recovery", "carpet stewardship",
]

# A gap result is kept only if its title looks genuinely in-scope (cuts full-text noise).
_SIGNAL = re.compile(
    r"(right[ -]?to[ -]?repair|fair repair|repair of (?:digital|electronic|certain)|"
    r"extended producer responsib|producer responsib|product stewardship|"
    r"stewardship (?:program|act|organization|for)|container deposit|beverage container|"
    r"bottle (?:bill|deposit)|recycled content|post[ -]?consumer|take[ -]?back|"
    r"end[ -]?of[ -]?life|recycling (?:program|of)|paint stewardship|battery stewardship)", re.I)


def _normalize_dsn(dsn: str) -> str:
    for p in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(p):
            return dsn if p == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(p):]
    return dsn


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--years", default="2023,2024,2025,2026")
    ap.add_argument("--pages", type=int, default=3, help="LegiScan result pages per query/year (50 each).")
    args = ap.parse_args()
    years = [int(y) for y in args.years.split(",")]

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # DB index: known legiscan ids + (state, canon bill#).
    async with Session() as db:
        rows = (await db.execute(text(
            "SELECT legiscan_bill_id, state, bill_number FROM bills"))).all()
    known_ids = {r.legiscan_bill_id for r in rows if r.legiscan_bill_id}
    known_keys = {(r.state, _canon(r.bill_number)) for r in rows if r.bill_number}
    await engine.dispose()
    print(f"DB has {len(rows)} bills ({len(known_ids)} legiscan-linked).")

    # Collect LegiScan results across queries/years.
    found: dict[int, dict] = {}
    async with LegiScanClient() as ls:
        for q in QUERIES:
            for y in years:
                for page in range(1, args.pages + 1):
                    try:
                        res = await ls.search(q, year=y, page=page)
                    except Exception as e:  # noqa: BLE001
                        print(f"  search err [{q} {y} p{page}]: {e}")
                        break
                    for r in res:
                        bid = r.get("bill_id")
                        if not bid:
                            continue
                        found.setdefault(int(bid), {
                            "bill_id": int(bid), "state": r.get("state"),
                            "bill_number": r.get("bill_number"), "title": r.get("title") or "",
                            "last_action_date": r.get("last_action_date"), "url": r.get("url"),
                            "query": q,
                        })
                    if len(res) < 50:
                        break

    # Diff -> gaps with an in-scope title signal.
    gaps = []
    for r in found.values():
        if r["bill_id"] in known_ids:
            continue
        if (r["state"], _canon(r["bill_number"])) in known_keys:
            continue
        if not _SIGNAL.search(r["title"]):
            continue
        gaps.append(r)

    gaps.sort(key=lambda r: (r["state"] or "", str(r["last_action_date"])))
    OUT.write_text(json.dumps(gaps, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nScanned {len(found)} unique LegiScan results -> {len(gaps)} in-scope GAPS "
          f"(not in DB). Written to {OUT.relative_to(OUT.parents[2])}\n")
    from collections import Counter
    by_state = Counter(g["state"] for g in gaps)
    print("by state:", dict(sorted(by_state.items(), key=lambda x: -x[1])))
    print()
    for g in gaps:
        print(f"  {g['state']:3} {(g['bill_number'] or ''):9} {str(g['last_action_date'])[:10]:11} {g['title'][:62]}")


if __name__ == "__main__":
    asyncio.run(main())
