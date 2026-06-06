"""Demo readiness validation script.

Runs a checklist of data quality checks required before the Oregon NAW demo.
Prints a pass/fail report and exits non-zero if any critical check fails.

Usage:
    .venv/Scripts/python scripts/validate_demo_data.py
    .venv/Scripts/python scripts/validate_demo_data.py --bill "SB 582" --top-n 20
"""
import argparse
import asyncio
import sys
from typing import Any

# Force UTF-8 output on Windows so accented characters (Nestlé, Mondelēz) render correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def run_checks(bill_pattern: str, top_n: int) -> bool:
    """Run all demo readiness checks. Returns True if all critical checks pass."""
    import structlog
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models import (
        Company,
        CompanyStatePresence,
        EntityMatchQueue,
        ExposureBrief,
        ImpactScore,
        Bill,
    )

    log = structlog.get_logger()
    checks_passed = 0
    checks_failed = 0
    warnings = 0

    def _pass(msg: str) -> None:
        nonlocal checks_passed
        checks_passed += 1
        print(f"  [PASS] {msg}")

    def _fail(msg: str) -> None:
        nonlocal checks_failed
        checks_failed += 1
        print(f"  [FAIL] {msg}")

    def _warn(msg: str) -> None:
        nonlocal warnings
        warnings += 1
        print(f"  [WARN] {msg}")

    async with AsyncSessionLocal() as db:
        print("\n" + "=" * 60)
        print("  SIGNALSCOUT DEMO READINESS CHECK")
        print("  Oregon NAW Trial \u2014 July 13, 2026")
        print("=" * 60)

        # ------------------------------------------------------------------
        # Check 1: Total companies in database
        # ------------------------------------------------------------------
        print("\n[1] Company data coverage")
        total_companies_result = await db.execute(select(func.count()).select_from(Company))
        total_companies = total_companies_result.scalar()
        if total_companies and total_companies >= 50:
            _pass(f"{total_companies} companies in database (target: 50+)")
        else:
            _fail(f"Only {total_companies} companies in database (target: 50+)")

        # ------------------------------------------------------------------
        # Check 2: Oregon presence
        # ------------------------------------------------------------------
        print("\n[2] Oregon state presence")
        or_companies_result = await db.execute(
            select(func.count(CompanyStatePresence.company_id.distinct())).where(
                CompanyStatePresence.state == "OR"
            )
        )
        or_companies = or_companies_result.scalar() or 0
        if or_companies >= 20:
            _pass(f"{or_companies} companies with Oregon state presence (target: 20+)")
        else:
            _fail(f"Only {or_companies} companies with Oregon state presence (target: 20+)")

        # ------------------------------------------------------------------
        # Check 3: Entity match queue must be empty
        # ------------------------------------------------------------------
        print("\n[3] Entity resolution queue")
        queue_result = await db.execute(
            select(func.count()).select_from(EntityMatchQueue).where(
                EntityMatchQueue.resolved == False  # noqa: E712
            )
        )
        unresolved = queue_result.scalar() or 0
        if unresolved == 0:
            _pass("Entity match queue is empty (zero unresolved entries)")
        else:
            _fail(f"{unresolved} unresolved entries in entity_match_queue \u2014 MUST resolve before demo")

        # ------------------------------------------------------------------
        # Check 4: Find Oregon SB 582 bill
        # ------------------------------------------------------------------
        print(f"\n[4] Bill: {bill_pattern}")
        bill_result = await db.execute(
            select(Bill).where(
                Bill.state == "OR",
                Bill.bill_number.ilike(f"%{bill_pattern}%"),
                Bill.epr_relevant == True,  # noqa: E712
            ).limit(1)
        )
        bill = bill_result.scalar_one_or_none()

        if bill is None:
            _fail(f"Bill '{bill_pattern}' not found in Oregon EPR bills")
            print("\n  Cannot check scores or briefs without the bill. Exiting early.")
            print(_summary(checks_passed, checks_failed, warnings))
            return checks_failed == 0

        _pass(f"Found: {bill.bill_number} \u2014 {bill.title[:60] if bill.title else 'No title'}...")

        # ------------------------------------------------------------------
        # Check 5: Impact scores exist for top-N companies
        # ------------------------------------------------------------------
        print(f"\n[5] Impact scores (top {top_n} companies for {bill.bill_number})")
        scores_result = await db.execute(
            select(ImpactScore, Company.name)
            .join(Company, ImpactScore.company_id == Company.id)
            .where(ImpactScore.bill_id == bill.id)
            .order_by(ImpactScore.composite_score.desc())
            .limit(top_n)
        )
        scores = scores_result.all()

        if len(scores) >= top_n:
            _pass(f"{len(scores)} impact scores found for {bill.bill_number}")
        elif len(scores) >= 10:
            _warn(f"Only {len(scores)} scores (target: {top_n}). Acceptable for demo.")
        else:
            _fail(f"Only {len(scores)} scores \u2014 run scoring cycle first")

        # ------------------------------------------------------------------
        # Check 6: Cost estimates exist for top companies
        # ------------------------------------------------------------------
        print("\n[6] Cost estimates")
        scores_with_cost = [s for s in scores if s[0].estimated_annual_cost is not None]
        if len(scores_with_cost) >= min(10, len(scores)):
            _pass(f"{len(scores_with_cost)}/{len(scores)} top companies have cost estimates")
        else:
            _warn(f"Only {len(scores_with_cost)}/{len(scores)} have cost estimates")

        # ------------------------------------------------------------------
        # Check 7: Exposure briefs exist for top companies
        # ------------------------------------------------------------------
        print("\n[7] Exposure briefs (top companies)")
        company_ids = [s[0].company_id for s in scores[:top_n]]
        briefs_result = await db.execute(
            select(func.count()).select_from(ExposureBrief).where(
                ExposureBrief.bill_id == bill.id,
                ExposureBrief.company_id.in_(company_ids),
            )
        )
        briefs_count = briefs_result.scalar() or 0
        if briefs_count >= min(top_n, len(scores)):
            _pass(f"{briefs_count}/{len(scores)} top companies have exposure briefs")
        elif briefs_count >= 10:
            _warn(f"{briefs_count}/{len(scores)} briefs \u2014 run pregame_oregon_briefs.py to generate more")
        else:
            _fail(f"Only {briefs_count} briefs \u2014 run pregame_oregon_briefs.py before demo")

        # ------------------------------------------------------------------
        # Check 8: Print top-20 ranking for manual review
        # ------------------------------------------------------------------
        print(f"\n[8] Top-{min(top_n, len(scores))} Oregon ranking for {bill.bill_number} (manual review):")
        print(f"  {'#':<4} {'Company':<40} {'Score':>6} {'Est. Annual Cost':>18}")
        print(f"  {'-'*4} {'-'*40} {'-'*6} {'-'*18}")
        for i, (score, company_name) in enumerate(scores[:top_n], 1):
            cost_str = f"${score.estimated_annual_cost:>14,.0f}" if score.estimated_annual_cost else "           N/A"
            print(f"  {i:<4} {company_name[:40]:<40} {score.composite_score:>6.1f} {cost_str}")

        # ------------------------------------------------------------------
        # Check 9: Verify no null titles in ranked companies
        # ------------------------------------------------------------------
        print("\n[9] Bill metadata completeness")
        if bill.compliance_details:
            _pass(f"compliance_details populated for {bill.bill_number}")
        else:
            _warn(f"No compliance_details on {bill.bill_number} \u2014 cost estimates may be low quality")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(_summary(checks_passed, checks_failed, warnings))
    return checks_failed == 0


def _summary(passed: int, failed: int, warned: int) -> str:
    total = passed + failed
    lines = [
        "",
        "=" * 60,
        f"  RESULT: {passed}/{total} checks passed, {warned} warnings, {failed} failures",
    ]
    if failed == 0:
        lines.append("  STATUS: DEMO READY \u2714")
    else:
        lines.append(f"  STATUS: NOT READY \u2014 fix {failed} failing check(s) before demo")
    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="SignalScout demo readiness checker")
    parser.add_argument("--bill", default="SB 582", help="Bill number pattern to check (default: SB 582)")
    parser.add_argument("--top-n", type=int, default=20, help="Number of top companies to validate (default: 20)")
    args = parser.parse_args()

    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    all_passed = asyncio.run(run_checks(args.bill, args.top_n))
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
