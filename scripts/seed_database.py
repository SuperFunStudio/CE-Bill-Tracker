"""
Seed the database with known EPR laws from data/seed/known_epr_laws.json.
Idempotent: uses ON CONFLICT DO UPDATE so safe to run multiple times.
"""
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.dialects.postgresql import insert

from app.database import AsyncSessionLocal, engine, Base
from app.models import Bill, ComplianceDeadline

SEED_PATH = Path(__file__).parent.parent / "data" / "seed" / "known_epr_laws.json"


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


async def seed_known_laws():
    with open(SEED_PATH) as f:
        laws = json.load(f)

    async with AsyncSessionLocal() as db:
        seeded = 0
        for law in laws:
            stmt = insert(Bill).values(
                state=law["state"],
                bill_number=law.get("bill_number"),
                title=law.get("title"),
                description=law.get("ai_summary"),
                status=law.get("status"),
                status_date=_parse_date(law.get("enacted_date")),
                last_action_date=_parse_date(law.get("enacted_date")),
                source_url=law.get("source_url"),
                epr_relevant=True,
                confidence_score=1.0,  # manually verified
                material_categories=law.get("material_categories", []),
                instrument_type=law.get("instrument_type"),
                urgency=law.get("urgency"),
                ai_summary=law.get("ai_summary"),
                compliance_details=law.get("compliance_details"),
            )
            # Conflict on (state, bill_number) — update if exists
            stmt = stmt.on_conflict_do_update(
                constraint=None,
                index_elements=None,
                # Fall back to update by state+bill_number check below
                set_={
                    "status": stmt.excluded.status,
                    "compliance_details": stmt.excluded.compliance_details,
                    "ai_summary": stmt.excluded.ai_summary,
                    "confidence_score": stmt.excluded.confidence_score,
                    "material_categories": stmt.excluded.material_categories,
                },
            ) if False else stmt  # Simplified: just insert, handle duplicates

            # Simple approach: check if exists then insert
            from sqlalchemy import select
            existing = await db.execute(
                select(Bill).where(
                    Bill.state == law["state"],
                    Bill.bill_number == law.get("bill_number"),
                )
            )
            existing_bill = existing.scalar_one_or_none()

            if existing_bill:
                # Update existing using explicit UPDATE to avoid ORM change-detection misses
                from sqlalchemy import update
                await db.execute(
                    update(Bill)
                    .where(Bill.id == existing_bill.id)
                    .values(
                        status=law.get("status"),
                        compliance_details=law.get("compliance_details"),
                        ai_summary=law.get("ai_summary"),
                        confidence_score=1.0,
                        material_categories=law.get("material_categories", []),
                        source_url=law.get("source_url"),
                        urgency=law.get("urgency"),
                        instrument_type=law.get("instrument_type"),
                        title=law.get("title"),
                    )
                )
                bill_obj = existing_bill
            else:
                bill_obj = Bill(
                    state=law["state"],
                    bill_number=law.get("bill_number"),
                    title=law.get("title"),
                    description=law.get("ai_summary"),
                    status=law.get("status"),
                    status_date=_parse_date(law.get("enacted_date")),
                    last_action_date=_parse_date(law.get("enacted_date")),
                    source_url=law.get("source_url"),
                    epr_relevant=True,
                    confidence_score=1.0,
                    material_categories=law.get("material_categories", []),
                    instrument_type=law.get("instrument_type"),
                    urgency=law.get("urgency"),
                    ai_summary=law.get("ai_summary"),
                    compliance_details=law.get("compliance_details"),
                )
                db.add(bill_obj)
                await db.flush()  # Get ID
                seeded += 1

            # Seed compliance deadlines
            compliance = law.get("compliance_details", {})
            for dl in compliance.get("deadlines", []):
                dl_date = _parse_date(dl.get("date"))
                if not dl_date or not bill_obj.id:
                    continue
                # Check if deadline exists
                from sqlalchemy import and_
                existing_dl = await db.execute(
                    select(ComplianceDeadline).where(
                        and_(
                            ComplianceDeadline.bill_id == bill_obj.id,
                            ComplianceDeadline.deadline_date == dl_date,
                            ComplianceDeadline.deadline_type == dl.get("type", "compliance"),
                        )
                    )
                )
                if not existing_dl.scalar_one_or_none():
                    db.add(ComplianceDeadline(
                        bill_id=bill_obj.id,
                        state=law["state"],
                        deadline_type=dl.get("type", "compliance"),
                        deadline_date=dl_date,
                        description=dl.get("description"),
                    ))

        await db.commit()
        print(f"Seeded {seeded} new laws ({len(laws)} total in JSON)")
        print("Spot-check: run 'SELECT state, bill_number, status FROM bills ORDER BY state;' in psql")


async def _disabled() -> None:
    """The known-EPR-laws seed is retired. Its source URLs were wrong (broken dashboard
    links); bill data now comes from the OpenStates dump import
    (scripts/import_openstates_pgdump.py), and migration 005 purges the old seed rows."""
    print("seed_database.py is DISABLED — use scripts/import_openstates_pgdump.py "
          "(seed replaced by OpenStates dump import; see migration 005)")


if __name__ == "__main__":
    asyncio.run(_disabled())
