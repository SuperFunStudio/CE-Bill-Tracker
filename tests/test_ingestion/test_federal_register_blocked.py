"""When the Federal Register API refuses us (403/429), the run must stop at once rather than retry
every term — prod was sending 75 refused requests per blocked run — and say so in its stats."""
import httpx
import pytest

from app.ingestion import federal_register as fr_mod
from app.ingestion.federal_register import USER_AGENT, FederalRegisterClient


def _client_with(handler):
    client = FederalRegisterClient()
    client._client = httpx.AsyncClient(
        base_url=fr_mod.BASE_URL, transport=httpx.MockTransport(handler),
        headers={"User-Agent": USER_AGENT},
    )
    return client


def _page(n):
    return {"results": [{"document_number": f"2026-{i:05d}"} for i in range(n)]}


@pytest.mark.parametrize("status", [403, 429])
async def test_blocked_response_ends_the_run_without_retries(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="Request blocked.",
                              headers={"x-request-id": "Root1-abc"})

    client = _client_with(handler)
    docs = await client.search_all_epr_terms()
    assert docs == []
    assert len(calls) == 1
    assert client.last_search_stats == {
        "terms_searched": 1, "terms_failed": 1,
        "terms_total": len(fr_mod.EPR_SEARCH_TERMS), "blocked_status": status,
    }


async def test_block_partway_keeps_what_was_already_fetched():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) <= 2:
            return httpx.Response(200, json=_page(3))
        return httpx.Response(403, text="blocked")

    client = _client_with(handler)
    docs = await client.search_all_epr_terms()
    # Both pages answered with the same three doc numbers, so they dedupe to three.
    assert len(docs) == 3
    assert len(calls) == 3
    assert client.last_search_stats["terms_searched"] == 3
    assert client.last_search_stats["blocked_status"] == 403


async def test_healthy_run_reports_every_term_and_identifies_itself():
    agents = set()

    def handler(request):
        agents.add(request.headers["user-agent"])
        return httpx.Response(200, json=_page(0))

    client = _client_with(handler)
    await client.search_all_epr_terms()
    assert agents == {USER_AGENT}
    stats = client.last_search_stats
    assert stats["terms_searched"] == stats["terms_total"] and stats["terms_failed"] == 0
    assert stats["blocked_status"] is None


async def test_real_client_sends_the_user_agent():
    async with FederalRegisterClient() as client:
        assert client._client.headers["user-agent"] == USER_AGENT
