"""Unit tests for the composite scoring engine.

No database required — all tests use in-memory Python objects.
"""
import uuid

import pytest

from app.models import (
    Bill,
    Company,
    CompanyMaterial,
    CompanyStatePresence,
    ImpactScore,
)
from app.scoring.engine import ScoringEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> ScoringEngine:
    return ScoringEngine(material_weight=0.35, geographic_weight=0.35, severity_weight=0.30)


@pytest.fixture
def oregon_bill() -> Bill:
    b = Bill()
    b.id = 1
    b.state = "OR"
    b.status = "signed"
    b.material_categories = ["plastic_packaging"]
    # fee_per_ton lives inside compliance_details.fees (new structure)
    b.compliance_details = {"fees": {"fee_per_ton": 250.0, "fee_structure_source": "industry_benchmark"}}
    return b


@pytest.fixture
def company_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def company(company_id: uuid.UUID) -> Company:
    c = Company()
    c.id = company_id
    c.name = "Test Packaging Co"
    c.hq_state = "OR"
    return c


@pytest.fixture
def material_with_volume(company_id: uuid.UUID) -> CompanyMaterial:
    m = CompanyMaterial()
    m.company_id = company_id
    m.material_category = "plastic_packaging"
    m.annual_volume_tonnes = 1000.0
    m.volume_confidence = 0.9
    m.source = "manual"
    return m


@pytest.fixture
def material_no_volume(company_id: uuid.UUID) -> CompanyMaterial:
    m = CompanyMaterial()
    m.company_id = company_id
    m.material_category = "plastic_packaging"
    m.annual_volume_tonnes = None
    m.volume_confidence = None
    m.source = "manual_estimate"
    return m


@pytest.fixture
def oregon_manufacturing_presence(company_id: uuid.UUID) -> CompanyStatePresence:
    p = CompanyStatePresence()
    p.company_id = company_id
    p.state = "OR"
    p.presence_type = "manufacturing"
    p.is_primary = True
    return p


# ---------------------------------------------------------------------------
# Material score tests
# ---------------------------------------------------------------------------


def test_material_score_volume_weighted(
    engine: ScoringEngine,
    company_id: uuid.UUID,
    material_with_volume: CompanyMaterial,
) -> None:
    """Company has 1000t of 5000t total industry volume -> ~20% score."""
    other_id = uuid.uuid4()
    all_volumes = {company_id: 1000.0, other_id: 4000.0}
    score, confidence = engine.score_material(
        [material_with_volume], ["plastic_packaging"], all_volumes, company_id
    )
    assert abs(score - 20.0) < 0.1
    assert confidence == pytest.approx(0.9)


def test_material_score_100_percent_of_volume(
    engine: ScoringEngine,
    company_id: uuid.UUID,
    material_with_volume: CompanyMaterial,
) -> None:
    """Company is the only producer -> score caps at 100."""
    all_volumes = {company_id: 1000.0}
    score, confidence = engine.score_material(
        [material_with_volume], ["plastic_packaging"], all_volumes, company_id
    )
    assert score == pytest.approx(100.0)


def test_material_score_fallback_count_based(
    engine: ScoringEngine,
    company_id: uuid.UUID,
    material_no_volume: CompanyMaterial,
) -> None:
    """Falls back to count-based when no volume data; confidence = 0.0."""
    score, confidence = engine.score_material(
        [material_no_volume], ["plastic_packaging"], {}, company_id
    )
    assert score > 0
    assert confidence == 0.0


def test_material_score_no_matching_materials(
    engine: ScoringEngine,
    company_id: uuid.UUID,
    material_with_volume: CompanyMaterial,
) -> None:
    """Bill covers electronics, company has plastic only -> score 0."""
    score, confidence = engine.score_material(
        [material_with_volume], ["electronics"], {}, company_id
    )
    assert score == 0.0
    assert confidence == 0.0


# ---------------------------------------------------------------------------
# Geographic score tests
# ---------------------------------------------------------------------------


def test_geographic_score_manufacturing_100(
    engine: ScoringEngine,
    oregon_manufacturing_presence: CompanyStatePresence,
) -> None:
    score = engine.score_geographic([oregon_manufacturing_presence], "OR")
    assert score == 100.0


def test_geographic_score_retail_60(
    engine: ScoringEngine,
    company_id: uuid.UUID,
) -> None:
    p = CompanyStatePresence()
    p.state = "OR"
    p.presence_type = "retail"
    score = engine.score_geographic([p], "OR")
    assert score == 60.0


def test_geographic_score_headquarters_80(
    engine: ScoringEngine,
    company_id: uuid.UUID,
) -> None:
    p = CompanyStatePresence()
    p.state = "OR"
    p.presence_type = "headquarters"
    score = engine.score_geographic([p], "OR")
    assert score == 80.0


def test_geographic_score_no_presence_in_state(
    engine: ScoringEngine,
    oregon_manufacturing_presence: CompanyStatePresence,
) -> None:
    """Company has manufacturing in OR but bill is for CA -> 0."""
    score = engine.score_geographic([oregon_manufacturing_presence], "CA")
    assert score == 0.0


