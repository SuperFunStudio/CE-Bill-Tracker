"""Backfill federal-action enrichment: ce_relevant, preemption_risk, ai_summary, material_categories.

The Federal Register ingestion (app/ingestion/coordinator.py:run_federal_cycle) now classifies new
actions inline, but rows ingested before that wiring existed are unclassified — preemption_risk is
NULL and ce_relevant is the default False. This script runs the FederalClassifier over existing
rows so the noisy raw feed becomes a usable federal-friction signal.

The classifier filters feed noise (antidumping/trade/antitrust notices score is_relevant=false) and
scores preemption_risk none/low/medium/high — the "where is the federal government adding friction"
number surfaced by GET /federal-actions?preemption_risk=high.

Examples:
    python scripts/classify_federal.py --only-missing            # classify rows never classified
    python scripts/classify_federal.py --only-missing --dry-run  # report distribution, write nothing
    python scripts/classify_federal.py --limit 20                # re-classify the 20 newest
    python scripts/classify_federal.py --concurrency 4
"""
import argparse
import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run(limit: int | None, only_missing: bool, dry_run: bool, concurrency: int) -> None:
    from sqlalchemy import select
    from app.classification.federal_classifier import FederalClassifier
    from app.database import AsyncSessionLocal
    from app.models import FederalAction

    classifier = FederalClassifier()
    sem = asyncio.Semaphore(concurrency)
    risk_counts: Counter = Counter()
    relevant = 0
    failures = 0

    async with AsyncSessionLocal() as db:
        q = select(FederalAction)
        if only_missing:
            # Never-classified rows: ai_summary is NULL (set on every classify, even irrelevant).
            q = q.where(FederalAction.ai_summary.is_(None))
        q = q.order_by(FederalAction.published_date.desc().nullslast())
        if limit:
            q = q.limit(limit)
        actions = (await db.execute(q)).scalars().all()
        print(f"classifying {len(actions)} federal actions (concurrency={concurrency})...")

        async def classify_one(a: FederalAction):
            nonlocal relevant, failures
            async with sem:
                abstract = (a.raw_data or {}).get("abstract", "") if a.raw_data else ""
                try:
                    fr = await classifier.classify(
                        title=a.title or "",
                        agency=a.agency or "",
                        action_type=a.action_type or "",
                        abstract=abstract,
                    )
                except Exception as e:
                    failures += 1
                    print(f"  [fail] {a.federal_register_document_number}: {type(e).__name__}: {e}")
                    return
                risk_counts[fr.preemption_risk] += 1
                if fr.is_relevant:
                    relevant += 1
                if not dry_run:
                    a.ce_relevant = fr.is_relevant
                    a.preemption_risk = fr.preemption_risk
                    a.ai_summary = fr.summary
                    a.material_categories = fr.material_categories

        CHUNK = 50
        for i in range(0, len(actions), CHUNK):
            chunk = actions[i:i + CHUNK]
            await asyncio.gather(*(classify_one(a) for a in chunk))
            if not dry_run:
                await db.commit()
            print(f"  ...{min(i + CHUNK, len(actions))}/{len(actions)} done")

    print(f"\nrelevant: {relevant}/{sum(risk_counts.values())}")
    print(f"preemption_risk distribution: {dict(risk_counts)}  (failures: {failures})"
          + (" (dry run, not written)" if dry_run else ""))


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None, help="Max actions to classify.")
    ap.add_argument("--only-missing", action="store_true",
                    help="Only classify rows never classified (ai_summary IS NULL).")
    ap.add_argument("--concurrency", type=int, default=4, help="Parallel Haiku calls.")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = ap.parse_args()
    await run(args.limit, args.only_missing, args.dry_run, args.concurrency)


if __name__ == "__main__":
    asyncio.run(main())
