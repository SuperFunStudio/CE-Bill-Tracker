"""Run the Sonnet compliance extraction over already-classified FOREIGN bills (region-filtered).

Background: for US bills, Stage-3 (Sonnet) compliance detail — including the `effective_date` that
powers the Insights "laws in force over time" chart — is filled by scripts/backfill_deadlines.py.
But that script is hard-gated on `openstates_id`, so it never touches foreign law. Foreign bills only
get `compliance_details` when the ClassificationPipeline's Sonnet stage runs, and the standard foreign
onboarding is Haiku-only (relevance) — so freshly-ingested foreign regions have ce_relevant set but no
compliance_details, and thus don't plot on the effective-date-keyed laws-in-force chart.

This script closes that gap: it runs SonnetExtractor over the ce_relevant bills in the given
region(s) that have no compliance_details yet, writes `compliance_details` (raw_json) + creates
ComplianceDeadline rows, exactly like ClassificationPipeline Stage 3.

MissingGreenlet-safe by construction: all network I/O (Sonnet) happens with NO DB session open, and
each bill's write uses a fresh short-lived session committed immediately — so no pooled connection is
ever held idle across an external call (the failure mode the memory warns about for bulk foreign Sonnet).

    # via the Cloud SQL proxy on 5434 (dev DB):
    venv/Scripts/python scripts/extract_foreign_compliance.py --region CN,CA,AU \
        --dsn "postgresql://signalscout:PW@127.0.0.1:5434/signalscout_dev" [--dry-run] [--limit N]

Costs Anthropic (Sonnet) API calls — one per bill. Always --dry-run first. Idempotent + re-runnable
(only picks up bills still missing compliance_details).
"""
import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def _run(regions: list[str], limit: int, dry_run: bool) -> None:
    from sqlalchemy import select

    from app.classification.sonnet_extractor import SonnetExtractor
    from app.database import AsyncSessionLocal
    from app.models import Bill, BillText, ComplianceDeadline

    # Candidate ids: ce_relevant foreign bills in-region that were never Sonnet-extracted.
    async with AsyncSessionLocal() as db:
        ids = list(
            (
                await db.execute(
                    select(Bill.id)
                    .where(
                        Bill.region.in_(regions),
                        Bill.ce_relevant.is_(True),
                        Bill.compliance_details.is_(None),
                    )
                    .order_by(Bill.id)
                    .limit(limit)
                )
            ).scalars().all()
        )
    print(f"candidates missing compliance_details across {regions}: {len(ids)}")
    if dry_run or not ids:
        return

    extractor = SonnetExtractor()
    done = eff = 0
    for i, bill_id in enumerate(ids, 1):
        # 1. Read the bill fields + full text (short session, released before the Sonnet call).
        async with AsyncSessionLocal() as db:
            bill = (await db.execute(select(Bill).where(Bill.id == bill_id))).scalar_one_or_none()
            if bill is None:
                continue
            state, bill_number, title, region = bill.state, bill.bill_number, bill.title, bill.region
            text = (
                await db.execute(select(BillText.text).where(BillText.bill_id == bill_id))
            ).scalar_one_or_none() or ""
        if not text:
            print(f"  [{i}/{len(ids)}] bill {bill_id}: no text, skip")
            continue

        # 2. Sonnet call — NO DB session open here (the MissingGreenlet-safety guarantee).
        try:
            extraction = await extractor.extract(
                state=state, bill_number=bill_number or "", title=title or "",
                full_text=text, region=region,
            )
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(ids)}] bill {bill_id}: sonnet failed: {e!r}")
            continue

        # 3. Persist in a fresh short session, committed immediately.
        async with AsyncSessionLocal() as db:
            bill = (await db.execute(select(Bill).where(Bill.id == bill_id))).scalar_one_or_none()
            if bill is None:
                continue
            bill.compliance_details = extraction.raw_json
            for dl in extraction.deadlines:
                ds = dl.get("date")
                if not ds:
                    continue
                try:
                    dd = date.fromisoformat(ds[:10])
                except (ValueError, TypeError):
                    continue
                db.add(ComplianceDeadline(
                    bill_id=bill.id, region=bill.region, state=bill.state,
                    deadline_type=dl.get("type", "compliance"), deadline_date=dd,
                    description=dl.get("description", ""),
                ))
            await db.commit()
        done += 1
        if extraction.effective_date:
            eff += 1
        if i % 10 == 0 or i == len(ids):
            print(f"  extracted {done}/{len(ids)} (with effective_date: {eff})")

    print(f"done: {done} extracted, {eff} carry an effective_date")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", required=True, help="CSV of region codes, e.g. CN,CA,AU.")
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--limit", type=int, default=500, help="Max bills to process.")
    ap.add_argument("--dry-run", action="store_true", help="Count candidates; no API calls or writes.")
    args = ap.parse_args()

    if args.dsn:
        os.environ["DATABASE_URL"] = args.dsn
    regions = [r.strip().upper() for r in args.region.split(",") if r.strip()]
    asyncio.run(_run(regions, args.limit, args.dry_run))


if __name__ == "__main__":
    main()
