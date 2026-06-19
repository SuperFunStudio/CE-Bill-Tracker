"""Re-compute all ImpactScore rows using the updated CostEstimator."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


async def main():
    from sqlalchemy import delete, select
    from sqlalchemy.orm import selectinload
    import uuid

    from app.database import AsyncSessionLocal
    from app.models import Bill, Company, ImpactScore
    from app.scoring.engine import make_engine

    engine = make_engine()

    async with AsyncSessionLocal() as db:
        companies_result = await db.execute(
            select(Company).options(
                selectinload(Company.materials),
                selectinload(Company.state_presences),
            )
        )
        all_companies = companies_result.scalars().all()

        bills_result = await db.execute(
            select(Bill).where(Bill.ce_relevant == True)  # noqa: E712
        )
        all_bills = bills_result.scalars().all()

        print(f"Re-scoring {len(all_companies)} companies x {len(all_bills)} bills...")

        # Build total volume map
        all_companies_volumes: dict[uuid.UUID, float] = {}
        for company in all_companies:
            total = sum(
                m.annual_volume_tonnes
                for m in company.materials
                if m.annual_volume_tonnes is not None
            )
            if total > 0:
                all_companies_volumes[company.id] = total

        # Delete all existing scores
        await db.execute(delete(ImpactScore))

        # Re-compute
        count = 0
        for company in all_companies:
            for bill in all_bills:
                score = engine.compute(
                    company, bill,
                    company.materials,
                    company.state_presences,
                    all_companies_volumes,
                )
                db.add(score)
                count += 1

        await db.commit()
        print(f"Done. Wrote {count} ImpactScore rows.")

        # Spot-check
        result = await db.execute(
            select(ImpactScore).join(Company).join(Bill)
            .where(Company.name.ilike("%Apple%"))
            .where(Bill.bill_number == "AB 1268 E-Waste")
        )
        row = result.scalar_one_or_none()
        if row:
            from app.models import Bill as B, Company as C
            print(f"\nApple / CA AB 1268 E-Waste:")
            print(f"  estimated_annual_cost: ${row.estimated_annual_cost:,.0f}")
            print(f"  cost_confidence: {row.cost_confidence:.0%}")
            print(f"  fee_basis: {(row.score_breakdown or {}).get('fee_basis')}")
        else:
            print("\nApple / CA AB 1268 not found in scores (may not be ce_relevant or company not matched)")


asyncio.run(main())
