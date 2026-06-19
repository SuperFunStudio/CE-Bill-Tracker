"""Backfill Bill.policy_stance for already-classified (ce_relevant) bills.

A bill's instrument_type says *which* policy it touches; policy_stance says which
*direction* it pushes that policy: "advances" (establish/strengthen/expand, or repeal a
preemption), "weakens" (exempt/narrow/repeal/preempt), or "neutral" (admin/study/ambiguous).

Two modes:

  --mode heuristic   Free. Sets policy_stance="weakens" (stance_source="heuristic") on bills
                     whose title/description match a strong weaken phrasing, as a provisional
                     tag visible before any AI spend. Leaves everything else untouched.

  --mode ai          Runs the Haiku classifier (now emitting a "stance" field) over the bills
                     and writes policy_stance + stance_source="ai". Authoritative; overwrites
                     heuristic tags. Costs ~1 Haiku call per bill.

Examples:
    python scripts/classify_stance.py --mode heuristic
    python scripts/classify_stance.py --mode ai                 # all ce_relevant bills
    python scripts/classify_stance.py --mode ai --only-missing  # skip bills already stance_source="ai"
    python scripts/classify_stance.py --mode ai --limit 50 --dry-run
"""
import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Strong phrasings that the bill itself narrows/repeals/exempts a policy. Deliberately tighter
# than a bare "exempt" (which appears in nearly every establishing bill's small-producer
# carve-out). This is a candidate-finder, not ground truth — the AI pass corrects it.
STRONG_WEAKEN = re.compile(
    r"\bexempt(s)?\b[^.]{0,60}\bfrom\b"
    r"|\bprovides? (an |a )?exemption\b"
    r"|\brepeals?\b"
    r"|\brollback\b|\broll back\b"
    r"|\bnarrow(s|ing)? the\b"
    r"|\blimit(s|ing)? the (authority|application|scope)\b",
    re.IGNORECASE,
)


async def run_heuristic(dry_run: bool) -> None:
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import Bill

    async with AsyncSessionLocal() as db:
        bills = (await db.execute(
            select(Bill).where(Bill.ce_relevant == True)  # noqa: E712
        )).scalars().all()

        hits = 0
        for b in bills:
            blob = " ".join(filter(None, [b.title, b.description])) or ""
            if STRONG_WEAKEN.search(blob):
                hits += 1
                if not dry_run:
                    b.policy_stance = "weakens"
                    b.stance_source = "heuristic"
        print(f"heuristic: {hits} of {len(bills)} ce_relevant bills tagged 'weakens'"
              + (" (dry run, not written)" if dry_run else ""))
        if not dry_run:
            await db.commit()


async def run_ai(limit: int | None, only_missing: bool, dry_run: bool, concurrency: int) -> None:
    from collections import Counter
    from sqlalchemy import or_, select
    from app.classification.haiku_classifier import HaikuClassifier
    from app.database import AsyncSessionLocal
    from app.models import Bill

    classifier = HaikuClassifier()
    sem = asyncio.Semaphore(concurrency)
    counts: Counter = Counter()
    failures = 0

    async with AsyncSessionLocal() as db:
        q = select(Bill).where(Bill.ce_relevant == True)  # noqa: E712
        if only_missing:
            q = q.where(or_(Bill.stance_source.is_(None), Bill.stance_source != "ai"))
        q = q.order_by(Bill.id)
        if limit:
            q = q.limit(limit)
        bills = (await db.execute(q)).scalars().all()
        print(f"ai: classifying stance for {len(bills)} bills (concurrency={concurrency})...")

        async def classify_one(b: Bill):
            nonlocal failures
            async with sem:
                try:
                    hr = await classifier.classify(
                        state=b.state,
                        bill_number=b.bill_number or "",
                        title=b.title or "",
                        description=b.description or "",
                    )
                except Exception as e:
                    failures += 1
                    print(f"  [fail] {b.state} {b.bill_number}: {type(e).__name__}: {e}")
                    return
                counts[hr.stance] += 1
                if not dry_run:
                    b.policy_stance = hr.stance
                    b.stance_source = "ai"

        # Process in chunks so we commit progress periodically rather than holding 1000+ dirty rows.
        CHUNK = 100
        for i in range(0, len(bills), CHUNK):
            chunk = bills[i:i + CHUNK]
            await asyncio.gather(*(classify_one(b) for b in chunk))
            if not dry_run:
                await db.commit()
            print(f"  ...{min(i + CHUNK, len(bills))}/{len(bills)} done")

    print(f"\nai stance distribution: {dict(counts)}  (failures: {failures})"
          + (" (dry run, not written)" if dry_run else ""))


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["heuristic", "ai"], required=True)
    ap.add_argument("--limit", type=int, default=None, help="Max bills (ai mode).")
    ap.add_argument("--only-missing", action="store_true",
                    help="ai mode: skip bills already stance_source='ai'.")
    ap.add_argument("--concurrency", type=int, default=8, help="ai mode: parallel Haiku calls.")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = ap.parse_args()

    if args.mode == "heuristic":
        await run_heuristic(args.dry_run)
    else:
        await run_ai(args.limit, args.only_missing, args.dry_run, args.concurrency)


if __name__ == "__main__":
    asyncio.run(main())
