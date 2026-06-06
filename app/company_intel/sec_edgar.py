"""SEC EDGAR 10-K volume extraction.

Enriches Company records with packaging volume data sourced from annual 10-K filings.
For public companies with a known CIK, fetches the latest 10-K directly.
For companies without a CIK, searches EDGAR full-text for the company name + EPR keywords.

Volume confidence levels written to CompanyMaterial.volume_confidence:
  0.9  — figure extracted via EDGAR, parsed by deterministic regex
  0.6  — figure extracted by regex from ambiguous text (units inferred)
  0.3  — figure inferred by Claude Haiku from ambiguous passage (gated by flag)

SEC fair-use: 10 req/sec max. This module enforces 0.12s between requests.
EDGAR requires a User-Agent header identifying the application.

References:
  - https://data.sec.gov/submissions/CIK{cik}.json  (company filing index)
  - https://efts.sec.gov/LATEST/search-index         (full-text search)
  - https://www.sec.gov/Archives/edgar/full-index/   (filing index archives)
"""
import asyncio
import re
from typing import Any

import httpx
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FILING_BASE = "https://www.sec.gov/Archives/edgar/"

# EPR-related keywords used in EDGAR full-text search
EPR_SEARCH_TERMS = [
    "extended producer responsibility",
    "packaging EPR",
    "SB 582",
    "producer responsibility organization",
]

# Regex patterns for volume extraction from 10-K text
# Matches patterns like: "1,200 metric tons", "45,000 tonnes", "120 thousand metric tons"
VOLUME_PATTERNS = [
    # "X thousand metric tons of plastic packaging"
    re.compile(
        r"(\d[\d,]*\.?\d*)\s*(?:thousand|million)?\s*(?:metric\s+)?(?:tons?|tonnes?)"
        r"(?:\s+of\s+(?:plastic|aluminum|aluminium|glass|paper|cardboard|packaging))?",
        re.IGNORECASE,
    ),
    # "plastic packaging volume of X tonnes"
    re.compile(
        r"(?:plastic|aluminum|aluminium|glass|paper|cardboard|packaging)\s+"
        r"(?:packaging\s+)?(?:volume|weight|mass)\s+of\s+(\d[\d,]*\.?\d*)\s*"
        r"(?:thousand\s+)?(?:metric\s+)?(?:tons?|tonnes?)",
        re.IGNORECASE,
    ),
]

# Material category keywords to infer which material a volume figure relates to
MATERIAL_KEYWORDS = {
    "plastic_packaging": ["plastic", "polymer", "resin", "PET", "HDPE", "polypropylene"],
    "aluminum": ["aluminum", "aluminium", "can", "foil"],
    "glass": ["glass"],
    "paper": ["paper", "cardboard", "paperboard", "corrugated", "fiber"],
    "other_packaging": ["packaging", "package", "container"],
}

REQUESTS_PER_SECOND = 8  # Below SEC 10/s limit
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND


def _normalize_cik(cik: str) -> str:
    """Pad CIK to 10 digits as required by EDGAR."""
    return str(cik).strip().zfill(10)


def _parse_volume_from_text(text: str) -> list[dict]:
    """Extract volume mentions from 10-K text.

    Returns list of dicts: {material_category, volume_tonnes, confidence, raw_text}.
    """
    extractions: list[dict] = []

    for pattern in VOLUME_PATTERNS:
        for match in pattern.finditer(text):
            raw_num = match.group(1).replace(",", "")
            try:
                volume = float(raw_num)
            except ValueError:
                continue

            # Check for "thousand" or "million" multipliers near the match
            surrounding = text[max(0, match.start() - 20): match.end() + 20].lower()
            if "million" in surrounding:
                volume *= 1_000_000
            elif "thousand" in surrounding:
                volume *= 1_000

            # Infer material category from surrounding context
            context = text[max(0, match.start() - 100): match.end() + 100].lower()
            matched_material = "other_packaging"
            for category, keywords in MATERIAL_KEYWORDS.items():
                if any(kw.lower() in context for kw in keywords):
                    matched_material = category
                    break

            # Confidence: 0.9 if units clearly stated, 0.6 if inferred
            confidence = 0.9 if re.search(r"metric\s+ton|tonne", match.group(0), re.IGNORECASE) else 0.6

            extractions.append({
                "material_category": matched_material,
                "volume_tonnes": volume,
                "confidence": confidence,
                "raw_text": match.group(0),
            })

    return extractions


