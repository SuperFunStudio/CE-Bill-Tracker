"""DORMANT module — do not enable without a paid LegiScan key.

The LegiScan free tier's getMasterList returns West Virginia session-1 bill data
for EVERY state queried, so this ingestion path produces garbage. All LegiScan-sourced
rows were purged in alembic migration 004 and ingestion is gated off via
settings.enable_legiscan_ingestion (default False). OpenStates v3 is the live source.
Kept intact (not deleted) so a paid key can revive it later.
"""
import base64
import hashlib
from typing import Any

import httpx
import structlog

from app.config import settings
from app.utils.retry import retry_with_backoff

log = structlog.get_logger()

BASE_URL = "https://api.legiscan.com/"

# EPR-priority ordering: demo-critical + most active EPR states first.
# Already-ingested states (AL–IN) placed last — re-fetching them costs
# only 2 API calls each (getSessionList + getMasterList), since their
# bills are hashed and will all report "unchanged".
ALL_STATES = [
    # Tier 1 — demo target + highest EPR legislative activity
    "OR",                                    # Oregon NAW trial — highest priority
    "WA", "NY", "ME", "CO", "CT",           # most active EPR states
    "MA", "MD", "NJ", "VT", "RI", "MN",    # strong EPR pipeline
    "NV", "UT", "NC", "PA", "IL", "MI",    # growing EPR interest
    # Tier 2 — remaining uninspected states
    "IA", "KS", "KY", "LA", "MS", "MO", "MT", "NE", "NH",
    "NM", "ND", "OH", "OK", "SC", "SD", "TN", "TX",
    "VA", "WV", "WI", "WY", "DC",
    # Tier 3 — already ingested (cheap re-check; placed last)
    "AK", "AR", "AL", "AZ", "DE", "FL", "GA", "HI", "ID",
    "CA", "IN",
]


class LegiScanClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.legiscan_api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Use LegiScanClient as async context manager")
        return self._client

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def _get(self, op: str, **params) -> dict:
        client = self._client_or_raise()
        resp = await client.get(
            BASE_URL,
            params={"key": self.api_key, "op": op, **params},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "ERROR":
            raise ValueError(f"LegiScan error for op={op}: {data.get('alert', {})}")
        return data

    async def get_session_list(self, state: str) -> list[dict]:
        data = await self._get("getSessionList", state=state)
        sessions = data.get("sessions", {})
        # LegiScan returns dict keyed by session_id
        if isinstance(sessions, dict):
            return list(sessions.values())
        return sessions

    async def get_master_list(self, state: str, session_id: int | None = None) -> dict[str, dict]:
        """Returns dict of str(bill_id) → bill summary with change_hash."""
        params = {"state": state}
        if session_id:
            params["id"] = session_id
        data = await self._get("getMasterList", **params)
        master = data.get("masterlist", {})
        # Remove the 'session' metadata key
        master.pop("session", None)
        return master

    async def get_bill(self, bill_id: int) -> dict:
        data = await self._get("getBill", id=bill_id)
        return data.get("bill", {})

    async def get_bill_text(self, doc_id: int) -> str:
        """Fetch bill text document; returns decoded text string."""
        data = await self._get("getBillText", id=doc_id)
        doc = data.get("text", {})
        encoded = doc.get("doc", "")
        if not encoded:
            return ""
        try:
            decoded = base64.b64decode(encoded)
            # Try UTF-8, fall back to latin-1
            try:
                return decoded.decode("utf-8")
            except UnicodeDecodeError:
                return decoded.decode("latin-1", errors="replace")
        except Exception as e:
            log.warning("bill_text_decode_failed", doc_id=doc_id, error=str(e))
            return ""

    async def search(
        self, query: str, state: str | None = None, page: int = 1, year: int | None = None
    ) -> list[dict]:
        params: dict[str, Any] = {"query": query, "page": page}
        if state:
            params["state"] = state
        if year:
            # LegiScan getSearch 'year': 1=all, 2=current, or a specific 4-digit year.
            params["year"] = year
        data = await self._get("getSearch", **params)
        results = data.get("searchresult", {})
        # Remove summary key
        results.pop("summary", None)
        return list(results.values())


def compute_bill_hash(bill_data: dict) -> str:
    """Compute a stable hash from the mutable fields we care about."""
    key = f"{bill_data.get('status', '')}-{bill_data.get('last_action_date', '')}-{bill_data.get('change_hash', '')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
