"""Philippines / Vietnam FAOLEX seed adapters: registration, seed shape, HTML seeds, Vietnamese anchors."""
import httpx
import pytest

from app.classification.sonnet_extractor import select_text_window
from app.ingestion.foreign import (
    FOREIGN_CLIENTS, FAOLEX_DOC, PhilippinesFaolexClient, VietnamFaolexClient,
)


def test_registered_under_their_region_codes():
    assert FOREIGN_CLIENTS["PH"] is PhilippinesFaolexClient
    assert FOREIGN_CLIENTS["VN"] is VietnamFaolexClient


def test_seeds_resolve_to_faolex_pdfs():
    for client in (PhilippinesFaolexClient, VietnamFaolexClient):
        ids = [s["id"] for s in client.seeds]
        assert len(ids) == len(set(ids))
        for s in client.seeds:
            assert s["en"]
            if "url" not in s:  # FAOLEX PDF names drop the leading 0 of the record id
                assert s["id"].isdigit() and not s["id"].startswith("0")
            if s.get("html"):
                assert s["start"] and s["end"]
    assert FAOLEX_DOC.format(prefix="phi", id="228024").endswith("/phi228024.pdf")
    assert FAOLEX_DOC.format(prefix="vie", id="212268").endswith("/vie212268.pdf")


def _html_client(body: str) -> VietnamFaolexClient:
    client = VietnamFaolexClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, html=body)))
    return client


@pytest.mark.asyncio
async def test_html_seed_is_sliced_between_its_markers():
    body = ("<html><nav>HOME Contact us</nav><div>THE GOVERNMENT OF VIETNAM No. 110/2026/ND-CP "
            + "Article 1. Scope. " * 30 + "(This translation is for reference only)</div>"
            "<footer>Jane Doe Purchased new equipments</footer></html>")
    law = await _html_client(body).fetch("nd-110-2026", "Decree 110/2026")
    assert law.full_text.startswith("THE GOVERNMENT OF VIETNAM")
    assert "Jane Doe" not in law.full_text and "Contact us" not in law.full_text
    assert law.source_url.startswith("https://asemconnectvietnam.gov.vn/")


@pytest.mark.asyncio
async def test_html_seed_without_its_markers_is_skipped():
    assert await _html_client("<html>maintenance page</html>").fetch("nd-110-2026") is None


def test_vietnamese_decree_windows_on_its_epr_chapter():
    preamble = "Nghị định quy định chi tiết một số điều của Luật Bảo vệ môi trường. " * 2000
    epr = "Điều 77. Tỷ lệ tái chế bắt buộc và quy cách tái chế bắt buộc"
    window = select_text_window(preamble + epr + " nội dung " * 100, region="VN", max_chars=20000)
    assert "Tỷ lệ tái chế bắt buộc" in window
