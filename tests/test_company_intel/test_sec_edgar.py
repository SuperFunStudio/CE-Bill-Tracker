"""Unit tests for SEC EDGAR enrichment module.

Uses respx for HTTP mocks and AsyncMock for the database session.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response

from app.company_intel.sec_edgar import (
    SECEdgarClient,
    _normalize_cik,
    _parse_volume_from_text,
    run_sec_edgar_enrichment,
)
from app.models import Company, CompanyMaterial


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_company(name: str = "BigCo", cik: str | None = None) -> Company:
    c = Company()
    c.id = uuid.uuid4()
    c.name = name
    c.cik = cik
    c.duns_number = None
    c.epa_registry_id = None
    return c


def _make_material(company_id: uuid.UUID, category: str, volume: float | None = None, confidence: float = 0.5) -> CompanyMaterial:
    m = CompanyMaterial()
    m.id = uuid.uuid4()
    m.company_id = company_id
    m.material_category = category
    m.annual_volume_tonnes = volume
    m.volume_confidence = confidence
    m.source = "seed"
    return m


def _scalars_result(values: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


# ---------------------------------------------------------------------------
# Unit: _normalize_cik
# ---------------------------------------------------------------------------


def test_normalize_cik_pads_short():
    assert _normalize_cik("12345") == "0000012345"


def test_normalize_cik_preserves_full_length():
    assert _normalize_cik("0000051512") == "0000051512"


def test_normalize_cik_strips_spaces():
    assert _normalize_cik("  51512  ") == "0000051512"


# ---------------------------------------------------------------------------
# Unit: _parse_volume_from_text
# ---------------------------------------------------------------------------


def test_parse_volume_finds_metric_tonnes():
    text = "We shipped 45,000 metric tonnes of plastic packaging in FY2023."
    results = _parse_volume_from_text(text)
    assert len(results) >= 1
    assert results[0]["volume_tonnes"] == pytest.approx(45000.0)
    assert results[0]["material_category"] == "plastic_packaging"
    assert results[0]["confidence"] == pytest.approx(0.9)


def test_parse_volume_finds_thousands_multiplier():
    text = "Annual paper volume was 12 thousand tonnes of cardboard."
    results = _parse_volume_from_text(text)
    assert len(results) >= 1
    assert results[0]["volume_tonnes"] == pytest.approx(12000.0)


def test_parse_volume_returns_empty_on_no_match():
    text = "We focus on digital products and have no physical packaging."
    results = _parse_volume_from_text(text)
    assert results == []


def test_parse_volume_infers_aluminum_category():
    text = "We use 5,000 metric tonnes of aluminum cans annually."
    results = _parse_volume_from_text(text)
    assert any(r["material_category"] == "aluminum" for r in results)


# ---------------------------------------------------------------------------
# Unit: SECEdgarClient — get_latest_10k_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_latest_10k_url_returns_filing_url():
    cik = "0000051512"
    submissions_data = {
        "filings": {
            "recent": {
                "form": ["10-K", "8-K"],
                "accessionNumber": ["0000051512-24-000001", "0000051512-24-000002"],
                "primaryDocument": ["pg-20231231.htm", "8k.htm"],
            }
        }
    }
    respx.get(f"https://data.sec.gov/submissions/CIK{cik}.json").mock(
        return_value=Response(200, json=submissions_data)
    )

    async with SECEdgarClient() as client:
        url = await client.get_latest_10k_url("51512")

    assert url is not None
    assert "0000051512" in url
    assert "pg-20231231.htm" in url


@pytest.mark.asyncio
@respx.mock
async def test_get_latest_10k_url_returns_none_when_no_10k():
    cik = "0000099999"
    submissions_data = {
        "filings": {
            "recent": {
                "form": ["8-K", "8-K"],
                "accessionNumber": ["0000099999-24-000001", "0000099999-24-000002"],
                "primaryDocument": ["8k.htm", "8k2.htm"],
            }
        }
    }
    respx.get(f"https://data.sec.gov/submissions/CIK{cik}.json").mock(
        return_value=Response(200, json=submissions_data)
    )

    async with SECEdgarClient() as client:
        url = await client.get_latest_10k_url("99999")

    assert url is None


# ---------------------------------------------------------------------------
# Integration: run_sec_edgar_enrichment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrichment_updates_volume_on_higher_confidence():
    """When 10-K extraction returns higher confidence, volume is updated."""
    company = _make_company("Procter & Gamble Co", cik="0000051512")
    existing_mat = _make_material(company.id, "plastic_packaging", volume=50000.0, confidence=0.3)

    db = AsyncMock()
    db.execute.side_effect = [
        _scalars_result([company]),           # all companies query
        _scalars_result([existing_mat]),      # materials for company
    ]

    filing_text = "We shipped 95,000 metric tonnes of plastic packaging in FY2023."

    with (
        patch("app.company_intel.sec_edgar.settings") as mock_settings,
        patch("app.company_intel.sec_edgar.SECEdgarClient") as MockClient,
    ):
        mock_settings.enable_sec_edgar = True
        mock_settings.max_edgar_companies_per_run = 10
        mock_settings.sec_user_agent = "Test/1.0"

        mock_client_instance = AsyncMock()
        mock_client_instance.get_latest_10k_url.return_value = "https://www.sec.gov/Archives/edgar/test.htm"
        mock_client_instance.search_company_cik.return_value = None
        mock_client_instance.fetch_filing_text.return_value = filing_text
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        stats = await run_sec_edgar_enrichment(db)

    assert stats["companies_searched"] == 1
    assert stats["volumes_updated"] >= 1
    # Existing material volume should have been updated
    assert existing_mat.annual_volume_tonnes == pytest.approx(95000.0)
    assert existing_mat.volume_confidence == pytest.approx(0.9)
    assert existing_mat.source == "sec_edgar_10k"


@pytest.mark.asyncio
async def test_enrichment_does_not_downgrade_confidence():
    """10-K extraction with lower confidence does not overwrite higher existing confidence."""
    company = _make_company("BigPackaging Corp", cik="0000012345")
    # Existing material already has high confidence (from previous EDGAR run)
    existing_mat = _make_material(company.id, "plastic_packaging", volume=80000.0, confidence=0.9)

    db = AsyncMock()
    db.execute.side_effect = [
        _scalars_result([company]),
        _scalars_result([existing_mat]),
    ]

    # Ambiguous text produces lower confidence (0.6)
    filing_text = "Total tons of packaging across our portfolio was 40,000 tonnes."

    with (
        patch("app.company_intel.sec_edgar.settings") as mock_settings,
        patch("app.company_intel.sec_edgar.SECEdgarClient") as MockClient,
    ):
        mock_settings.enable_sec_edgar = True
        mock_settings.max_edgar_companies_per_run = 10
        mock_settings.sec_user_agent = "Test/1.0"

        mock_client_instance = AsyncMock()
        mock_client_instance.get_latest_10k_url.return_value = "https://www.sec.gov/Archives/edgar/test.htm"
        mock_client_instance.search_company_cik.return_value = None
        mock_client_instance.fetch_filing_text.return_value = filing_text
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        stats = await run_sec_edgar_enrichment(db)

    # Volume should NOT have been downgraded
    assert existing_mat.volume_confidence == pytest.approx(0.9)
    assert existing_mat.annual_volume_tonnes == pytest.approx(80000.0)
    assert stats["volumes_updated"] == 0


@pytest.mark.asyncio
async def test_enrichment_skipped_when_flag_false():
    db = AsyncMock()

    with patch("app.company_intel.sec_edgar.settings") as mock_settings:
        mock_settings.enable_sec_edgar = False

        stats = await run_sec_edgar_enrichment(db)

    assert stats["companies_searched"] == 0
    db.execute.assert_not_called()
