"""Retag in-scope `other`/`budget` bills as `incentives` where the lever is financial.

After adding the `incentives` instrument_type (tax credits/deductions/rebates, appropriations/
grants/funding programs, procurement/tenders for circular-economy outcomes), this re-runs the
Haiku classifier over the existing in-scope `other` and `budget` bills and promotes the ones it
now tags `incentives`. ADDITIVE ONLY: it only ever sets instrument_type='incentives'; it never
clears relevance or changes any other field. Classifies on title+description (enough to spot a
financial lever) — no bill-text fetch.

Idempotent. Defaults to DRY RUN.

Run:
    python scripts/reclassify_incentives.py                 # dry run (local)
    python scripts/reclassify_incentives.py --commit
    python scripts/reclassify_incentives.py --commit --dsn "postgresql://...@127.0.0.1:55432/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

# Ceremonial bills (resolutions, week/day designations, commendations) deploy no money, so they
# are never "incentives" even if the classifier tags them so — keep them as-is.
_RESO_PREFIX = ("HR", "SR", "HJR", "SJR", "HCR", "SCR", "HJM", "SJM", "HJ", "SJ", "HM", "SM")
_CEREMONIAL = re.compile(r"\b(commending|honoring|recognizing|designat\w*|awareness)\b|\bweek\b", re.I)


def _is_ceremonial(r: dict) -> bool:
    bn = (r.get("bill_number") or "").upper().replace(" ", "-")
    if bn.split("-")[0] in _RESO_PREFIX:
        return True
    return bool(_CEREMONIAL.search(r.get("title") or ""))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.haiku_classifier import HaikuClassifier  # noqa: E402
from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402

CONCURRENCY = 8


async def _classify(sem, haiku, row) -> dict:
    async with sem:
        try:
            hr = await haiku.classify(state=row.state, bill_number=row.bill_number or "",
                                      title=row.title or "", description=row.description or "")
            return {"id": row.id, "state": row.state, "bill_number": row.bill_number,
                    "title": row.title or "", "old": row.instrument_type,
                    "new": hr.instrument_type, "conf": hr.confidence}
        except Exception as e:  # noqa: BLE001
            return {"id": row.id, "state": row.state, "bill_number": row.bill_number,
                    "title": row.title or "", "old": row.instrument_type, "new": None,
                    "error": str(e)}


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    sql = ("SELECT id, state, bill_number, title, description, instrument_type FROM bills "
           "WHERE ce_relevant = true AND instrument_type IN ('other','budget') "
           "ORDER BY instrument_type, state" + (" LIMIT :lim" if args.limit else ""))
    async with Session() as db:
        rows = list((await db.execute(text(sql), {"lim": args.limit} if args.limit else {})).all())
    print(f"{len(rows)} in-scope other/budget bills to re-examine.")

    sem = asyncio.Semaphore(CONCURRENCY)
    haiku = HaikuClassifier()
    results = await asyncio.gather(*(_classify(sem, haiku, r) for r in rows))

    tagged = [r for r in results if r.get("new") == "incentives"]
    promote = [r for r in tagged if not _is_ceremonial(r)]
    skipped_ceremonial = [r for r in tagged if _is_ceremonial(r)]
    errors = [r for r in results if r.get("new") is None]
    promote.sort(key=lambda r: (r["state"] or "", r["bill_number"] or ""))

    print(f"\n{len(promote)} -> incentives  ({sum(r['old']=='budget' for r in promote)} from budget, "
          f"{sum(r['old']=='other' for r in promote)} from other); "
          f"{len(skipped_ceremonial)} ceremonial kept as-is; {len(errors)} errors\n")
    for r in promote:
        print(f"  {r['state']:3} {(r['bill_number'] or ''):10} [{r['old']}->incentives conf={r.get('conf')}]  {r['title'][:50]}")

    if not args.commit:
        print("\n(dry run — re-run with --commit to write.)")
        await engine.dispose()
        return

    async with Session() as db:
        for r in promote:
            await db.execute(
                text("UPDATE bills SET instrument_type='incentives', updated_at=now() WHERE id=:id"),
                {"id": r["id"]})
        await db.commit()
    print(f"\nUPDATED {len(promote)} bills to instrument_type='incentives'.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
