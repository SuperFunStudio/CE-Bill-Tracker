"""EU TRIS draft-notification adapter: country routing, the session-cookie search, message parsing
(title by position, contact block dropped), and the cold lookup of a reference by search."""
import datetime

import httpx
import pytest

from app.ingestion.foreign import FOREIGN_CLIENTS, TRIS_SECTORS, EuTrisClient, _tris_region

RESULTS = """<table id="tris-notif-results"><tbody>
<tr><td><a href="/en/notification/29361"> 2026/0550/PL</a></td><td>Parliamentary draft Act</td></tr>
<tr><td><a href="/en/notification/29000"> 2026/0400/IS</a></td><td>Icelandic draft</td></tr>
<tr><td><a href="/en/notification/28000"> 2026/0300/XI</a></td><td>NI draft</td></tr>
</tbody></table>"""

DETAIL = """<html><header>site chrome</header><main>
<h1>2026/0550/PL</h1>
<div>Date received:</div><div>09/10/2026</div><div>End of Standstill:</div><div>12/01/2027</div>
<p>Communication from the Commission - TRIS/(2026) 2847</p>
<p>1. MSG 001 IND 2026 0550 PL EN 09-10-2026 PL NOTIF</p><p>2. Poland</p>
<p>3A. Ministerstwo Rozwoju, tel.: (+48) 22 411 93 94</p>
<p>3B. poseł Jan Kowalski, jan.kowalski@sejm.pl; 691 945 730</p>
<p>4. 2026/0550/PL - S10E - Packaging</p>
<p>5th Parliamentary draft Act amending the Act on packaging and packaging waste management</p>
<p>8. The draft abolishes the deposit-return system for beverage packaging.</p>
<p>16. </p><p>TBT aspects: No</p><p>**********</p><p>European Commission contact point</p>
</main><footer>footer</footer></html>"""


def _client(calls):
    def handler(req: httpx.Request):
        calls.append(req)
        if req.method == "GET" and req.url.path == "/en/search":
            return httpx.Response(200, html="<form></form>", headers={"set-cookie": "SESS=1; Path=/"})
        if req.method == "POST":
            if "SESS=1" not in req.headers.get("cookie", "") or "Referer" not in req.headers:
                return httpx.Response(403, html="<title>Sorry - 1</title>")
            return httpx.Response(200, html=RESULTS)
        if req.url.path == "/en/notification/29361":
            return httpx.Response(200, html=DETAIL)
        return httpx.Response(404)

    client = EuTrisClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def test_registered_and_routed_to_the_notifying_country():
    assert FOREIGN_CLIENTS["EU_TRIS"] is EuTrisClient
    assert _tris_region("2026/0550/PL") == "PL"
    assert _tris_region("2026/0300/XI") == "UK"    # Northern Ireland notifies as XI
    assert _tris_region("2026/0400/IS") is None    # not in the jurisdiction tree
    assert EuTrisClient().foreign_id_for("2026/0550/PL") == "PL:tris:2026/0550/PL"


@pytest.mark.asyncio
async def test_discovery_uses_the_search_session_and_skips_unknown_countries():
    calls = []
    refs = [r for r, _ in await _client(calls).discover()]
    assert refs == ["2026/0550/PL", "2026/0300/XI"]
    posts = [c for c in calls if c.method == "POST"]
    assert posts, "discovery must POST the search form"
    body = posts[0].content.decode()
    assert all(f"sel_product%5B%5D={s}" in body for s in TRIS_SECTORS)
    assert sum(c.method == "GET" for c in calls) == 1  # one cookie fetch, reused for every year


@pytest.mark.asyncio
async def test_fetch_builds_a_pending_draft_without_the_contact_block():
    calls = []
    client = _client(calls)
    await client.discover()
    law = await client.fetch("2026/0550/PL")
    assert law.foreign_id == "PL:tris:2026/0550/PL" and law.region == "PL"
    assert law.status == "introduced"
    assert law.title == "Parliamentary draft Act amending the Act on packaging and packaging waste management"
    assert law.status_date == law.last_action_date == datetime.date(2026, 10, 9)
    assert "End of standstill: 2027-01-12" in law.full_text
    assert "abolishes the deposit-return system" in law.full_text
    assert "sejm.pl" not in law.full_text and "411 93 94" not in law.full_text
    assert "site chrome" not in law.full_text and "contact point" not in law.full_text
    assert law.source_url.endswith("/en/notification/29361")


@pytest.mark.asyncio
async def test_cold_fetch_resolves_the_reference_by_search():
    calls = []
    law = await _client(calls).fetch("2026/0550/PL")  # no discovery first
    assert law is not None and law.region == "PL"
    lookup = next(c for c in calls if c.method == "POST").content.decode()
    assert "year=2026" in lookup and "number=550" in lookup and "country%5B%5D=PL" in lookup


@pytest.mark.asyncio
async def test_unknown_country_or_unresolvable_reference_is_skipped():
    calls = []
    client = _client(calls)
    assert await client.fetch("2026/0400/IS") is None
    assert await client.fetch("2026/9999/DE") is None   # search returns no row for it
