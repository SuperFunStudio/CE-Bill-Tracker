"""Batch-add the in-scope bills found by find_missing_bills.py (the keyword-filter gaps).

For each candidate in data/seed/_missing_bill_candidates.json: fetch status + text from
LegiScan, DROP anything LegiScan marks vetoed/failed (status 5/6) — the "enacted + active"
scope — run the SAME Haiku classifier the pipeline uses (which also gates out the few
full-text-search false positives), and upsert the rest. Idempotent on legiscan_bill_id /
state+bill_number. Defaults to DRY RUN.

Run:
    python scripts/add_missing_bills.py                          # dry run (local DB)
    python scripts/add_missing_bills.py --commit                 # write local
    python scripts/add_missing_bills.py --commit --dsn "postgresql://...@127.0.0.1:55432/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.haiku_classifier import TRACKED_INSTRUMENTS, HaikuClassifier  # noqa: E402
from app.ingestion.coordinator import _normalize_bill_number  # noqa: E402
from app.ingestion.legiscan import LegiScanClient  # noqa: E402
from app.models import Bill  # noqa: E402
from scripts.add_bill_from_legiscan import _STATUS, _normalize_dsn, _parse_date  # noqa: E402
from scripts.backfill_deadlines_legiscan import _fetch_text  # noqa: E402

CANDS = Path(__file__).parent.parent / "data" / "seed" / "_missing_bill_candidates.json"
EXCLUDE_STATUS = {5, 6}  # vetoed, failed/dead — the "enacted + active" filter
CONCURRENCY = 6


async def _evaluate(ls: LegiScanClient, sem: asyncio.Semaphore, haiku: HaikuClassifier, cand: dict) -> dict:
    """Fetch status+text, classify. Returns a verdict dict (no DB)."""
    async with sem:
        out = {"cand": cand, "insert": False, "reason": ""}
        try:
            meta = await ls.get_bill(int(cand["bill_id"]))
            snum = int(meta.get("status", 0) or 0)
            out["status_num"] = snum
            out["status"] = _STATUS.get(snum, "introduced")
            out["title"] = meta.get("title") or cand.get("title") or ""
            out["desc"] = meta.get("description") or out["title"]
            out["source_url"] = meta.get("state_link") or cand.get("url")
            out["last_action"] = _parse_date(meta.get("status_date") or cand.get("last_action_date"))
            if snum in EXCLUDE_STATUS:
                out["reason"] = f"{out['status']} (excluded)"
                return out
            text, _ = await _fetch_text(ls, int(cand["bill_id"]))
            hr = await haiku.classify(state=cand["state"], bill_number=_normalize_bill_number(cand["bill_number"] or ""),
                                      title=out["title"], description=out["desc"], text_excerpt=text)
            out["hr"] = hr
            relevant = hr.confidence >= 0.4 and (hr.is_epr_relevant or hr.instrument_type in TRACKED_INSTRUMENTS)
            out["insert"] = relevant
            out["reason"] = (f"{hr.instrument_type} conf={hr.confidence}" if relevant
                             else f"not-relevant ({hr.instrument_type} conf={hr.confidence})")
        except Exception as e:  # noqa: BLE001
            out["reason"] = f"error {type(e).__name__}: {e}"
        return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--active-since", type=int, default=2025,
                    help="Non-enacted bills are kept only if their last action is in/after this "
                         "year (older introduced bills are dead — LegiScan often leaves them "
                         "'introduced' rather than 'failed'). Enacted bills are kept regardless.")
    args = ap.parse_args()

    cands = json.loads(CANDS.read_text(encoding="utf-8"))
    if args.limit:
        cands = cands[: args.limit]
    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    sem = asyncio.Semaphore(CONCURRENCY)
    haiku = HaikuClassifier()
    async with LegiScanClient() as ls:
        verdicts = await asyncio.gather(*(_evaluate(ls, sem, haiku, c) for c in cands))

    def _active(v: dict) -> bool:
        if v["status"] == "enacted":
            return True
        la = v.get("last_action")
        return bool(la and la.year >= args.active_since)

    to_insert = [v for v in verdicts if v["insert"] and _active(v)]
    stale = [v for v in verdicts if v["insert"] and not _active(v)]
    excluded = [v for v in verdicts if not v["insert"] and "excluded" in v["reason"]]
    dropped = [v for v in verdicts if not v["insert"] and "excluded" not in v["reason"]]
    print(f"(also skipped {len(stale)} relevant-but-stale non-enacted bills pre-{args.active_since})")

    from collections import Counter
    print(f"\n{len(verdicts)} candidates -> {len(to_insert)} to add, "
          f"{len(excluded)} vetoed/failed, {len(dropped)} not-relevant/error\n")
    print("to-add by instrument:", dict(Counter(v["hr"].instrument_type for v in to_insert)))
    print("to-add by status:    ", dict(Counter(v["status"] for v in to_insert)))
    print()
    for v in sorted(to_insert, key=lambda v: (v["cand"]["state"], v["status"])):
        c = v["cand"]
        print(f"  + {c['state']:3} {(c['bill_number'] or ''):9} {v['status']:9} {v['hr'].instrument_type:16} {v['title'][:46]}")
    if dropped:
        print("\n  dropped (Haiku not-relevant / error):")
        for v in dropped:
            print(f"  - {v['cand']['state']:3} {(v['cand']['bill_number'] or ''):9} {v['reason'][:60]}  {v['title'][:34] if v.get('title') else v['cand']['title'][:34]}")

    if not args.commit:
        print("\n(dry run — re-run with --commit to write.)")
        await engine.dispose()
        return

    inserted = updated = 0
    async with Session() as db:
        for v in to_insert:
            c = v["cand"]
            norm = _normalize_bill_number(c["bill_number"] or "")
            bid = int(c["bill_id"])
            hr = v["hr"]
            existing = (await db.execute(select(Bill).where(
                (Bill.legiscan_bill_id == bid) | ((Bill.state == c["state"]) & (Bill.bill_number == norm))
            ))).scalars().first()
            values = dict(
                legiscan_bill_id=bid, state=c["state"], bill_number=norm, title=v["title"], description=v["desc"],
                status=v["status"], status_date=v["last_action"], last_action_date=v["last_action"],
                source_url=v["source_url"], epr_relevant=True, confidence_score=hr.confidence,
                material_categories=hr.material_categories, instrument_type=hr.instrument_type,
                urgency=hr.urgency, policy_stance=hr.stance, stance_source="ai", ai_summary=v["desc"],
                last_fetched_at=datetime.now(timezone.utc),
            )
            if existing:
                for k, val in values.items():
                    setattr(existing, k, val)
                updated += 1
            else:
                db.add(Bill(**values))
                inserted += 1
        await db.commit()
    print(f"\nINSERTED {inserted}, UPDATED {updated}.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
