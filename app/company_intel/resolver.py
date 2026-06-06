"""Entity resolution protocol — maps candidate name strings to Company records.

Resolution priority (5 steps):
  1. Hard identifier match (DUNS, CIK, EPA Registry ID)
  2. Exact alias match (case-insensitive)
  3. Fuzzy pg_trgm match (similarity >= 0.85)
  4. Queue unresolved candidates in entity_match_queue
  5. Never auto-create a Company from a fuzzy match alone
"""
import uuid

import structlog
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Company, CompanyAlias, EntityMatchQueue

log = structlog.get_logger()

FUZZY_THRESHOLD = 0.85


class EntityResolver:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def resolve(
        self,
        candidate_name: str,
        source: str,
        duns: str | None = None,
        cik: str | None = None,
        epa_id: str | None = None,
    ) -> tuple[Company | None, float]:
        """Resolve a candidate name to a Company.

        Returns (company, confidence) where confidence is 0.0–1.0.
        Returns (None, best_confidence) when queued for manual review.
        """

        # Step 1 — Hard identifier match
        if duns or cik or epa_id:
            conditions = []
            if duns:
                conditions.append(Company.duns_number == duns)
            if cik:
                conditions.append(Company.cik == cik)
            if epa_id:
                conditions.append(Company.epa_registry_id == epa_id)

            result = await self.db.execute(
                select(Company).where(or_(*conditions)).limit(1)
            )
            company = result.scalar_one_or_none()
            if company:
                log.info(
                    "entity_resolve_exact_id",
                    candidate=candidate_name,
                    company_id=str(company.id),
                    company_name=company.name,
                )
                return company, 1.0

        # Step 2 — Exact alias match (case-insensitive)
        result = await self.db.execute(
            select(CompanyAlias)
            .where(
                CompanyAlias.alias_name.ilike(candidate_name)
            )
            .options(selectinload(CompanyAlias.company))
            .limit(1)
        )
        alias = result.scalar_one_or_none()
        if alias and alias.company:
            confidence = alias.match_confidence if alias.match_confidence is not None else 0.95
            log.info(
                "entity_resolve_exact_alias",
                candidate=candidate_name,
                company_id=str(alias.company.id),
                company_name=alias.company.name,
                confidence=confidence,
            )
            return alias.company, confidence

        # Step 3 — Fuzzy trgm match
        fuzzy_result = (
            await self.db.execute(
                text(
                    "SELECT company_id, alias_name, "
                    "similarity(alias_name, :name) AS sim "
                    "FROM company_alias "
                    "WHERE similarity(alias_name, :name) >= :threshold "
                    "ORDER BY sim DESC "
                    "LIMIT 1"
                ),
                {"name": candidate_name, "threshold": FUZZY_THRESHOLD},
            )
        ).first()

        if fuzzy_result:
            company_id: uuid.UUID = fuzzy_result.company_id
            sim: float = float(fuzzy_result.sim)
            company_result = await self.db.execute(
                select(Company).where(Company.id == company_id)
            )
            company = company_result.scalar_one_or_none()
            if company:
                log.info(
                    "entity_resolve_fuzzy",
                    candidate=candidate_name,
                    company_id=str(company.id),
                    company_name=company.name,
                    similarity=sim,
                )
                return company, sim

        # Step 4 — Queue for manual review
        suggested_id: uuid.UUID | None = (
            uuid.UUID(str(fuzzy_result.company_id)) if fuzzy_result else None
        )
        best_confidence: float = float(fuzzy_result.sim) if fuzzy_result else 0.0

        queue_entry = EntityMatchQueue(
            candidate_name=candidate_name,
            source=source,
            suggested_company_id=suggested_id,
            confidence=best_confidence,
            resolved=False,
        )
        self.db.add(queue_entry)
        await self.db.flush()

        log.info(
            "entity_resolve_queued",
            candidate=candidate_name,
            suggested_company_id=str(suggested_id) if suggested_id else None,
            confidence=best_confidence,
        )
        return None, best_confidence
