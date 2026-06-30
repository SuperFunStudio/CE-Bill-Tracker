"""Force re-classify existing bills (Haiku) to repopulate the current taxonomy on old rows —
multi-value instrument_types + normalized/`hazardous_materials` materials.

Unlike run_classification_cycle (which only touches unclassified bills), this re-runs the classifier
over already-classified rows, scoped by region. Lives under app/ (NOT scripts/) so it ships in the
API image and can run as a Cloud Run job — `python -m app.reclassify` — against Cloud SQL over the
socket, robustly (no laptop/proxy drops). Haiku-only by default (instruments/materials); Sonnet
(compliance_details → pathways/deadlines/design-guide) is a separate, costlier refresh (--sonnet).

Usage:
  python -m app.reclassify                      # every region in the DB, ce_relevant only
  python -m app.reclassify --region EU          # one region
  python -m app.reclassify --region US --max 50 # bounded test
  RECLASSIFY_REGION=EU python -m app.reclassify  # region via env (Cloud Run job exec)
"""
import argparse
import asyncio
import os


async def _run(regions: list[str] | None, relevant_only: bool, max_per: int | None) -> None:
    import structlog
    from sqlalchemy import select

    from app.classification.pipeline import ClassificationPipeline
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models import Bill

    log = structlog.get_logger()
    chunk = max(1, settings.max_haiku_calls_per_run)

    if not regions:
        async with AsyncSessionLocal() as db:
            found = {r[0] for r in (await db.execute(select(Bill.region).distinct())).all() if r[0]}
        # Small regions first, US (the big one) last, so quick wins land early.
        regions = [r for r in sorted(found) if r != "US"] + (["US"] if "US" in found else [])

    summary: dict[str, int] = {}
    for region in regions:
        async with AsyncSessionLocal() as db:
            q = select(Bill.id).where(Bill.region == region)
            if relevant_only:
                q = q.where(Bill.ce_relevant.is_(True))
            ids = [r[0] for r in (await db.execute(q.order_by(Bill.id))).all()]
        if max_per:
            ids = ids[:max_per]
        done = 0
        for i in range(0, len(ids), chunk):
            cids = ids[i : i + chunk]
            async with AsyncSessionLocal() as db:
                bills = list(
                    (await db.execute(select(Bill).where(Bill.id.in_(cids)))).scalars().all()
                )
                # Curated, already-in-scope rows: bypass the US keyword gate, re-run Haiku on all.
                # source="reclassify" tags this run's audit rows (ClassificationChange) so the set of
                # bills it moves in/out of scope is queryable and recoverable.
                await ClassificationPipeline().run(
                    db, bills, skip_keyword_filter=True, source="reclassify"
                )
            done += len(cids)
            log.info("reclassify_progress", region=region, done=done, total=len(ids))
        summary[region] = len(ids)
        print(f"reclassified region={region}: {len(ids)} bills", flush=True)
    print(f"DONE reclassify: {summary}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default=os.environ.get("RECLASSIFY_REGION"),
                    help="Region code (e.g. EU). Omit to do every region in the DB.")
    ap.add_argument("--all-bills", action="store_true",
                    help="Re-classify ALL bills in the region, not just ce_relevant (heavier).")
    ap.add_argument("--sonnet", action="store_true",
                    help="Also run Sonnet extraction (compliance_details). Default Haiku-only.")
    ap.add_argument("--max", type=int, default=None, help="Cap bills per region (testing).")
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to env DATABASE_URL).")
    args = ap.parse_args()

    if args.dsn:
        os.environ["DATABASE_URL"] = args.dsn
    # Forced on for the run; Sonnet off unless asked (instruments/materials come from Haiku).
    os.environ["ENABLE_LLM_CLASSIFICATION"] = "true"
    os.environ["ENABLE_SONNET_EXTRACTION"] = "true" if args.sonnet else "false"

    regions = [args.region.upper()] if args.region else None
    asyncio.run(_run(regions, relevant_only=not args.all_bills, max_per=args.max))


if __name__ == "__main__":
    main()
