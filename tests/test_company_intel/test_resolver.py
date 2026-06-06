"""Unit tests for EntityResolver.

Uses unittest.mock.AsyncMock to mock the database session — no real DB required.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.company_intel.resolver import EntityResolver, FUZZY_THRESHOLD
from app.models import Company, CompanyAlias, EntityMatchQueue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_company(name: str = "Test Co", duns: str | None = None) -> Company:
    c = Company()
    c.id = uuid.uuid4()
    c.name = name
    c.duns_number = duns
    c.cik = None
    c.epa_registry_id = None
    return c


def _make_alias(company: Company, alias_name: str, confidence: float = 0.95) -> CompanyAlias:
    a = CompanyAlias()
    a.id = uuid.uuid4()
    a.alias_name = alias_name
    a.match_confidence = confidence
    a.company = company
    a.company_id = company.id
    return a


def _scalar_result(value) -> MagicMock:
    """Simulate db.execute() result with .scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _empty_result() -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.first.return_value = None
    return result


# ---------------------------------------------------------------------------
# Test: Step 1 — Hard identifier match (DUNS)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_match_on_duns() -> None:
    """Resolver finds company by DUNS number -> returns (company, 1.0)."""
    company = _make_company("Pacific Seafood", duns="123456789")
    db = AsyncMock()
    db.execute.return_value = _scalar_result(company)

    resolver = EntityResolver(db)
    result_company, confidence = await resolver.resolve(
        "Pacific Seafood Group", source="test", duns="123456789"
    )

    assert result_company is company
    assert confidence == 1.0
    # Only one DB query executed (hard ID lookup)
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_exact_match_on_cik() -> None:
    """Resolver finds company by CIK -> returns (company, 1.0)."""
    company = _make_company("Intel Corp")
    db = AsyncMock()
    db.execute.return_value = _scalar_result(company)

    resolver = EntityResolver(db)
    result_company, confidence = await resolver.resolve(
        "Intel Corporation", source="edgar", cik="0000050863"
    )

    assert result_company is company
    assert confidence == 1.0


# ---------------------------------------------------------------------------
# Test: Step 2 — Exact alias match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_alias_match() -> None:
    """No hard ID match; alias table has an exact match -> returns alias company."""
    company = _make_company("Pacific Seafood Group")
    alias = _make_alias(company, "Pacific Seafood", confidence=0.95)

    db = AsyncMock()
    # First call: hard ID lookup (no duns/cik/epa_id passed) -> skip to step 2
    # Second call: alias lookup -> returns alias
    db.execute.side_effect = [
        _scalar_result(alias),
    ]

    resolver = EntityResolver(db)
    result_company, confidence = await resolver.resolve("Pacific Seafood", source="test")

    assert result_company is company
    assert confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_exact_alias_match_uses_default_confidence_when_none() -> None:
    """Alias with match_confidence=None defaults to 0.95."""
    company = _make_company("BiMart")
    alias = _make_alias(company, "BiMart", confidence=None)  # type: ignore[arg-type]
    alias.match_confidence = None

    db = AsyncMock()
    db.execute.return_value = _scalar_result(alias)

    resolver = EntityResolver(db)
    _, confidence = await resolver.resolve("BiMart", source="test")
    assert confidence == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# Test: Step 4 — Queue when no match found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_match_queues_entry_and_returns_none() -> None:
    """No exact or fuzzy match -> inserts EntityMatchQueue entry, returns (None, 0.0)."""
    db = AsyncMock()
    # alias lookup returns None; trgm query returns None
    no_alias = _scalar_result(None)
    no_trgm = MagicMock()
    no_trgm.first.return_value = None

    db.execute.side_effect = [no_alias, no_trgm]
    db.flush = AsyncMock()

    resolver = EntityResolver(db)
    result_company, confidence = await resolver.resolve("Completely Unknown Corp", source="test")

    assert result_company is None
    assert confidence == 0.0
    # db.add was called with an EntityMatchQueue instance
    db.add.assert_called_once()
    queued_entry = db.add.call_args[0][0]
    assert isinstance(queued_entry, EntityMatchQueue)
    assert queued_entry.candidate_name == "Completely Unknown Corp"
    assert queued_entry.resolved is False
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_fuzzy_match_below_threshold_queues() -> None:
    """Fuzzy match exists but below threshold (no rows returned) -> queued."""
    db = AsyncMock()
    no_alias = _scalar_result(None)
    # Simulate pg_trgm returning nothing (similarity < threshold)
    no_trgm = MagicMock()
    no_trgm.first.return_value = None

    db.execute.side_effect = [no_alias, no_trgm]
    db.flush = AsyncMock()

    resolver = EntityResolver(db)
    company, confidence = await resolver.resolve("Vaguely Similar Name", source="test")

    assert company is None
    db.add.assert_called_once()


# ---------------------------------------------------------------------------
# Test: No identifier provided skips Step 1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_hard_id_skips_step1() -> None:
    """When no duns/cik/epa_id provided, Step 1 is skipped entirely."""
    company = _make_company("BiMart")
    alias = _make_alias(company, "Bi-Mart")

    db = AsyncMock()
    # Only the alias lookup fires (step 2)
    db.execute.return_value = _scalar_result(alias)

    resolver = EntityResolver(db)
    result_company, _ = await resolver.resolve("Bi-Mart", source="test")

    # Should succeed via alias match in one execute call
    assert result_company is company
    assert db.execute.call_count == 1
