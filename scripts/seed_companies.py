"""Seed the database with curated companies from data/seed/target_companies.json.

Idempotent: resolves existing companies via EntityResolver before inserting.
Safe to run multiple times -- materials and presences are wholesale-replaced per run.

Usage:
    .venv/Scripts/python scripts/seed_companies.py
"""
import asyncio
import json
import sys
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models import Company, CompanyAlias, CompanyMaterial, CompanyStatePresence, EntityMatchQueue
from app.company_intel.resolver import EntityResolver

SEED_PATH = Path(__file__).parent.parent / "data" / "seed" / "target_companies.json"


async def seed_companies() -> None:
    with open(SEED_PATH) as f:
        entries = json.load(f)

    company_count = 0
    alias_count = 0
    material_count = 0
    presence_count = 0

    async with AsyncSessionLocal() as db:
        for entry in entries:
            name: str = entry["name"]
            duns: str | None = entry.get("duns_number")
            cik: str | None = entry.get("cik")
            epa_id: str | None = entry.get("epa_registry_id")

            resolver = EntityResolver(db)
            company, confidence = await resolver.resolve(
                candidate_name=name,
                source="seed_file",
                duns=duns,
                cik=cik,
                epa_id=epa_id,
            )

            if company is None:
                # No match found — create new company
                company = Company(
                    name=name,
                    duns_number=duns,
                    cik=cik,
                    epa_registry_id=epa_id,
                    hq_state=entry.get("hq_state"),
                    naics_codes=entry.get("naics_codes"),
                    operating_states=entry.get("operating_states"),
                    total_annual_volume_tonnes=entry.get("total_annual_volume_tonnes"),
                    volume_source=entry.get("volume_source"),
                    volume_confidence=entry.get("volume_confidence"),
                )
                db.add(company)
                await db.flush()  # get company.id assigned
                print(f"  [new]    {name}")
            else:
                # Update fields on existing company
                company.hq_state = entry.get("hq_state")
                company.naics_codes = entry.get("naics_codes")
                company.operating_states = entry.get("operating_states")
                company.total_annual_volume_tonnes = entry.get("total_annual_volume_tonnes")
                company.volume_source = entry.get("volume_source")
                company.volume_confidence = entry.get("volume_confidence")
                if duns:
                    company.duns_number = duns
                if cik:
                    company.cik = cik
                if epa_id:
                    company.epa_registry_id = epa_id
                print(f"  [update] {name}")

            company_count += 1

            # Clear any entity_match_queue entries created by the resolver
            # during this same seeding run (resolver queues unknowns on first pass
            # before the company record exists).
            await db.execute(
                delete(EntityMatchQueue).where(
                    EntityMatchQueue.candidate_name == name,
                    EntityMatchQueue.source == "seed_file",
                    EntityMatchQueue.resolved == False,  # noqa: E712
                )
            )

            # Upsert canonical name as an alias
            all_aliases = [name] + list(entry.get("aliases", []))
            for alias_name in all_aliases:
                stmt = (
                    pg_insert(CompanyAlias)
                    .values(
                        company_id=company.id,
                        alias_name=alias_name,
                        source="seed_file",
                        match_confidence=1.0,
                        verified=True,
                    )
                    .on_conflict_do_update(
                        constraint="uq_alias_source",
                        set_={"company_id": company.id, "match_confidence": 1.0, "verified": True},
                    )
                )
                await db.execute(stmt)
                alias_count += 1

            # Wholesale replace materials
            await db.execute(
                delete(CompanyMaterial).where(CompanyMaterial.company_id == company.id)
            )
            for mat in entry.get("materials", []):
                db.add(
                    CompanyMaterial(
                        company_id=company.id,
                        material_category=mat["material_category"],
                        annual_volume_tonnes=mat.get("annual_volume_tonnes"),
                        volume_confidence=mat.get("volume_confidence"),
                        source=mat.get("source"),
                    )
                )
                material_count += 1

            # Wholesale replace state presences
            await db.execute(
                delete(CompanyStatePresence).where(CompanyStatePresence.company_id == company.id)
            )
            for pres in entry.get("state_presences", []):
                db.add(
                    CompanyStatePresence(
                        company_id=company.id,
                        state=pres["state"],
                        presence_type=pres["presence_type"],
                        is_primary=pres.get("is_primary", False),
                    )
                )
                presence_count += 1

        await db.commit()

    print(
        f"\nSeeded {company_count} companies, "
        f"{alias_count} aliases, "
        f"{material_count} materials, "
        f"{presence_count} presences."
    )


if __name__ == "__main__":
    asyncio.run(seed_companies())
