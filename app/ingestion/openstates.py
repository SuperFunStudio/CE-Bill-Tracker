import html
import re
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
        params: dict = {
            "q": query,
            "page": page,
            "per_page": per_page,
            "include": ["sources", "abstracts"],
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

        if chosen_media == "application/pdf":
            log.info("openstates_text_unavailable_pdf", bill_id=bill_id, url=chosen_url)
            return ""

        # Fetch the document from the state legislature / OpenStates-hosted URL.
        # No API key header — these are public document links, not the v3 API.
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as doc_client:
                resp = await doc_client.get(chosen_url)
                resp.raise_for_status()
                text = resp.text
        except Exception as e:
            log.warning("openstates_text_fetch_failed",
                        bill_id=bill_id, url=chosen_url, error=str(e))
            return ""

        if chosen_media == "text/html" or "<html" in text[:2000].lower():
            text = html.unescape(_TAG_RE.sub(" ", text))
            text = re.sub(r"\s+", " ", text).strip()
        return text
