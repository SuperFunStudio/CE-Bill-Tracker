"""Backfill Sonnet compliance extraction (`compliance_details`) over already-classified bills.

Unlike the classification pipeline's Stage 3 — which only extracts the high-confidence (>=0.7) bills
of a fresh run, bounded by max_sonnet_calls_per_run — this sweeps EVERY ce_relevant bill that still
lacks `compliance_details`, so a newly-ingested corpus (e.g. the foreign jurisdictions) gets fully
extracted in one pass. It reads persisted text from `bill_texts` (foreign measures have no live text
API), runs the region-aware SonnetExtractor (which windows large omnibus acts — see
sonnet_extractor.select_text_window), writes `compliance_details`, and (re)creates ComplianceDeadline
rows. Idempotent: skips bills that already have `compliance_details` unless --refresh.

Lives under app/ (NOT scripts/) so it ships in the job image and runs as a Cloud Run job —
`python -m app.extract_job` — against Cloud SQL over the socket. Foreign-only by default (US text is
fetched live at classify time, not stored here); pass --include-us to extract US too.

Usage:
  python -m app.extract_job                       # all non-US ce_relevant bills missing compliance
  python -m app.extract_job --region UK           # one region
  python -m app.extract_job --max 20              # bounded test
  python -m app.extract_job --refresh             # re-extract even if compliance_details present
  RECLASSIFY_REGION=PL python -m app.extract_job  # region via env (Cloud Run job exec)
"""
import argparse
import asyncio
import os
from datetime import date


async def _run(regions: list[str] | None, include_us: bool, refresh: bool, max_bills: int | None) -> None:
    import structlog
    from sqlalchemy import select

    from app.classification.sonnet_extractor import SonnetExtractor
    from app.database import AsyncSessionLocal
    from app.models import Bill, BillText, ComplianceDeadline

    log = structlog.get_logger()
    sonnet = SonnetExtractor()

    async with AsyncSessionLocal() as db:
        q = (
            select(Bill.id)
            .join(BillText, BillText.bill_id == Bill.id)  # only bills with persisted text
            .where(Bill.ce_relevant.is_(True))
        )
        if not refresh:
            q = q.where(Bill.compliance_details.is_(None))
        if regions:
            q = q.where(Bill.region.in_(regions))
        elif not include_us:
            q = q.where(Bill.region != "US")
        ids = [r[0] for r in (await db.execute(q.order_by(Bill.id))).all()]

    if max_bills:
        ids = ids[:max_bills]
    log.info("extract_job_start", candidates=len(ids), refresh=refresh)

    done = wrote = failed = 0
    for bill_id in ids:
        # New session per bill so a slow Sonnet call never holds a transaction open (mirrors the
        # pipeline Stage 3 rationale: no locks held across the external call).
        async with AsyncSessionLocal() as db:
            bill = (await db.execute(select(Bill).where(Bill.id == bill_id))).scalar_one_or_none()
            if bill is None:
                continue
            text = (
                await db.execute(select(BillText.text).where(BillText.bill_id == bill_id))
            ).scalar_one_or_none() or ""
            if not text.strip():
                continue
            try:
                extraction = await sonnet.extract(
                    state=bill.state,
                    bill_number=bill.bill_number or "",
                    title=bill.title or "",
                    full_text=text,
                    region=bill.region,
                )
                bill.compliance_details = extraction.raw_json

                # Replace this bill's deadlines so a --refresh re-run doesn't accumulate duplicates.
                existing = (
                    await db.execute(
                        select(ComplianceDeadline).where(ComplianceDeadline.bill_id == bill_id)
                    )
                ).scalars().all()
                for cd in existing:
                    await db.delete(cd)
                for dl in extraction.deadlines:
                    deadline_date_str = dl.get("date")
                    if not deadline_date_str:
                        continue
                    try:
                        deadline_date = date.fromisoformat(deadline_date_str[:10])
                    except (ValueError, TypeError):
                        continue
                    db.add(
                        ComplianceDeadline(
                            bill_id=bill.id,
                            region=bill.region,
                            state=bill.state,
                            deadline_type=dl.get("type", "compliance"),
                            deadline_date=deadline_date,
                            description=dl.get("description", ""),
                        )
                    )
                await db.commit()
                wrote += 1
            except Exception as e:  # noqa: BLE001 — one bad bill must not abort the sweep
                await db.rollback()
                failed += 1
                log.error("extract_job_failed", bill_id=bill_id, error=str(e))
        done += 1
        if done % 25 == 0:
            log.info("extract_job_progress", done=done, total=len(ids), wrote=wrote, failed=failed)

    log.info("extract_job_complete", done=done, wrote=wrote, failed=failed)
    print(f"DONE extract_job: candidates={len(ids)} wrote={wrote} failed={failed}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default=os.environ.get("RECLASSIFY_REGION"),
                    help="Single region code (e.g. UK). Omit for all non-US (or all with --include-us).")
    ap.add_argument("--include-us", action="store_true",
                    help="Also extract US bills (reads stored text; US text must be backfilled first).")
    ap.add_argument("--refresh", action="store_true",
                    help="Re-extract bills that already have compliance_details (default: skip them).")
    ap.add_argument("--max", type=int, default=None, help="Cap bills processed (testing).")
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to env DATABASE_URL).")
    args = ap.parse_args()

    if args.dsn:
        os.environ["DATABASE_URL"] = args.dsn

    regions = [args.region.upper()] if args.region else None
    asyncio.run(_run(regions, include_us=args.include_us, refresh=args.refresh, max_bills=args.max))


if __name__ == "__main__":
    main()
