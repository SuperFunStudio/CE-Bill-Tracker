"""EPA Facility Registry System (FRS) client.

Queries the EPA FRS public API for Oregon facilities and enriches Company
records with validated state presence data.

API docs: https://frs.epa.gov/frs-public-api/
No authentication required. Paginated with rows/start parameters.

SIC codes used to infer presence_type:
  2000-3999 (manufacturing) -> "manufacturing"
  5000-5999 (wholesale/distribution) -> "distribution"
  everything else -> "distribution" (conservative default)
"""
import asyncio
from typing import Any

import httpx
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

FRS_BASE_URL = "https://frs.epa.gov/frs-public-api"
PAGE_SIZE = 100

# SIC code ranges that indicate manufacturing
MANUFACTURING_SIC_RANGES = [(2000, 3999)]


def _infer_presence_type(sic_codes: list[str] | None) -> str:
    """Infer presence_type from SIC codes. Defaults to 'distribution'."""
    if not sic_codes:
        return "distribution"
    for sic in sic_codes:
        try:
            code = int(sic[:4]) if len(sic) >= 4 else int(sic)
            for lo, hi in MANUFACTURING_SIC_RANGES:
                if lo <= code <= hi:
                    return "manufacturing"
        except (ValueError, TypeError):
            continue
    return "distribution"


class EPAFRSClient:
    """Fetches Oregon facility records from EPA FRS and enriches Company data."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EPAFRSClient":
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": settings.sec_user_agent},
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Use EPAFRSClient as async context manager")
        return self._client

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def _get_page(self, state_code: str, start: int) -> dict:
        client = self._client_or_raise()
        resp = await client.get(
            f"{FRS_BASE_URL}/facility-search",
            params={
                "state_code": state_code,
                "rows": PAGE_SIZE,
                "start": start,
                "output": "JSON",
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def fetch_state_facilities(self, state_code: str = "OR") -> list[dict]:
        """Fetch all facilities in a state. Returns list of facility dicts."""
        facilities: list[dict] = []
        start = 0

        while True:
            try:
                data = await self._get_page(state_code, start)
            except Exception as exc:
                log.warning(
                    "epa_frs_page_error",
                    state=state_code,
                    start=start,
                    error=str(exc),
                )
                break

            # FRS API response structure varies; handle both list and nested formats
            results = data if isinstance(data, list) else data.get("results", data.get("facilities", []))
            if not results:
                break

            facilities.extend(results)
            log.debug("epa_frs_page_fetched", state=state_code, start=start, count=len(results))

            if len(results) < PAGE_SIZE:
                break
            start += PAGE_SIZE

        log.info("epa_frs_fetch_complete", state=state_code, total=len(facilities))
        return facilities


async def run_epa_frs_enrichment(db: Any) -> dict:
    """Main entry point: fetch Oregon FRS facilities and enrich Company records.

    Returns stats dict with keys: facilities_fetched, matched, unmatched, state_presences_added.
    """
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.company_intel.resolver import EntityResolver
    from app.models import Company, CompanyStatePresence

    if not settings.enable_epa_frs:
        log.info("epa_frs_skipped", reason="enable_epa_frs=false")
        return {"facilities_fetched": 0, "matched": 0, "unmatched": 0, "state_presences_added": 0}

    stats = {"facilities_fetched": 0, "matched": 0, "unmatched": 0, "state_presences_added": 0}
    resolver = EntityResolver(db)

    async with EPAFRSClient() as client:
        facilities = await client.fetch_state_facilities("OR")

    stats["facilities_fetched"] = len(facilities)

    for facility in facilities:
        # Extract fields — FRS uses various key names across API versions
        name: str = (
            facility.get("primaryName")
            or facility.get("facilityName")
            or facility.get("name")
            or ""
        ).strip()
        if not name:
            continue

        epa_id: str | None = (
            facility.get("registryId")
            or facility.get("facilityRegistryId")
            or facility.get("epaRegistryId")
        )
        if epa_id:
            epa_id = str(epa_id).strip()

        sic_codes: list[str] = facility.get("sicCodes", facility.get("sics", [])) or []

        company, confidence = await resolver.resolve(
            candidate_name=name,
            source="epa_frs",
            epa_id=epa_id,
        )

        if company is None:
            stats["unmatched"] += 1
            continue

        stats["matched"] += 1

        # Save EPA registry ID if the company doesn't have one yet
        if epa_id and not company.epa_registry_id:
            company.epa_registry_id = epa_id

        # Upsert state presence — only add if not already present with equal or stronger type
        presence_type = _infer_presence_type(sic_codes if isinstance(sic_codes, list) else [str(sic_codes)])

        existing_result = await db.execute(
            select(CompanyStatePresence).where(
                CompanyStatePresence.company_id == company.id,
                CompanyStatePresence.state == "OR",
            )
        )
        existing = existing_result.scalars().all()

        presence_strength = {
            "manufacturing": 4,
            "distribution": 3,
            "headquarters": 2,
            "retail": 1,
            "registered_agent": 0,
            "sales": 0,
        }
        new_strength = presence_strength.get(presence_type, 0)

        has_stronger = any(
            presence_strength.get(p.presence_type, 0) >= new_strength
            for p in existing
        )

        if not has_stronger:
            db.add(
                CompanyStatePresence(
                    company_id=company.id,
                    state="OR",
                    presence_type=presence_type,
                    is_primary=False,
                )
            )
            stats["state_presences_added"] += 1
            log.debug(
                "epa_frs_presence_added",
                company=company.name,
                presence_type=presence_type,
            )

    await db.flush()
    log.info("epa_frs_enrichment_complete", **stats)
    return stats
