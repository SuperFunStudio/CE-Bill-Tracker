"""Unit tests for the circular-economy wing roll-up (app/classification/cycles.py) and the
research-facet cycle matcher — pure functions, no DB."""
from app.classification.cycles import (
    BIOLOGICAL,
    TECHNICAL,
    MATERIAL_WINGS,
    materials_for_wing,
    wing_of,
    wings_of_material,
)
from app.classification.materials import CANONICAL_MATERIALS
from app.api.research_facets import _match_cycles


def test_every_canonical_material_mapped_except_other():
    unmapped = (CANONICAL_MATERIALS - {"other"}) - set(MATERIAL_WINGS)
    assert not unmapped


def test_paper_is_technical_not_biological():
    assert wings_of_material("paper_packaging") == frozenset({TECHNICAL})


def test_biological_and_cross_materials():
    assert wings_of_material("organics") == frozenset({BIOLOGICAL})
    assert wings_of_material("textiles") == frozenset({BIOLOGICAL, TECHNICAL})
    assert wings_of_material("water") == frozenset({BIOLOGICAL, TECHNICAL})  # forward-declared


def test_wing_of_partition():
    assert wing_of(["organics"]) == BIOLOGICAL
    assert wing_of(["plastic_packaging", "paper_packaging"]) == TECHNICAL
    assert wing_of(["organics", "plastic_packaging"]) == "both"
    assert wing_of(["textiles"]) == "both"                       # cross material alone
    assert wing_of(["other"]) == "unclassified"
    assert wing_of([]) == "unclassified"


def test_wing_of_instrument_fallback():
    # material axis silent -> a technical instrument tips it to technical; otherwise unclassified.
    assert wing_of(["other"], ["epr"]) == TECHNICAL
    assert wing_of([], ["incentives"]) == "unclassified"


def test_materials_for_wing_is_inclusive():
    bio = materials_for_wing(BIOLOGICAL)
    tech = materials_for_wing(TECHNICAL)
    assert "organics" in bio and "organics" not in tech
    assert "plastic_packaging" in tech and "plastic_packaging" not in bio
    # cross-wing materials appear under BOTH
    assert "textiles" in bio and "textiles" in tech
    assert "paper_packaging" in tech and "paper_packaging" not in bio


def test_match_cycles_resolves_wings():
    slugs, labels, _ = _match_cycles("show me the biological cycle", "show me the biological cycle")
    assert slugs == ["biological"]
    for q in ("technical cycle bills", "bills in the artificial cycle", "technosphere bills"):
        slugs, _, _ = _match_cycles(q, q)
        assert slugs == ["technical"], q
    slugs, _, _ = _match_cycles("bills about tires", "bills about tires")
    assert slugs == []
