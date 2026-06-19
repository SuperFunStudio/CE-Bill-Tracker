"""
Manual smoke test for the ingestion + classification pipeline.
Uses real API keys. Limit to a single state to minimize costs.

Usage:
    python scripts/test_pipeline.py --state OR --limit 5
    python scripts/test_pipeline.py --state CA --limit 10 --classify
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main(state: str, limit: int, classify: bool):
    from app.database import AsyncSessionLocal
    from app.ingestion.coordinator import IngestionCoordinator
    from sqlalchemy import select, func
    from app.models import Bill

    print(f"\n=== SignalScout Pipeline Smoke Test ===")
    print(f"State: {state} | Limit behavior: first {limit} bills displayed\n")

    # Step 1: Ingest
    print("Step 1: Running ingestion for", state)
    async with AsyncSessionLocal() as db:
        coordinator = IngestionCoordinator()
        summary = await coordinator.run_full_cycle(db, state_filter=state)
        print(f"  Ingestion result: {summary}")

        # Show what we got
        result = await db.execute(
            select(Bill)
            .where(Bill.state == state)
            .order_by(Bill.last_action_date.desc().nullslast())
            .limit(limit)
        )
        bills = result.scalars().all()
        print(f"\nTop {limit} bills in {state}:")
        for b in bills:
            print(f"  [{b.status or '?':20}] {b.bill_number or '':15} {(b.title or '')[:60]}")

        # Step 2: Keyword filter
        print("\nStep 2: Keyword filter")
        from app.classification.keywords import KeywordFilter
        kf = KeywordFilter()
        all_bills_result = await db.execute(select(Bill).where(Bill.state == state))
        all_bills = all_bills_result.scalars().all()
        passed = [b for b in all_bills if kf.passes_threshold(b.title or "", b.description or "")]
        print(f"  {len(passed)}/{len(all_bills)} bills passed keyword filter")
        for b in passed[:5]:
            score = kf.score(b.title or "", b.description or "")
            print(f"    ✓ {b.bill_number}: {score.material_hints} (score={score.score:.1f})")

        # Step 3: Optional LLM classify
        if classify:
            print("\nStep 3: LLM classification (Haiku) on first 3 keyword-filtered bills")
            from app.classification.haiku_classifier import HaikuClassifier
            hc = HaikuClassifier()
            for b in passed[:3]:
                result = await hc.classify(
                    state=b.state,
                    bill_number=b.bill_number or "",
                    title=b.title or "",
                    description=b.description or "",
                )
                print(f"  {b.bill_number}: relevant={result.is_ce_relevant} "
                      f"confidence={result.confidence:.2f} "
                      f"categories={result.material_categories}")

    print("\n=== Done ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="OR", help="State abbreviation")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--classify", action="store_true", help="Run Haiku classification")
    args = parser.parse_args()
    asyncio.run(main(args.state, args.limit, args.classify))