def test_geographic_score_takes_max_weight(
    engine: ScoringEngine,
    company_id: uuid.UUID,
) -> None:
    """Company has both retail and manufacturing in OR -> takes manufacturing (100)."""
    retail = CompanyStatePresence()
    retail.state = "OR"
    retail.presence_type = "retail"

    mfg = CompanyStatePresence()
    mfg.state = "OR"
    mfg.presence_type = "manufacturing"

    score = engine.score_geographic([retail, mfg], "OR")
    assert score == 100.0


# ---------------------------------------------------------------------------
# Severity score tests
# ---------------------------------------------------------------------------


def test_severity_score_signed_with_fee(
    engine: ScoringEngine,
    oregon_bill: Bill,
) -> None:
    """Signed bill + fees.fee_per_ton=250 -> likelihood=100*0.4=40, impact=50*0.6=30 -> 70."""
    score = engine.score_severity(oregon_bill)
    # impact = min(250 / 500 * 100, 100) = 50.0
    # severity = 100 * 0.4 + 50 * 0.6 = 40 + 30 = 70.0
    assert abs(score - 70.0) < 1.0


def test_severity_score_introduced_no_details(engine: ScoringEngine) -> None:
    """Introduced bill + no compliance_details -> likelihood=20*0.4=8, impact=30*0.6=18 -> 26."""
    b = Bill()
    b.status = "introduced"
    b.compliance_details = None
    score = engine.score_severity(b)
    assert abs(score - 26.0) < 1.0


def test_severity_score_enacted_with_compliance(engine: ScoringEngine) -> None:
    """Enacted bill with compliance_details but no fee -> impact defaults to 50."""
    b = Bill()
    b.status = "enacted"
    b.compliance_details = {"registration_required": True}  # no fee_per_ton key
    score = engine.score_severity(b)
    # likelihood=100*0.4=40, impact=50*0.6=30 -> 70
    assert abs(score - 70.0) < 1.0


def test_severity_score_unknown_status(engine: ScoringEngine) -> None:
    """Unknown status defaults to likelihood=20."""
    b = Bill()
    b.status = "some_unknown_status"
    b.compliance_details = None
    score = engine.score_severity(b)
    assert abs(score - 26.0) < 1.0


# ---------------------------------------------------------------------------
# Composite / compute tests
# ---------------------------------------------------------------------------


def test_compute_returns_impact_score_instance(
    engine: ScoringEngine,
    company: Company,
    oregon_bill: Bill,
    material_with_volume: CompanyMaterial,
    oregon_manufacturing_presence: CompanyStatePresence,
    company_id: uuid.UUID,
) -> None:
    """compute() returns a properly typed ImpactScore with composite in [0, 100]."""
    all_volumes = {company_id: 1000.0}
    result = engine.compute(
        company,
        oregon_bill,
        [material_with_volume],
        [oregon_manufacturing_presence],
        all_volumes,
    )
    assert isinstance(result, ImpactScore)
    assert 0 <= result.composite_score <= 100
    assert result.company_id == company_id
    assert result.bill_id == 1


def test_compute_score_breakdown_populated(
    engine: ScoringEngine,
    company: Company,
    oregon_bill: Bill,
    material_with_volume: CompanyMaterial,
    oregon_manufacturing_presence: CompanyStatePresence,
    company_id: uuid.UUID,
) -> None:
    """score_breakdown dict contains all expected keys."""
    result = engine.compute(
        company,
        oregon_bill,
        [material_with_volume],
        [oregon_manufacturing_presence],
        {company_id: 1000.0},
    )
    assert result.score_breakdown is not None
    for key in ("material_score", "geographic_score", "severity_score", "volume_confidence"):
        assert key in result.score_breakdown


def test_compute_control_company_zero_geographic(
    engine: ScoringEngine,
    company_id: uuid.UUID,
) -> None:
    """Company with no Oregon presence scores 0 on geographic for an OR bill."""
    company = Company()
    company.id = company_id
    company.name = "Control Corp"
    company.hq_state = "TX"

    bill = Bill()
    bill.id = 2
    bill.state = "OR"
    bill.status = "signed"
    bill.material_categories = ["paper_packaging"]
    bill.compliance_details = None

    mat = CompanyMaterial()
    mat.company_id = company_id
    mat.material_category = "paper_packaging"
    mat.annual_volume_tonnes = 2000.0
    mat.volume_confidence = 0.6

    tx_presence = CompanyStatePresence()
    tx_presence.state = "TX"
    tx_presence.presence_type = "headquarters"

    result = engine.compute(company, bill, [mat], [tx_presence], {company_id: 2000.0})
    assert result.geographic_score == 0.0
    # Material=100*0.35=35, Geographic=0, Severity (signed, no fee)=58*0.30=17.4 -> 52.4
    # Composite is reduced vs. a company with Oregon presence (which would also get 35 from geo)
    assert result.composite_score < 60.0
    assert result.geographic_score == 0.0
