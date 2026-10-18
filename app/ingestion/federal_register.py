from datetime import date

import httpx
import structlog

from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

BASE_URL = "https://www.federalregister.gov/api/v1"

# Identify ourselves. The API sits behind an AWS firewall that intermittently 403s prod's Cloud Run
# egress (shared Google IPs) while answering the same request from elsewhere; an anonymous default
# client UA is the easiest thing for such a rule to throttle.
USER_AGENT = "AtlasCircular/1.0 (+https://www.atlascircular.com; hello@atlascircular.com)"

# Statuses that mean "you are being refused", not "this request failed". Retrying them only adds to
# the request count a rate-based block is keyed on, so they end the run instead (see
# search_all_epr_terms). The next scheduled run catches up: each run re-reads the newest pages.
_BLOCKED_STATUSES = (403, 429)


class FederalRegisterBlocked(Exception):
    """The API refused us (403/429). Not retried; ends the current run."""

    def __init__(self, status: int, body: str, request_id: str | None):
        super().__init__(f"Federal Register refused the request ({status})")
        self.status = status
        self.body = body
        self.request_id = request_id


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code in _BLOCKED_STATUSES:
        raise FederalRegisterBlocked(resp.status_code, resp.text[:300],
                                     resp.headers.get("x-request-id"))
    resp.raise_for_status()

# Search terms for EPR-adjacent federal actions.
#
# IMPORTANT: these are searched as QUOTED phrases (see search_documents). The Federal Register
# `term` param is a full-text search that, UNQUOTED, ORs the individual words — so
# "extended producer responsibility" matched any doc containing "producer" or "responsibility"
# and flooded the feed with ~1000 antidumping/trade notices. Quoting cuts that ~1000x.
#
# The list was calibrated empirically against the live FR API + classifier yield: terms that
# returned only noise or zero hits at the federal level were dropped, and the biological-cycle
# terms (biobased / regen-ag / organics — see haiku_classifier material axis) were added. Even
# quoted, these over-retrieve via passing mentions; FederalClassifier is the precision layer.
EPR_SEARCH_TERMS = [
    "extended producer responsibility",
    "product stewardship",
    "circular economy",
    "national recycling strategy",
    "recycling infrastructure",
    "recycled content",
    "plastic pollution",
    "single-use plastic",
    "right to repair",
    "battery recycling",
    "electronic waste",
    "e-waste",
    "compostable",
    "sustainable materials management",
    "container deposit",
    "drug take-back",
    "biobased product",
    "regenerative agriculture",
    "soil health",
    "compostable packaging",
    "photovoltaic module",
    # Waste-shipment / secondary-materials trade (mirrors the bill classifier's "waste_shipment"
    # instrument). Export controls and allocation orders on scrap, black mass, and other recovered
    # feedstock are circular-economy actions that the EPR vocabulary above misses. Deliberately
    # tight phrases: "critical minerals" (180 hits since 2021) and "transboundary" (150) were tested
    # and dropped as mining/air-pollution noise; these four total ~90 docs over the same window.
    "black mass",
    "waste and scrap",
    "scrap metal",
    "secondary materials",
]


class FederalRegisterClient:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        # Set by search_all_epr_terms: terms searched / failed and whether the API blocked us.
        self.last_search_stats: dict = {}

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=BASE_URL, timeout=30.0, headers={"User-Agent": USER_AGENT}
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def search_documents(
        self,
        term: str,
        per_page: int = 50,
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
            # QUOTE the term so the FR full-text search matches the phrase, not each word OR'd.
            # This is the single most important precision fix for the feed.
            "conditions[term]": f'"{term}"',
            "per_page": per_page,
            "page": page,
            "order": "newest",
        }
        if published_since:
            params["conditions[publication_date][gte]"] = published_since.isoformat()

        resp = await self._client.get("/documents.json", params=params)
        _raise_for_status(resp)
        return resp.json()

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def get_document(self, document_number: str) -> dict:
        if self._client is None:
            raise RuntimeError("Use as async context manager")
        resp = await self._client.get(f"/documents/{document_number}.json")
        _raise_for_status(resp)
        return resp.json()

    async def search_all_epr_terms(
        self, published_since: date | None = None, max_pages: int = 2, per_page: int = 50
    ) -> list[dict]:
        """Search all EPR terms (as quoted phrases) and deduplicate by document_number.

        Paginates up to max_pages per term so a high-volume term (e.g. "circular economy")
        isn't truncated. For a historical backfill pass published_since further back."""
        seen: set[str] = set()
        results: list[dict] = []
        searched = failed = 0
        blocked_status: int | None = None
        for term in EPR_SEARCH_TERMS:
            searched += 1
            try:
                for page in range(1, max_pages + 1):
                    data = await self.search_documents(
                        term, per_page=per_page, page=page, published_since=published_since
                    )
                    page_results = data.get("results", [])
                    for doc in page_results:
                        doc_num = doc.get("document_number", "")
                        if doc_num and doc_num not in seen:
                            seen.add(doc_num)
                            results.append(doc)
                    if len(page_results) < per_page:
                        break  # last page for this term
            except FederalRegisterBlocked as e:
                failed += 1
                blocked_status = e.status
                log.error("federal_register_blocked", term=term, status=e.status,
                          request_id=e.request_id, body=e.body,
                          terms_skipped=len(EPR_SEARCH_TERMS) - searched)
                break
            except Exception as e:
                failed += 1
                log.warning("federal_register_search_failed", term=term, error=str(e))
        self.last_search_stats = {
            "terms_searched": searched,
            "terms_failed": failed,
            "terms_total": len(EPR_SEARCH_TERMS),
            "blocked_status": blocked_status,
        }
        return results