class SECEdgarClient:
    """Fetches 10-K filings from SEC EDGAR and extracts volume data."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "SECEdgarClient":
        self._client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Use SECEdgarClient as async context manager")
        return self._client

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def _get_json(self, url: str, params: dict | None = None) -> dict:
        await asyncio.sleep(REQUEST_DELAY)
        client = self._client_or_raise()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    @retry_with_backoff(max_attempts=2, base_delay=2.0)
    async def _get_text(self, url: str) -> str:
        await asyncio.sleep(REQUEST_DELAY)
        client = self._client_or_raise()
        resp = await client.get(url, headers={"Accept": "text/plain,text/html,*/*"})
        resp.raise_for_status()
        return resp.text

    async def get_latest_10k_url(self, cik: str) -> str | None:
        """Find the URL of the most recent 10-K filing for a given CIK."""
        cik_padded = _normalize_cik(cik)
        try:
            data = await self._get_json(EDGAR_SUBMISSIONS_URL.format(cik=cik_padded))
        except Exception as exc:
            log.warning("edgar_submissions_error", cik=cik, error=str(exc))
            return None

        filings = data.get("filings", {}).get("recent", {})
        form_types = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])

        for i, form_type in enumerate(form_types):
            if form_type in ("10-K", "10-K/A"):
                accession = accession_numbers[i].replace("-", "")
                doc = primary_docs[i] if i < len(primary_docs) else ""
                if doc:
                    return f"{EDGAR_FILING_BASE}{cik_padded}/{accession}/{doc}"
                # Fall back to index
                return f"{EDGAR_FILING_BASE}{cik_padded}/{accession}/{accession_numbers[i]}-index.htm"

        return None

    async def search_company_cik(self, company_name: str) -> str | None:
        """Search EDGAR full-text for a company name + EPR keywords. Returns CIK if unique match."""
        query = f'"{company_name}" "extended producer responsibility"'
        try:
            data = await self._get_json(
                EDGAR_SEARCH_URL,
                params={
                    "q": query,
                    "dateRange": "custom",
                    "startdt": "2022-01-01",
                    "forms": "10-K",
                    "_source": "period_of_report,entity_name,file_num,period_of_report",
                },
            )
        except Exception as exc:
            log.warning("edgar_search_error", company=company_name, error=str(exc))
            return None

        hits = data.get("hits", {}).get("hits", [])
        if len(hits) == 1:
            cik = hits[0].get("_source", {}).get("file_num", "").replace("0001", "")
            entity_cik = hits[0].get("_id", "").split(":")[0] if hits else None
            return entity_cik
        return None

    async def fetch_filing_text(self, filing_url: str, max_chars: int = 200_000) -> str:
        """Fetch 10-K filing text. Truncates to max_chars to limit memory use."""
        try:
            text = await self._get_text(filing_url)
            # Strip HTML tags for cleaner regex matching
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            return text[:max_chars]
        except Exception as exc:
            log.warning("edgar_filing_fetch_error", url=filing_url, error=str(exc))
            return ""


async def run_sec_edgar_enrichment(db: Any) -> dict:
    """Main entry point: enrich Company records with 10-K volume data.

    Processes up to max_edgar_companies_per_run companies per run.
    Returns stats: {companies_searched, ciks_found, volumes_updated, errors}.
    """
    from sqlalchemy import select, update

    from app.models import Company, CompanyMaterial

    if not settings.enable_sec_edgar:
        log.info("sec_edgar_skipped", reason="enable_sec_edgar=false")
        return {"companies_searched": 0, "ciks_found": 0, "volumes_updated": 0, "errors": 0}

    stats = {"companies_searched": 0, "ciks_found": 0, "volumes_updated": 0, "errors": 0}

    # Load companies — prioritise those with CIK already set (direct lookup),
    # then try companies without CIK up to the per-run limit
    companies_result = await db.execute(select(Company))
    all_companies = companies_result.scalars().all()

    with_cik = [c for c in all_companies if c.cik]
    without_cik = [c for c in all_companies if not c.cik]

    cap = settings.max_edgar_companies_per_run
    to_process = (with_cik + without_cik)[:cap]

    async with SECEdgarClient() as client:
        for company in to_process:
            stats["companies_searched"] += 1
            cik = company.cik

            # Try to find CIK if not set
            if not cik:
                cik = await client.search_company_cik(company.name)
                if cik:
                    company.cik = cik
                    stats["ciks_found"] += 1
                    log.info("edgar_cik_found", company=company.name, cik=cik)

            if not cik:
                continue

            # Fetch latest 10-K
            filing_url = await client.get_latest_10k_url(cik)
            if not filing_url:
                continue

            filing_text = await client.fetch_filing_text(filing_url)
            if not filing_text:
                continue

            extractions = _parse_volume_from_text(filing_text)
            if not extractions:
                continue

            # Load existing materials for this company
            mats_result = await db.execute(
                select(CompanyMaterial).where(CompanyMaterial.company_id == company.id)
            )
            existing_materials = {m.material_category: m for m in mats_result.scalars().all()}

            for extraction in extractions:
                cat = extraction["material_category"]
                vol = extraction["volume_tonnes"]
                conf = extraction["confidence"]

                if cat in existing_materials:
                    mat = existing_materials[cat]
                    # Only update if new confidence is higher than existing
                    existing_conf = mat.volume_confidence or 0.0
                    if conf > existing_conf:
                        mat.annual_volume_tonnes = vol
                        mat.volume_confidence = conf
                        mat.source = "sec_edgar_10k"
                        stats["volumes_updated"] += 1
                        log.info(
                            "edgar_volume_updated",
                            company=company.name,
                            material=cat,
                            volume=vol,
                            confidence=conf,
                        )
                else:
                    # Add new material record found in 10-K
                    db.add(
                        CompanyMaterial(
                            company_id=company.id,
                            material_category=cat,
                            annual_volume_tonnes=vol,
                            volume_confidence=conf,
                            source="sec_edgar_10k",
                        )
                    )
                    stats["volumes_updated"] += 1
                    log.info(
                        "edgar_material_added",
                        company=company.name,
                        material=cat,
                        volume=vol,
                    )

    await db.flush()
    log.info("sec_edgar_enrichment_complete", **stats)
    return stats
