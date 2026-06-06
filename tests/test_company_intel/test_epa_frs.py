"""Unit tests for EPA FRS enrichment module.

Uses respx to mock HTTP calls and AsyncMock for the database session.
No real network or database required.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response

from app.company_intel.epa_frs import (
    EPAFRSClient,
    _infer_presence_type,
    run_epa_frs_enrichment,
)
from app.models import Company, CompanyStatePresence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_company(name: str = "Test Corp", epa_id: str | None = None) -> Company:
    c = Company()
    c.id = uuid.uuid4()
    c.name = name
    c.epa_registry_id = epa_id
    c.cik = None
    c.duns_number = None
    return c


def _scalar_result(value) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalars.return_value.all.return_value = [value] if value else []
    return r


def _scalars_result(values: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


# ---------------------------------------------------------------------------
# Unit: _infer_presence_type
# ---------------------------------------------------------------------------


def test_infer_presence_type_manufacturing():
    assert _infer_presence_type(["2650"]) == "manufacturing"


def test_infer_presence_type_non_manufacturing():
    assert _infer_presence_type(["5900"]) == "distribution"


def test_infer_presence_type_none():
    assert _infer_presence_type(None) == "distribution"


def test_infer_presence_type_empty():
    assert _infer_presence_type([]) == "distribution"


def test_infer_presence_type_mixed_prefers_manufacturing():
    # If any SIC is manufacturing, return manufacturing
    assert _infer_presence_type(["5900", "2650"]) == "manufacturing"


# ---------------------------------------------------------------------------
# Unit: EPAFRSClient pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_fetch_state_facilities_single_page():
    """A single-page response returns all facilities without looping."""
    facilities = [
        {"primaryName": "Acme Plastics OR", "registryId": "REG001", "sicCodes": ["2650"]},
        {"primaryName": "Portland Paper Co", "registryId": "REG002", "sicCodes": ["2600"]},
    ]
    respx.get("https://frs.epa.gov/frs-public-api/facility-search").mock(
        return_value=Response(200, json=facilities)
    )

    async with EPAFRSClient() as client:
        result = await client.fetch_state_facilities("OR")

    assert len(result) == 2
    assert result[0]["primaryName"] == "Acme Plastics OR"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_state_facilities_api_error_returns_empty():
    """HTTP error on first page returns empty list (no crash)."""
    respx.get("https://frs.epa.gov/frs-public-api/facility-search").mock(
        return_value=Response(500)
    )

    async with EPAFRSClient() as client:
        result = await client.fetch_state_facilities("OR")

    assert result == []


# ---------------------------------------------------------------------------
# Integration: run_epa_frs_enrichment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrichment_adds_state_presence_on_match():
    """Matched facility adds a CompanyStatePresence record."""
    company = _make_company("Acme Plastics")

    db = AsyncMock()
    # scalar_one_or_none for alias lookup -> company found
    alias_mock = MagicMock()
    alias_mock.company = company
    alias_mock.match_confidence = 0.95
    # execute calls: alias lookup, company lookup (resolver step 2), presences lookup
    db.execute.side_effect = [
        _scalar_result(alias_mock),  # alias match in resolver
        _scalars_result([]),          # no existing OR presences
    ]

    facilities = [
        {"primaryName": "Acme Plastics", "registryId": "REG001", "sicCodes": ["2650"]}
    ]

    with (
        patch("app.company_intel.epa_frs.settings") as mock_settings,
        patch("app.company_intel.epa_frs.EPAFRSClient") as MockClient,
    ):
        mock_settings.enable_epa_frs = True
        mock_settings.sec_user_agent = "Test/1.0"

        mock_client_instance = AsyncMock()
        mock_client_instance.fetch_state_facilities.return_value = facilities
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        stats = await run_epa_frs_enrichment(db)

    assert stats["facilities_fetched"] == 1
    assert stats["matched"] == 1
    assert stats["unmatched"] == 0
    assert stats["state_presences_added"] == 1
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert isinstance(added, CompanyStatePresence)
    assert added.state == "OR"
    assert added.presence_type == "manufacturing"


@pytest.mark.asyncio
async def test_enrichment_skipped_when_flag_false():
    """Returns zero-stats immediately when enable_epa_frs=False."""
    db = AsyncMock()

    with patch("app.company_intel.epa_frs.settings") as mock_settings:
        mock_settings.enable_epa_frs = False

        stats = await run_epa_frs_enrichment(db)

    assert stats["facilities_fetched"] == 0
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_enrichment_does_not_downgrade_stronger_presence():
    """If company already has manufacturing presence, distribution is not added."""
    company = _make_company("Packaging Co")
    existing_presence = CompanyStatePresence()
    existing_presence.presence_type = "manufacturing"
    existing_presence.state = "OR"
    existing_presence.company_id = company.id

    db = AsyncMock()
    alias_mock = MagicMock()
    alias_mock.company = company
    alias_mock.match_confidence = 0.95
    db.execute.side_effect = [
        _scalar_result(alias_mock),
        _scalars_result([existing_presence]),
    ]

    facilities = [
        {"primaryName": "Packaging Co", "registryId": "REG003", "sicCodes": ["5900"]}
    ]

    with (
        patch("app.company_intel.epa_frs.settings") as mock_settings,
        patch("app.company_intel.epa_frs.EPAFRSClient") as MockClient,
    ):
        mock_settings.enable_epa_frs = True
        mock_settings.sec_user_agent = "Test/1.0"

        mock_client_instance = AsyncMock()
        mock_client_instance.fetch_state_facilities.return_value = facilities
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        stats = await run_epa_frs_enrichment(db)

    assert stats["state_presences_added"] == 0
    db.add.assert_not_called()
