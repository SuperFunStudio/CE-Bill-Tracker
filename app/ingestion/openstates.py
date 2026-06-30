import html
import io
import re
import urllib.parse
from datetime import datetime

import httpx
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

BASE_URL = "https://v3.openstates.org"

# Preference order for which bill-version document to feed the Sonnet extractor.
_TEXT_MEDIA_PREFERENCE = ("text/plain", "text/html", "application/pdf")
_TAG_RE = re.compile(r"<[^>]+>")
# Strip these blocks content-and-all before tag-stripping, so a landing-page scrape doesn't leave
# inline JS/CSS text (e.g. gtag('config', …)) baked into the "bill text" we hand to the Sonnet
# extractor / store for full-text search. Plain tag-stripping alone removes <script> but keeps the code.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|head)\b[^>]*>.*?</\1>", re.I | re.S)


# Some state legislature sites reject the default httpx User-Agent or serve
# incomplete TLS chains; a browser UA plus an SSL-verification fallback recovers them.
_DOC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _canonical_doc_url(url: str) -> str:
    """Rewrite known JavaScript-shell document URLs to a server-rendered text endpoint.

    California's leginfo links (billNavClient / billPdf) return a JS app shell with no
    bill text, so extraction got nothing for every CA bill. billTextClient.xhtml serves
    the full text inline in the page for the same bill_id, so rewrite to that.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return url
    if parsed.netloc.endswith("leginfo.legislature.ca.gov"):
        bill_id = urllib.parse.parse_qs(parsed.query).get("bill_id", [None])[0]
        if bill_id:
            return ("https://leginfo.legislature.ca.gov/faces/"
                    f"billTextClient.xhtml?bill_id={bill_id}")
    return url


async def _fetch_document(url: str) -> "httpx.Response | None":
    """GET a public legislative document. Returns None on failure.

    Retries once with TLS verification disabled — many state sites serve public
    bill PDFs over a misconfigured/incomplete certificate chain. These are public
    documents with no credentials attached, so the fallback is acceptable.
    """
    for verify in (True, False):
        try:
            async with httpx.AsyncClient(
                timeout=30.0, follow_redirects=True, headers=_DOC_HEADERS, verify=verify
            ) as doc_client:
                resp = await doc_client.get(url)
                resp.raise_for_status()
                return resp
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            # Likely a TLS/connection issue — retry without verification.
            if verify:
                log.info("openstates_doc_ssl_retry", url=url, error=str(e))
                continue
            log.warning("openstates_doc_fetch_error", url=url, error=str(e))
            return None
        except Exception as e:
            log.warning("openstates_doc_fetch_error", url=url, error=str(e))
            return None
    return None


async def _document_text(url: str, media_hint: str = "") -> str:
    """Fetch a legislative document URL and return its extracted plain text ('' on failure).

    Shared by get_bill_text (API-discovered version link) and get_text_from_source (the
    source_url we already hold from the bulk dump). Detects PDF by magic bytes and strips
    HTML markup so the Sonnet extractor receives clean text either way.
    """
    if not url:
        return ""
    url = _canonical_doc_url(url)
    resp = await _fetch_document(url)
    if resp is None:
        log.warning("openstates_text_fetch_failed", url=url)
        return ""
    content = resp.content
    # Detect PDF by magic bytes, not the declared media type — some states label an
    # XHTML viewer page as application/pdf (and vice versa).
    if content[:5] == b"%PDF-":
        text = _extract_pdf_text(content)
        if not text:
            log.info("openstates_pdf_extract_empty", url=url)
        return text
    text = resp.text
    if media_hint in ("text/html", "application/pdf") or "<" in text[:2000]:
        text = _SCRIPT_STYLE_RE.sub(" ", text)
        text = html.unescape(_TAG_RE.sub(" ", text))
        text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_pdf_text(data: bytes) -> str:
    """Extract plain text from a PDF byte string. Returns '' on any failure.

    Many state legislatures expose bill text only as PDF, so without this the Sonnet
    compliance extractor gets empty text and produces no deadlines. pypdf is pure-python
    and handles the text-layer PDFs these sites serve; scanned/image PDFs yield ''.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = [page.extract_text() or "" for page in reader.pages]
    except Exception:
        return ""
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


class OpenStatesClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.open_states_api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"X-API-KEY": self.api_key},
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def search_bills(
        self,
        query: str,
        jurisdiction: str | None = None,
        updated_since: datetime | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        if self._client is None:
            raise RuntimeError("Use as async context manager")
        # `sources` + `abstracts` are NOT returned by the search endpoint unless requested.
        # _upsert_openstates_bill reads sources[0].url for source_url and abstracts[0] for
        # description, so without these includes every ingested row gets a NULL source link.
        # `actions` carries each action's normalized classification (executive-signature / became-law),
        # which _infer_openstates_status uses to detect enactment reliably — the free-text
        # latest_action_description misses signatures phrased differently per state (e.g. CO).
        params: dict = {
            "q": query,
            "page": page,
            "per_page": per_page,
            "include": ["sources", "abstracts", "actions"],
        }
        if jurisdiction:
            params["jurisdiction"] = jurisdiction
        if updated_since:
            params["updated_since"] = updated_since.date().isoformat()
        resp = await self._client.get("/bills", params=params)
        resp.raise_for_status()
        return resp.json()

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def get_bill(self, bill_id: str, include: list[str] | None = None) -> dict:
        if self._client is None:
            raise RuntimeError("Use as async context manager")
        params = {"include": include} if include else None
        resp = await self._client.get(f"/bills/{bill_id}", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_bill_text(self, bill_id: str) -> str:
        """Fetch the latest version's document text for an OpenStates bill.

        Replaces the LegiScan full-text path (dormant). OpenStates v3 bills expose a
        `versions` array; each version has `links` of `{url, media_type}`. We pick the
        most recent version and prefer text/plain, then text/html, then PDF. PDF-only
        bills are skipped in this version (no PDF extractor dependency installed) and
        return "". Any failure returns "" — Stage 3 tolerates empty text.
        """
        try:
            bill = await self.get_bill(bill_id, include=["versions"])
        except Exception as e:
            log.warning("openstates_get_versions_failed", bill_id=bill_id, error=str(e))
            return ""

        versions = bill.get("versions") or []
        if not versions:
            return ""

        # Most recent version: sort by date when present, else take the last entry.
        latest = max(versions, key=lambda v: v.get("date") or "") if any(
            v.get("date") for v in versions
        ) else versions[-1]

        links = latest.get("links") or []
        link_by_media = {}
        for link in links:
            media = (link.get("media_type") or "").lower()
            if media and media not in link_by_media:
                link_by_media[media] = link.get("url")

        chosen_url = None
        chosen_media = None
        for media in _TEXT_MEDIA_PREFERENCE:
            if media in link_by_media:
                chosen_url, chosen_media = link_by_media[media], media
                break
        # Fall back to the first available link if none matched the preference list.
        if chosen_url is None and links:
            chosen_url = links[0].get("url")
            chosen_media = (links[0].get("media_type") or "").lower()

        if not chosen_url:
            return ""

        # Fetch the document from the state legislature / OpenStates-hosted URL.
        return await _document_text(chosen_url, chosen_media or "")

    async def get_text_from_source(self, source_url: str) -> str:
        """Extract bill text straight from a state-legislature source URL.

        Uses the source_url we already hold from the bulk dump, so it skips the
        rate-limited OpenStates versions API entirely (the document fetch goes to the
        state site, not v3.openstates.org). Returns '' on failure.
        """
        return await _document_text(source_url)
