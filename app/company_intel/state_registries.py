"""CAA Oregon Producer Registry scraper.

Scrapes the Circular Action Alliance (CAA) Oregon producer registry to identify
confirmed obligated parties under Oregon's packaging EPR program.

Source: https://circularactionalliance.org/registration
Falls back to a hardcoded seed list if the live page is unavailable or changes
structure. Scrape failures are logged and do not crash the refresh cycle.

Every matched producer receives a CompanyAlias with verified=True and source="caa_oregon",
marking it as a confirmed obligated party. Unmatched producers go to entity_match_queue
and MUST be manually resolved before the Oregon demo.
"""
import re
from typing import Any

import httpx
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

CAA_REGISTRY_URL = "https://circularactionalliance.org/registration"

# Fallback list: manually curated CAA Oregon registered producers.
# Update this list after manually checking the CAA site before the demo.
FALLBACK_PRODUCERS: list[dict] = [
    {"name": "Procter & Gamble", "materials": ["plastic_packaging", "paper"]},
    {"name": "Unilever United States", "materials": ["plastic_packaging"]},
    {"name": "Nestle USA", "materials": ["plastic_packaging", "aluminum"]},
    {"name": "PepsiCo", "materials": ["plastic_packaging", "aluminum", "glass"]},
    {"name": "The Coca-Cola Company", "materials": ["plastic_packaging", "aluminum", "glass"]},
    {"name": "Kraft Heinz", "materials": ["plastic_packaging", "glass", "paper"]},
    {"name": "General Mills", "materials": ["plastic_packaging", "paper"]},
    {"name": "Kellogg Company", "materials": ["plastic_packaging", "paper"]},
    {"name": "Campbell Soup Company", "materials": ["aluminum", "glass", "plastic_packaging"]},
    {"name": "Colgate-Palmolive", "materials": ["plastic_packaging", "paper"]},
]


def _parse_producer_table(html: str) -> list[dict]:
    """Parse producer names from CAA registry HTML.

    Attempts to find an HTML table or list of registered producers.
    Returns list of dicts with at least a 'name' key.
    """
    producers: list[dict] = []

    # Try to find a data table (most likely format)
    table_pattern = re.compile(
        r"<tr[^>]*>.*?<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL
    )
    rows = table_pattern.findall(html)
    for row in rows:
        # Strip HTML tags from cell content
        name = re.sub(r"<[^>]+>", "", row).strip()
        if name and len(name) > 2 and not name.lower().startswith(("company", "name", "producer")):
            producers.append({"name": name, "materials": []})

    if producers:
        return producers

    # Fallback: look for list items that look like company names
    li_pattern = re.compile(r"<li[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
    items = li_pattern.findall(html)
    for item in items:
        name = re.sub(r"<[^>]+>", "", item).strip()
        if name and 3 < len(name) < 200:
            producers.append({"name": name, "materials": []})

    return producers


class CAARegistryScraper:
    """Fetches and parses the CAA Oregon producer registry."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "CAARegistryScraper":
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    @retry_with_backoff(max_attempts=2, base_delay=3.0)
    async def _fetch_html(self) -> str:
        client = self._client
        if client is None:
            raise RuntimeError("Use CAARegistryScraper as async context manager")
        resp = await client.get(CAA_REGISTRY_URL)
        resp.raise_for_status()
        return resp.text

    async def fetch_producers(self) -> tuple[list[dict], bool]:
        """Fetch producers from live CAA registry.

        Returns (producers, is_live) where is_live=False means fallback was used.
        """
        try:
            html = await self._fetch_html()
            producers = _parse_producer_table(html)
            if producers:
                log.info("caa_registry_live_fetch", count=len(producers))
                return producers, True
            else:
                log.warning(
                    "caa_registry_parse_empty",
                    reason="No producers parsed from live page; using fallback",
                )
                return FALLBACK_PRODUCERS, False
        except Exception as exc:
            log.warning(
                "caa_registry_fetch_failed",
                error=str(exc),
                reason="Using fallback producer list",
            )
            return FALLBACK_PRODUCERS, False


async def run_caa_registry_enrichment(db: Any) -> dict:
    """Main entry point: scrape CAA Oregon registry and enrich Company records.

    Returns stats dict with keys: producers_fetched, matched, unmatched, new_aliases, used_fallback.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.company_intel.resolver import EntityResolver
    from app.models import CompanyAlias, CompanyStatePresence

    if not settings.enable_caa_registry:
        log.info("caa_registry_skipped", reason="enable_caa_registry=false")
        return {
            "producers_fetched": 0,
            "matched": 0,
            "unmatched": 0,
            "new_aliases": 0,
            "used_fallback": False,
        }

    stats = {
        "producers_fetched": 0,
        "matched": 0,
        "unmatched": 0,
        "new_aliases": 0,
        "used_fallback": False,
    }
    resolver = EntityResolver(db)
    now = datetime.now(timezone.utc)

    async with CAARegistryScraper() as scraper:
        producers, is_live = await scraper.fetch_producers()

    stats["producers_fetched"] = len(producers)
    stats["used_fallback"] = not is_live

    for producer in producers:
        name: str = producer.get("name", "").strip()
        if not name:
            continue

        company, confidence = await resolver.resolve(
            candidate_name=name,
            source="caa_oregon",
        )

        if company is None:
            stats["unmatched"] += 1
            log.info(
                "caa_registry_unmatched",
                producer=name,
                note="Queued for manual review — confirmed obligated party",
            )
            continue

        stats["matched"] += 1

        # Add or refresh the CAA verified alias
        existing_alias_result = await db.execute(
            select(CompanyAlias).where(
                CompanyAlias.company_id == company.id,
                CompanyAlias.source == "caa_oregon",
            )
        )
        existing_alias = existing_alias_result.scalar_one_or_none()

        if existing_alias is None:
            db.add(
                CompanyAlias(
                    company_id=company.id,
                    alias_name=name,
                    source="caa_oregon",
                    match_confidence=confidence,
                    verified=True,
                    verified_by="caa_registry_scraper",
                    verified_at=now,
                )
            )
            stats["new_aliases"] += 1
            log.debug("caa_registry_alias_added", company=company.name, alias=name)
        elif not existing_alias.verified:
            existing_alias.verified = True
            existing_alias.verified_by = "caa_registry_scraper"
            existing_alias.verified_at = now

        # Add registered_agent presence in OR if no stronger presence exists
        existing_presences_result = await db.execute(
            select(CompanyStatePresence).where(
                CompanyStatePresence.company_id == company.id,
                CompanyStatePresence.state == "OR",
            )
        )
        existing_presences = existing_presences_result.scalars().all()

        stronger_types = {"manufacturing", "distribution", "headquarters", "retail"}
        has_stronger = any(p.presence_type in stronger_types for p in existing_presences)

        if not existing_presences:
            db.add(
                CompanyStatePresence(
                    company_id=company.id,
                    state="OR",
                    presence_type="registered_agent",
                    is_primary=False,
                )
            )
            log.debug("caa_registry_presence_added", company=company.name)
        elif not has_stronger:
            # Already has registered_agent or sales — no action needed
            pass

    await db.flush()
    log.info("caa_registry_enrichment_complete", **stats)
    return stats
