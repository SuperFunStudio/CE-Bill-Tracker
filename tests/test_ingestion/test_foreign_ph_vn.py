"""Philippines / Vietnam FAOLEX seed adapters: registration, seed shape and the Vietnamese anchors."""
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
            assert s["id"].isdigit() and not s["id"].startswith("0")  # FAOLEX PDF names drop the leading 0
            assert s["en"]
    assert FAOLEX_DOC.format(prefix="phi", id="228024").endswith("/phi228024.pdf")
    assert FAOLEX_DOC.format(prefix="vie", id="212268").endswith("/vie212268.pdf")


def test_vietnamese_decree_windows_on_its_epr_chapter():
    preamble = "Nghị định quy định chi tiết một số điều của Luật Bảo vệ môi trường. " * 2000
    epr = "Điều 77. Tỷ lệ tái chế bắt buộc và quy cách tái chế bắt buộc"
    window = select_text_window(preamble + epr + " nội dung " * 100, region="VN", max_chars=20000)
    assert "Tỷ lệ tái chế bắt buộc" in window
