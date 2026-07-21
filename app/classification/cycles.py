"""Circular-economy CYCLE roll-up — the two wings of the butterfly diagram, derived from the material
axis. Not a stored/judged field: a bill's wing is computed from its ``material_categories`` (with a
weak instrument fallback), so this adds the biological/technical structure with zero reclassification
and zero LLM cost.

Design decisions (validated against the prod-parity corpus, 2,156 relevant bills):
  * The MATERIAL axis carries the wing signal; ``instrument_type`` is technical-skewed (EPR / repair /
    deposit / recycled-content are all technical-loop levers, and the biological cycle rides generic
    incentives/standards/other), so instrument is only a last-resort tiebreak.
  * ``paper_packaging`` sits on the TECHNICAL wing: it's an engineered material (coatings, inks,
    sizing) managed through industrial recycling infrastructure. Its biological *origin* is preserved
    separately in ``CASCADE_CANDIDATES`` (a "bio-origin material stuck in a technical loop" is a real
    cascade-failure lens), but its *wing* — where it's managed — is technical.
  * ``textiles`` and ``water`` are genuinely cross-wing (natural vs. synthetic fibre; water is
    leakage out of *both* cycles), so they belong to both wings for filtering purposes.

``water`` and ``biodiversity`` are forward-declared here (no bills carry them yet) so the wing map is
drop-in once those materials are added to ``CANONICAL_MATERIALS`` — biodiversity is the biological
cycle's regenerative outcome; water is cross-wing leakage.
"""
from __future__ import annotations

from app.classification.materials import CANONICAL_MATERIALS

BIOLOGICAL = "biological"
TECHNICAL = "technical"

# Each material -> the wing(s) it belongs to. Subsets of {BIOLOGICAL, TECHNICAL}. "other" is
# intentionally absent (-> unclassified). water/biodiversity are forward-declared (see module docstring).
_BIOLOGICAL_ONLY = frozenset({"organics", "biobased", "agriculture", "biodiversity"})
_TECHNICAL_ONLY = frozenset({
    "plastic_packaging", "paper_packaging", "glass", "metals", "electronics", "batteries", "paint",
    "carpet", "mattresses", "tires", "vehicles", "construction", "furniture", "used_oil",
    "pharmaceuticals", "solar_panels", "hazardous_materials",
})
_CROSS = frozenset({"textiles", "water"})  # relevant to both wings

MATERIAL_WINGS: dict[str, frozenset[str]] = {
    **{m: frozenset({BIOLOGICAL}) for m in _BIOLOGICAL_ONLY},
    **{m: frozenset({TECHNICAL}) for m in _TECHNICAL_ONLY},
    **{m: frozenset({BIOLOGICAL, TECHNICAL}) for m in _CROSS},
}

# Biological-origin materials that are managed in the technical cycle — the "cascade candidates" whose
# fibre could, in principle, return to the biosphere but is locked into recycling loops by engineering.
# Reference metadata only (not used in wing assignment); powers the future cascade-failure lens.
CASCADE_CANDIDATES: frozenset[str] = frozenset({"paper_packaging", "construction", "furniture", "textiles"})

# Instruments that skew technical — the ONLY ones strong enough to serve as a last-resort wing tiebreak
# when a bill has no wing-bearing material (usually because it was text-starved and tagged only "other").
_TECHNICAL_INSTRUMENTS = frozenset({"epr", "right_to_repair", "deposit_return", "recycled_content"})

# Coverage guard: every canonical material except "other" must be mapped, or the partition silently
# drops a stream. Forward-declared slugs (water/biodiversity) are allowed to exceed the canonical set.
_unmapped = (CANONICAL_MATERIALS - {"other"}) - set(MATERIAL_WINGS)
assert not _unmapped, f"cycles.py: unmapped canonical materials {sorted(_unmapped)}"


def wings_of_material(slug: str) -> frozenset[str]:
    """The wing(s) a single material belongs to ({} for 'other'/unknown)."""
    return MATERIAL_WINGS.get(slug, frozenset())


def wing_of(materials: list[str] | None, instruments: list[str] | None = None) -> str:
    """Strict partition of a bill into one wing: 'biological' | 'technical' | 'both' | 'unclassified'.

    Cross-wing materials (textiles/water) or a mix of biological+technical materials -> 'both'. If the
    material axis is silent, fall back to a technical-skewed instrument (-> 'technical'), else
    'unclassified'. Used for reporting/aggregates; the research facet uses inclusive filtering instead
    (see materials_for_wing)."""
    wings = {w for m in (materials or []) for w in MATERIAL_WINGS.get(m, ())}
    if wings == {BIOLOGICAL, TECHNICAL}:
        return "both"
    if wings == {BIOLOGICAL}:
        return BIOLOGICAL
    if wings == {TECHNICAL}:
        return TECHNICAL
    # material axis silent -> weak instrument tiebreak
    if any(i in _TECHNICAL_INSTRUMENTS for i in (instruments or [])):
        return TECHNICAL
    return "unclassified"


def materials_for_wing(wing: str) -> list[str]:
    """Inclusive set of material slugs to filter on for a wing (a cross-wing material appears under
    both wings — a 'both' bill IS relevant to each). This is the FACET-filter view; contrast with
    wing_of's strict, mutually-exclusive partition."""
    return sorted(m for m, wings in MATERIAL_WINGS.items() if wing in wings)
