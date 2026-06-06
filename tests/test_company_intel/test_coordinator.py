"""Unit tests for CompanyIntelCoordinator.

Verifies that all three enrichment sources are called in order and
their stats are combined correctly. Each source is mocked independently.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.company_intel.coordinator import CompanyIntelCoordinator


@pytest.mark.asyncio
async def test_refresh_all_calls_all_three_sources():
    """All three enrichment functions are called exactly once per refresh."""
    db = AsyncMock()

    epa_stats = {"facilities_fetched": 10, "matched": 7, "unmatched": 3, "state_presences_added": 7}
    caa_stats = {"producers_fetched": 5, "matched": 4, "unmatched": 1, "new_aliases": 4, "used_fallback": False}
    edgar_stats = {"companies_searched": 20, "ciks_found": 3, "volumes_updated": 8, "errors": 0}

    with (
        patch("app.company_intel.coordinator.run_epa_frs_enrichment", new=AsyncMock(return_value=epa_stats)) as mock_epa,
        patch("app.company_intel.coordinator.run_caa_registry_enrichment", new=AsyncMock(return_value=caa_stats)) as mock_caa,
        patch("app.company_intel.coordinator.run_sec_edgar_enrichment", new=AsyncMock(return_value=edgar_stats)) as mock_edgar,
    ):
        coordinator = CompanyIntelCoordinator()
        result = await coordinator.refresh_all(db)

    mock_epa.assert_called_once_with(db)
    mock_caa.assert_called_once_with(db)
    mock_edgar.assert_called_once_with(db)

    assert result["epa_frs"] == epa_stats
    assert result["caa_registry"] == caa_stats
    assert result["sec_edgar"] == edgar_stats


@pytest.mark.asyncio
async def test_refresh_all_combines_summary_stats():
    """Top-level summary stats are correctly aggregated."""
    db = AsyncMock()

    epa_stats = {"facilities_fetched": 5, "matched": 3, "unmatched": 2, "state_presences_added": 3}
    caa_stats = {"producers_fetched": 10, "matched": 8, "unmatched": 2, "new_aliases": 8, "used_fallback": False}
    edgar_stats = {"companies_searched": 15, "ciks_found": 2, "volumes_updated": 6, "errors": 1}

    with (
        patch("app.company_intel.coordinator.run_epa_frs_enrichment", new=AsyncMock(return_value=epa_stats)),
        patch("app.company_intel.coordinator.run_caa_registry_enrichment", new=AsyncMock(return_value=caa_stats)),
        patch("app.company_intel.coordinator.run_sec_edgar_enrichment", new=AsyncMock(return_value=edgar_stats)),
    ):
        coordinator = CompanyIntelCoordinator()
        result = await coordinator.refresh_all(db)

    assert result["total_state_presences_added"] == 3
    assert result["total_caa_matched"] == 8
    assert result["total_caa_unmatched"] == 2
    assert result["total_volumes_updated"] == 6


@pytest.mark.asyncio
async def test_refresh_all_continues_on_source_error():
    """If one source raises an exception, the others still run."""
    db = AsyncMock()

    caa_stats = {"producers_fetched": 5, "matched": 5, "unmatched": 0, "new_aliases": 5, "used_fallback": False}
    edgar_stats = {"companies_searched": 10, "ciks_found": 1, "volumes_updated": 4, "errors": 0}

    with (
        patch("app.company_intel.coordinator.run_epa_frs_enrichment", new=AsyncMock(side_effect=RuntimeError("FRS API down"))),
        patch("app.company_intel.coordinator.run_caa_registry_enrichment", new=AsyncMock(return_value=caa_stats)),
        patch("app.company_intel.coordinator.run_sec_edgar_enrichment", new=AsyncMock(return_value=edgar_stats)),
    ):
        coordinator = CompanyIntelCoordinator()
        result = await coordinator.refresh_all(db)

    # EPA FRS error stored in result, but others ran
    assert "error" in result["epa_frs"]
    assert result["caa_registry"] == caa_stats
    assert result["sec_edgar"] == edgar_stats
    # Summary stats still reflect successful sources
    assert result["total_caa_matched"] == 5
    assert result["total_volumes_updated"] == 4


@pytest.mark.asyncio
async def test_refresh_all_edgar_runs_last():
    """SEC EDGAR is called after EPA FRS and CAA to ensure entity resolution is settled."""
    call_order: list[str] = []

    async def fake_epa(db):
        call_order.append("epa")
        return {"facilities_fetched": 0, "matched": 0, "unmatched": 0, "state_presences_added": 0}

    async def fake_caa(db):
        call_order.append("caa")
        return {"producers_fetched": 0, "matched": 0, "unmatched": 0, "new_aliases": 0, "used_fallback": False}

    async def fake_edgar(db):
        call_order.append("edgar")
        return {"companies_searched": 0, "ciks_found": 0, "volumes_updated": 0, "errors": 0}

    db = AsyncMock()

    with (
        patch("app.company_intel.coordinator.run_epa_frs_enrichment", new=fake_epa),
        patch("app.company_intel.coordinator.run_caa_registry_enrichment", new=fake_caa),
        patch("app.company_intel.coordinator.run_sec_edgar_enrichment", new=fake_edgar),
    ):
        coordinator = CompanyIntelCoordinator()
        await coordinator.refresh_all(db)

    assert call_order == ["epa", "caa", "edgar"]
