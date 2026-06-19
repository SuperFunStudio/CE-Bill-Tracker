"""Add a single bill that ingestion missed, sourced from LegiScan and classified by Haiku.

The OpenStates dump + keyword filter occasionally drop an in-scope bill (e.g. TX HB 2963,
an enacted digital right-to-repair law, whose title lacks the EPR keywords). This fetches
the bill from LegiScan, runs the SAME Haiku classifier the pipeline uses (so relevance /
instrument_type / materials / stance match everything else), and upserts it.

Idempotent on legiscan_bill_id (and state+bill_number). Defaults to DRY RUN.

Run:
    python scripts/add_bill_from_legiscan.py --state TX --bill "HB 2963" --year 2025
    python scripts/add_bill_from_legiscan.py --state TX --bill "HB 2963" --year 2025 --commit
    python scripts/add_bill_from_legiscan.py --state TX --bill "HB 2963" --year 2025 --commit \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:55432/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.haiku_classifier import TRACKED_INSTRUMENTS, HaikuClassifier  # noqa: E402
from app.ingestion.coordinator import _normalize_bill_number  # noqa: E402
from app.ingestion.legiscan import LegiScanClient  # noqa: E402
from app.models import Bill  # noqa: E402
from scripts.backfill_deadlines_legiscan import _canon, _fetch_text  # noqa: E402

# LegiScan numeric status -> our status vocabulary.
_STATUS = {1: "introduced", 2: "passed_chamber", 3: "passed", 4: "enacted", 5: "vetoed", 6: "failed"}


def _normalize_dsn(dsn: str) -> str:
    for p in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(p):
            return dsn if p == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(p):]
    return dsn


def _parse_date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", required=True)
    ap.add_argument("--bill", required=True, help="e.g. 'HB 2963'")
    ap.add_argument("--year", type=int, default=None, help="session year to disambiguate")
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--commit", action="store_true", help="write (default is dry run)")
    args = ap.parse_args()

    state = args.state.upper()
    norm = _normalize_bill_number(args.bill)
    target = _canon(args.bill)

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url
    engine = create_async_engine(_normalize_dsn(dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with LegiScanClient() as ls:
        # Resolve the LegiScan bill: search then exact bill#/state match.
        results = []
        for y in ([args.year, None] if args.year else [None]):
            try:
                results = await ls.search(args.bill, state=state, year=y)
            except Exception as e:  # noqa: BLE001
                print(f"search error: {e}")
            if any(_canon(r.get("bill_number")) == target and r.get("state") == state for r in results):
                break
        hit = next((r for r in results if _canon(r.get("bill_number")) == target and r.get("state") == state), None)
        if not hit:
            print(f"No LegiScan match for {state} {args.bill} (year={args.year}).")
            await engine.dispose()
            return
        bill_id = int(hit["bill_id"])
        meta = await ls.get_bill(bill_id)
        status = _STATUS.get(int(meta.get("status", 0) or 0), "introduced")
        title = meta.get("title") or hit.get("title") or ""
        desc = meta.get("description") or title
        source_url = meta.get("state_link") or hit.get("url")
        last_action = _parse_date(meta.get("status_date") or hit.get("last_action_date"))

        full_text, label = await _fetch_text(ls, bill_id)
        print(f"LegiScan {state} {norm} id={bill_id} status={status} text={len(full_text)}c ({label})")
        print(f"  title: {title[:90]}")

        hr = await HaikuClassifier().classify(
            state=state, bill_number=norm, title=title, description=desc, text_excerpt=full_text)
        relevant = hr.confidence >= 0.4 and (hr.is_ce_relevant or hr.instrument_type in TRACKED_INSTRUMENTS)
        print(f"  Haiku: relevant={relevant} instrument={hr.instrument_type} materials={hr.material_categories} "
              f"conf={hr.confidence} stance={hr.stance} urgency={hr.urgency}")

    async with Session() as db:
        existing = (await db.execute(
            select(Bill).where((Bill.legiscan_bill_id == bill_id) |
                               ((Bill.state == state) & (Bill.bill_number == norm)))
        )).scalars().first()

        values = dict(
            legiscan_bill_id=bill_id, state=state, bill_number=norm, title=title, description=desc,
            status=status, status_date=last_action, last_action_date=last_action, source_url=source_url,
            ce_relevant=relevant, confidence_score=hr.confidence, material_categories=hr.material_categories,
            instrument_type=hr.instrument_type, urgency=hr.urgency, policy_stance=hr.stance,
            stance_source="ai", ai_summary=desc, last_fetched_at=datetime.now(timezone.utc),
        )

        if existing:
            print(f"\nAlready in DB (id={existing.id}) — would UPDATE.")
            action = "update"
        else:
            action = "insert"
        if not args.commit:
            print(f"\n(dry run — would {action}. Re-run with --commit to write.)")
            await engine.dispose()
            return

        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
        else:
            db.add(Bill(**values))
        await db.commit()
        print(f"\n{action.upper()}ED {state} {norm} (relevant={relevant}, instrument={hr.instrument_type}).")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
