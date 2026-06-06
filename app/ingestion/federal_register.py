from datetime import date

import httpx
import structlog

from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

BASE_URL = "https://www.federalregister.gov/api/v1"

# Search terms for EPR-adjacent federal actions
EPR_SEARCH_TERMS = [
    "extended producer responsibility",
    "packaging waste producer",
    "product stewardship federal",
    "battery recycling federal",
    "electronics stewardship",
    "PFAS packaging restriction",
    "deposit return scheme",
    "dormant commerce clause packaging",
]


class FederalRegisterClient:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def search_documents(
        self,
        terms: list[str],
        per_page: int = 20,
        page: int = 1,
        published_since: date | None = None,
    ) -> dict:
        if self._client is None:
            raise RuntimeError("Use as async context manager")
        params: dict = {
            "fields[]": [
                "document_number", "title", "agencies", "type",
                "publication_date", "comments_close_on", "effective_on",
                "html_url", "abstract",
            ],
            "per_page": per_page,
            "page": page,
            "order": "newest",
        }
        # Build conditions: any term match
        for i, term in enumerate(terms):
            params[f"conditions[term]"] = term  # FR API supports single term per request
            break  # Use first term; loop callers should call per-term
        if published_since:
            params["conditions[publication_date][gte]"] = published_since.isoformat()

        resp = await self._client.get("/documents.json", params=params)
        resp.raise_for_status()
        return resp.json()

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def get_document(self, document_number: str) -> dict:
        if self._client is None:
            raise RuntimeError("Use as async context manager")
        resp = await self._client.get(f"/documents/{document_number}.json")
        resp.raise_for_status()
        return resp.json()

    async def search_all_epr_terms(
        self, published_since: date | None = None
    ) -> list[dict]:
        """Search all EPR terms and deduplicate by document_number."""
        seen: set[str] = set()
        results: list[dict] = []
        for term in EPR_SEARCH_TERMS:
            try:
                data = await self.search_documents([term], published_since=published_since)
                for doc in data.get("results", []):
                    doc_num = doc.get("document_number", "")
                    if doc_num and doc_num not in seen:
                        seen.add(doc_num)
                        results.append(doc)
            except Exception as e:
                log.warning("federal_register_search_failed", term=term, error=str(e))
        return results
