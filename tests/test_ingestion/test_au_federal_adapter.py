"""The Australian federal adapter must ride out the Register of Legislation API's slow spells
(retry timeouts/5xx), follow OData paging, and log what actually went wrong."""
import httpx
import pytest

from app.ingestion import foreign
from app.ingestion.foreign import AustraliaFederalClient


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        pass

    monkeypatch.setattr(foreign.asyncio, "sleep", instant)


def _row(i, collection="Act", in_force=True):
    return {"id": f"C2020A{i:05d}", "name": f"Act {i}", "collection": collection,
            "isInForce": in_force}


async def _discover(handler, terms=("Product Stewardship",), monkeypatch=None):
    monkeypatch.setattr(foreign, "AU_FED_TERMS", list(terms))
    client = AustraliaFederalClient()
    async with client:
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return await client.discover()


async def test_timeouts_are_retried_then_succeed(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise httpx.ReadTimeout("", request=request)
        return httpx.Response(200, json={"value": [_row(1)]})

    found = await _discover(handler, monkeypatch=monkeypatch)
    assert [sid for sid, _ in found] == ["C2020A00001"]
    assert len(calls) == 3


async def test_5xx_is_retried_but_4xx_is_not(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 400)

    found = await _discover(handler, monkeypatch=monkeypatch)
    assert found == [] and len(calls) == 2


async def test_one_stuck_term_does_not_lose_the_others(monkeypatch):
    def handler(request):
        if "Packaging" in str(request.url):
            raise httpx.ConnectTimeout("", request=request)
        return httpx.Response(200, json={"value": [_row(7)]})

    found = await _discover(handler, terms=("Packaging", "Product Stewardship"),
                            monkeypatch=monkeypatch)
    assert [sid for sid, _ in found] == ["C2020A00007"]


async def test_follows_odata_next_links_and_keeps_the_filters(monkeypatch):
    next_url = "https://api.prod.legislation.gov.au/v1/titles?$skiptoken=abc"

    def handler(request):
        if "skiptoken" in str(request.url):
            return httpx.Response(200, json={"value": [_row(2), _row(3, collection="Gazette"),
                                                       _row(4, in_force=False)]})
        return httpx.Response(200, json={"value": [_row(1)], "@odata.nextLink": next_url})

    found = await _discover(handler, monkeypatch=monkeypatch)
    assert [sid for sid, _ in found] == ["C2020A00001", "C2020A00002"]


def test_timeout_errors_are_described():
    request = httpx.Request("GET", "https://example.org")
    assert foreign._describe_error(httpx.ReadTimeout("", request=request)) == "ReadTimeout"
    assert foreign._describe_error(ValueError("bad json")) == "ValueError: bad json"
