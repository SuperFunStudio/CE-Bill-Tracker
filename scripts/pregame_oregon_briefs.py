"""Pre-generate Oregon exposure briefs for demo.

Fetches the top-N companies by composite score for a given Oregon bill,
then generates (or refreshes) Exposure Briefs for all of them using Claude Sonnet.
Stores results in the exposure_brief table.

Run this before the demo after all seed data and company enrichment is complete.
Requires ENABLE_INTERPRETATION=true in your .env file (PowerShell does not support
inline env var syntax like ENABLE_INTERPRETATION=true python ...).

Usage (PowerShell):
    $env:ENABLE_INTERPRETATION="true"; python scripts/pregame_oregon_briefs.py
Usage (bash/zsh):
    ENABLE_INTERPRETATION=true python scripts/pregame_oregon_briefs.py
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def pregame(bill_pattern: str, top_n: int) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import delete, select
    from sqlalchemy.orm import selectinload

    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models import Bill, Company, ExposureBrief, ImpactScore
    from app.scoring.interpreter import ExposureBriefGenerator

    if not settings.enable_interpretation:
        print(
            "\n[ERROR] ENABLE_INTERPRETATION is False.\n"
            "Set ENABLE_INTERPRETATION=true in your .env before running this script.\n"
        )
        sys.exit(1)

    generator = ExposureBriefGenerator()
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Find the bill
        bill_result = await db.execute(
            select(Bill).where(
                Bill.state == "OR",
                Bill.bill_number.ilike(f"%{bill_pattern}%"),
                Bill.ce_relevant == True,  # noqa: E712
            ).limit(1)
        )
        bill = bill_result.scalar_one_or_none()

        if bill is None:
            print(f"\n[ERROR] Bill '{bill_pattern}' not found in Oregon EPR bills.\n")
            sys.exit(1)

        print(f"\nGenerating briefs for: {bill.bill_number} \u2014 {bill.title or 'No title'}")
        print(f"Top-N: {top_n} | Model: claude-sonnet-4-6\n")

        # Load top-N impact scores with company data
        scores_result = await db.execute(
            select(ImpactScore)
            .options(
                selectinload(ImpactScore.company).selectinload(Company.materials),
                selectinload(ImpactScore.company).selectinload(Company.state_presences),
            )
            .where(ImpactScore.bill_id == bill.id)
            .order_by(ImpactScore.composite_score.desc())
            .limit(top_n)
        )
        scores = scores_result.scalars().all()

        if not scores:
            print("[WARN] No impact scores found for this bill. Run the scoring cycle first.\n")
            sys.exit(1)

        print(f"Found {len(scores)} companies to process.\n")

        generated = 0
        cached = 0
        errors = 0

        for i, impact_score in enumerate(scores, 1):
            company = impact_score.company
            if company is None:
                continue

            # Check for valid existing brief
            existing_result = await db.execute(
                select(ExposureBrief).where(
                    ExposureBrief.company_id == company.id,
                    ExposureBrief.bill_id == bill.id,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing and existing.ttl_expires_at and existing.ttl_expires_at > now:
                cached += 1
                print(f"  [{i:>3}/{len(scores)}] {company.name[:45]:<45} [cached]")
                continue

            # Generate new brief
            print(f"  [{i:>3}/{len(scores)}] {company.name[:45]:<45} [generating...]", end="", flush=True)

            try:
                brief_json = await generator.generate(
                    company_name=company.name,
                    hq_state=company.hq_state,
                    materials=[
                        {
                            "material_category": m.material_category,
                            "annual_volume_tonnes": m.annual_volume_tonnes,
                            "volume_confidence": m.volume_confidence,
                        }
                        for m in company.materials
                    ],
                    state_presences=[
                        {
                            "state": p.state,
                            "presence_type": p.presence_type,
                            "is_primary": p.is_primary,
                        }
                        for p in company.state_presences
                    ],
                    bill_title=bill.title,
                    bill_state=bill.state,
                    bill_number=bill.bill_number,
                    bill_status=bill.status,
                    compliance_details=bill.compliance_details,
                    composite_score=impact_score.composite_score,
                    estimated_annual_cost=impact_score.estimated_annual_cost,
                )

                # Upsert — delete old then insert fresh
                if existing:
                    await db.execute(
                        delete(ExposureBrief).where(
                            ExposureBrief.company_id == company.id,
                            ExposureBrief.bill_id == bill.id,
                        )
                    )

                brief = ExposureBrief(
                    company_id=company.id,
                    bill_id=bill.id,
                    brief_json=brief_json,
                    ttl_expires_at=generator.ttl_timestamp(),
                )
                db.add(brief)
                await db.commit()
                generated += 1
                print(" done")

            except Exception as exc:
                errors += 1
                print(f" ERROR: {exc}")
                await db.rollback()

    print(f"\n{'='*55}")
    print(f"  Generated: {generated}")
    print(f"  Cached (skipped): {cached}")
    print(f"  Errors: {errors}")
    print(f"  Total processed: {generated + cached + errors}")
    print(f"{'='*55}\n")

    if errors > 0:
        print(f"[WARN] {errors} brief(s) failed to generate. Check API key and network.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate Oregon Exposure Briefs for demo")
    parser.add_argument("--bill", default="SB 582", help="Bill number pattern (default: SB 582)")
    parser.add_argument("--top-n", type=int, default=50, help="Number of top companies (default: 50)")
    args = parser.parse_args()

    asyncio.run(pregame(args.bill, args.top_n))


if __name__ == "__main__":
    main()
