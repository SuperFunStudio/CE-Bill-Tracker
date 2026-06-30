"""Classify foreign (FR/UK/JP) bills that were ingested but never classified — e.g. rows written by an
ingest run that committed the fetch loop but crashed before the classification stage. Re-fetches
nothing; just runs the region-aware ClassificationPipeline over the pending rows (skip_keyword_filter,
the curated-source path). Idempotent: re-running only re-touches rows still at the unclassified sentinel.

    venv/Scripts/python scripts/reclassify_foreign_pending.py            # FR+UK+JP pending
    venv/Scripts/python scripts/reclassify_foreign_pending.py --region FR
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def _run(regions: list[str]) -> None:
    from sqlalchemy import or_, select

    from app.classification.pipeline import ClassificationPipeline
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models import Bill

    async with AsyncSessionLocal() as db:
        pending = list(
            (
                await db.execute(
                    select(Bill)
                    .where(
                        Bill.region.in_(regions),
                        or_(Bill.confidence_score.is_(None), Bill.confidence_score == -1.0),
                    )
                    .order_by(Bill.id)
                )
            ).scalars().all()
        )
    print(f"pending unclassified across {regions}: {len(pending)}")
    if not pending:
        return

    chunk = max(1, settings.max_haiku_calls_per_run)
    done = 0
    for i in range(0, len(pending), chunk):
        ids = [b.id for b in pending[i : i + chunk]]
        async with AsyncSessionLocal() as db:
            bills = list((await db.execute(select(Bill).where(Bill.id.in_(ids)))).scalars().all())
            res = await ClassificationPipeline().run(db, bills, skip_keyword_filter=True)
            done += res.classified_haiku
        print(f"  classified {done}/{len(pending)} (haiku={res.classified_haiku}, sonnet={res.extracted_sonnet})")

    # Final tally
    from sqlalchemy import func
    async with AsyncSessionLocal() as db:
        for r in regions:
            total = (await db.execute(select(func.count()).select_from(Bill).where(Bill.region == r))).scalar_one()
            rel = (await db.execute(select(func.count()).select_from(Bill).where(Bill.region == r, Bill.ce_relevant.is_(True)))).scalar_one()
            print(f"  {r}: total={total} ce_relevant={rel}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default=None, help="Single region (default: FR,UK,JP).")
    ap.add_argument("--sonnet", action="store_true",
                    help="Also run Sonnet compliance extraction (slower; can trip pool idle-ping on long runs). "
                         "Default: Haiku-only relevance pass — run Sonnet extraction separately.")
    args = ap.parse_args()
    os.environ["ENABLE_LLM_CLASSIFICATION"] = "true"
    # Haiku-only by default: it sets ce_relevant/instrument/materials (the coverage signal). Sonnet is
    # the heavy compliance_details extraction whose no-transaction external calls trigger the pool
    # pre-ping MissingGreenlet on a long bulk run — opt in only when extracting detail.
    os.environ["ENABLE_SONNET_EXTRACTION"] = "true" if args.sonnet else "false"
    regions = [args.region.upper()] if args.region else ["FR", "UK", "JP"]
    asyncio.run(_run(regions))


if __name__ == "__main__":
    main()
