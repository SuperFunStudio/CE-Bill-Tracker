"""Unit tests for CAA Oregon registry scraper.

Uses respx to mock HTTP calls and AsyncMock for the database session.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response

from app.company_intel.state_registries import (
    FALLBACK_PRODUCERS,
    CAARegistryScraper,
    _parse_producer_table,
    run_caa_registry_enrichment,
)
from app.models import Company, CompanyAlias, CompanyStatePresence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_company(name: str = "Test Corp") -> Company:
    c = Company()
    c.id = uuid.uuid4()
    c.name = name
    c.cik = None
    c.duns_number = None
    c.epa_registry_id = None
    return c


def _scalar_result(value) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_result(values: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


# ---------------------------------------------------------------------------
# Unit: _parse_producer_table
# ---------------------------------------------------------------------------


def test_parse_producer_table_finds_table_rows():
    html = """
    <table>
      <tr><th>Company Name</th><th>Status</th></tr>
      <tr><td>Acme Corp</td><td>Active</td></tr>
      <tr><td>Greenfield Inc</td><td>Active</td></tr>
    </table>
    """
    results = _parse_producer_table(html)
    names = [r["name"] for r in results]
    assert "Acme Corp" in names
    assert "Greenfield Inc" in names


def test_parse_producer_table_skips_header_rows():
    html = "<tr><td>Company Name</td></tr><tr><td>Actual Producer LLC</td></tr>"
    results = _parse_producer_table(html)
    names = [r["name"] for r in results]
    assert "Actual Producer LLC" in names
    assert "Company Name" not in names


def test_parse_producer_table_empty_html_returns_empty():
    results = _parse_producer_table("<html><body><p>No data.</p></body></html>")
    assert results == []


# ---------------------------------------------------------------------------
# Unit: CAARegistryScraper — fallback on error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_fetch_producers_falls_back_on_http_error():
    """HTTP 503 causes graceful fallback to FALLBACK_PRODUCERS."""
    respx.get("https://circularactionalliance.org/registration").mock(
        return_value=Response(503)
    )

    async with CAARegistryScraper() as scraper:
        producers, is_live = await scraper.fetch_producers()

    assert not is_live
    assert producers == FALLBACK_PRODUCERS


@pytest.mark.asyncio
@respx.mock
async def test_fetch_producers_returns_live_on_success():
    """Parseable HTML returns live producers."""
    html = "<table><tr><td>Name</td></tr><tr><td>Oregon Canners</td></tr></table>"
    respx.get("https://circularactionalliance.org/registration").mock(
        return_value=Response(200, text=html)
    )

    async with CAARegistryScraper() as scraper:
        producers, is_live = await scraper.fetch_producers()

    assert is_live
    assert any(p["name"] == "Oregon Canners" for p in producers)


# ---------------------------------------------------------------------------
# Integration: run_caa_registry_enrichment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrichment_adds_alias_on_match():
    """Matched producer receives a verified CAA alias."""
    company = _make_company("Procter & Gamble")

    db = AsyncMock()
    alias_mock = MagicMock()
    alias_mock.company = company
    alias_mock.match_confidence = 0.97
    db.execute.side_effect = [
        _scalar_result(alias_mock),      # resolver alias lookup
        _scalar_result(None),             # existing caa_oregon alias lookup (none)
        _scalars_result([]),              # existing OR presences (none)
    ]

    producers = [{"name": "Procter & Gamble", "materials": ["plastic_packaging"]}]

    with (
        patch("app.company_intel.state_registries.settings") as mock_settings,
        patch("app.company_intel.state_registries.CAARegistryScraper") as MockScraper,
    ):
        mock_settings.enable_caa_registry = True
        mock_settings.sec_user_agent = "Test/1.0"

        mock_scraper_instance = AsyncMock()
        mock_scraper_instance.fetch_producers.return_value = (producers, True)
        MockScraper.return_value.__aenter__ = AsyncMock(return_value=mock_scraper_instance)
        MockScraper.return_value.__aexit__ = AsyncMock(return_value=False)

        stats = await run_caa_registry_enrichment(db)

    assert stats["matched"] == 1
    assert stats["new_aliases"] == 1
    assert stats["unmatched"] == 0

    db.add.assert_called()
    # Find the alias add call (first add should be the alias)
    alias_add = db.add.call_args_list[0][0][0]
    assert isinstance(alias_add, CompanyAlias)
    assert alias_add.verified is True
    assert alias_add.source == "caa_oregon"


@pytest.mark.asyncio
async def test_enrichment_adds_registered_agent_presence_when_no_or_presence():
    """Matched company with no OR presence gets registered_agent presence."""
    company = _make_company("NestlePurina")

    db = AsyncMock()
    alias_mock = MagicMock()
    alias_mock.company = company
    alias_mock.match_confidence = 0.9
    db.execute.side_effect = [
        _scalar_result(alias_mock),
        _scalar_result(None),    # no existing caa alias
        _scalars_result([]),     # no existing OR presences
    ]

    producers = [{"name": "NestlePurina", "materials": []}]

    with (
        patch("app.company_intel.state_registries.settings") as mock_settings,
        patch("app.company_intel.state_registries.CAARegistryScraper") as MockScraper,
    ):
        mock_settings.enable_caa_registry = True
        mock_settings.sec_user_agent = "Test/1.0"

        mock_instance = AsyncMock()
        mock_instance.fetch_producers.return_value = (producers, True)
        MockScraper.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockScraper.return_value.__aexit__ = AsyncMock(return_value=False)

        stats = await run_caa_registry_enrichment(db)

    # db.add called twice: once for alias, once for presence
    assert db.add.call_count == 2
    added_objects = [call[0][0] for call in db.add.call_args_list]
    presence = next((o for o in added_objects if isinstance(o, CompanyStatePresence)), None)
    assert presence is not None
    assert presence.presence_type == "registered_agent"
    assert presence.state == "OR"


@pytest.mark.asyncio
async def test_enrichment_skipped_when_flag_false():
    db = AsyncMock()

    with patch("app.company_intel.state_registries.settings") as mock_settings:
        mock_settings.enable_caa_registry = False

        stats = await run_caa_registry_enrichment(db)

    assert stats["producers_fetched"] == 0
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_enrichment_queues_unmatched_producers():
    """Producers that don't match any company go to entity_match_queue."""
    db = AsyncMock()
    # Resolver step 2 (alias): no match; step 3 (fuzzy): no match -> queued
    no_alias = _scalar_result(None)
    no_trgm = MagicMock()
    no_trgm.first.return_value = None

    db.execute.side_effect = [no_alias, no_trgm]
    db.flush = AsyncMock()

    producers = [{"name": "Unknown Oregon Bottler LLC", "materials": []}]

    with (
        patch("app.company_intel.state_registries.settings") as mock_settings,
        patch("app.company_intel.state_registries.CAARegistryScraper") as MockScraper,
    ):
        mock_settings.enable_caa_registry = True
        mock_settings.sec_user_agent = "Test/1.0"

        mock_instance = AsyncMock()
        mock_instance.fetch_producers.return_value = (producers, True)
        MockScraper.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockScraper.return_value.__aexit__ = AsyncMock(return_value=False)

        stats = await run_caa_registry_enrichment(db)

    assert stats["unmatched"] == 1
    assert stats["matched"] == 0
