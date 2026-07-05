"""NYS Open Legislation API client (https://legislation.nysenate.gov/api/3).

The authoritative source for New York bill data — our NY rows' `source_url` already points at
this API's bill endpoint, but every request needs an api key (`key=` query param), so without one
the source_url rung of the bill-text ladder always fails for NY. This client is slotted in as the
FIRST rung for NY bills in app/ingestion/bill_text.fetch_clean_text: it returns clean plain text
(fullTextFormat=PLAIN) with no HTML scraping or PDF extraction needed, and its rate limits are far
friendlier than the OpenStates free tier.

Key setup: sign up at https://legislation.nysenate.gov/ and CONFIRM the activation email — until
confirmed the API rejects the key with errorCode 701 ("A valid API key is needed"). Empty
settings.nys_api_key disables the client (is_enabled → False); the ladder then behaves exactly as
before.

Bill addressing: `{sessionYear}/{printNo}` — sessionYear is the ODD start year of NY's two-year
session (2025 covers 2025-2026), printNo is the unpunctuated bill number ("A8391", not "A-8391").
`session_year_for` derives the session from the bill's source_url (which embeds "2025-2026") and
falls back to the newest action date, odd-ized.
"""
from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

BASE_URL = "https://legislation.nysenate.gov/api/3"

# NY source_urls come in two shapes: the OpenLeg API/site path ("…/bills/2025-2026/A8391") and the
# Assembly's query-string form ("nyassembly.gov/leg/?bn=A07166&term=2025"). Both embed the session.
_SESSION_IN_URL_RE = re.compile(
    r"nysenate\.gov/(?:api/3/bills|legislation/bills)/(\d{4})"
    r"|nyassembly\.gov/leg/\?[^\s]*\bterm=(\d{4})"
)


def session_year_for(b) -> int | None:
    """Derive the NY session start year (odd) for a bill row.

    Prefers the year embedded in source_url (both the OpenLeg "…/bills/2025-2026/…" and the
    Assembly "…?bn=…&term=2025" shapes — already the session start, since those sites minted the
    URLs); falls back to the bill's most recent action/status date rounded down to the odd year.
    None if neither is available.
    """
    m = _SESSION_IN_URL_RE.search(getattr(b, "source_url", None) or "")
    if m:
        y = int(m.group(1) or m.group(2))
        return y if y % 2 == 1 else y - 1
    for attr in ("last_action_date", "status_date"):
        d = getattr(b, attr, None)
        if d is not None:
            return d.year if d.year % 2 == 1 else d.year - 1
    return None


class NYSenateClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.nys_api_key
        self._client: httpx.AsyncClient | None = None

    @property
    def is_enabled(self) -> bool:
        return bool(self.api_key)

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Use NYSenateClient as async context manager")
        return self._client

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def _get(self, path: str, **params) -> dict:
        client = self._client_or_raise()
        resp = await client.get(f"{BASE_URL}{path}", params={"key": self.api_key, **params})
        # 404 = bill not found for that session/printNo — a normal miss, not an error to retry.
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", False):
            raise ValueError(
                f"NYS OpenLeg error for {path}: "
                f"{data.get('errorCode')} {data.get('message', '')}".strip()
            )
        return data

    async def get_bill(self, session_year: int, print_no: str, *, full_text: bool = False) -> dict:
        """Detailed bill view (result object), {} if not found.

        With full_text=True the amendments carry plain-text fullText (fullTextFormat=PLAIN);
        without it we request the lighter no-fulltext view.
        """
        params: dict[str, Any] = (
            {"fullTextFormat": "PLAIN"} if full_text else {"view": "with_refs_no_fulltext"}
        )
        data = await self._get(f"/bills/{session_year}/{print_no}", **params)
        return data.get("result") or {}

    async def get_bill_text(self, session_year: int, print_no: str) -> str:
        """Plain full text of the bill's active amendment ("" if unavailable).

        Falls back through the other amendment versions (newest first) if the active one has no
        text yet — freshly-amended bills can briefly carry text only on an older version.
        """
        bill = await self.get_bill(session_year, print_no, full_text=True)
        items = (bill.get("amendments") or {}).get("items") or {}
        if not items:
            return ""
        active = bill.get("activeVersion")
        versions = sorted(items, reverse=True)  # "" < "A" < "B" → newest first
        if active in items:
            versions.remove(active)
            versions.insert(0, active)
        for v in versions:
            txt = (items[v] or {}).get("fullText") or ""
            if isinstance(txt, str) and txt.strip():
                return txt
        return ""

    async def search(self, term: str, session_year: int | None = None, limit: int = 25) -> list[dict]:
        """Bill search (Lucene syntax supported). Returns the raw result items."""
        params: dict[str, Any] = {"term": term, "limit": limit}
        path = f"/bills/{session_year}/search" if session_year else "/bills/search"
        data = await self._get(path, **params)
        return ((data.get("result") or {}).get("items")) or []
