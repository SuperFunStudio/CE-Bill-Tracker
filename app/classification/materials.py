"""Canonical material-category taxonomy + alias normalization — one set across all regions.

The classifier prompt (haiku_classifier.USER_TEMPLATE) asks for CANONICAL_MATERIALS, but older US
rows (and the occasional LLM stray) carry near-synonyms or niche slugs. `normalize_materials` folds
those into the canonical set so US/EU/JP/… are directly comparable on the material axis. Applied at
write time in the classification pipeline, and to existing rows by scripts/normalize_materials.py.

When adding a new canonical category, add it here (single source of truth) AND to the prompt list.
"""
from __future__ import annotations

# The single canonical set. Mirrors the classifier prompt's material_categories list.
CANONICAL_MATERIALS: frozenset[str] = frozenset({
    "plastic_packaging", "paper_packaging", "glass", "metals", "electronics", "batteries",
    "paint", "carpet", "mattresses", "tires", "vehicles", "construction", "furniture",
    "used_oil", "pharmaceuticals", "solar_panels", "textiles", "organics", "biobased",
    "agriculture", "hazardous_materials", "other",
})

# Non-canonical slug -> canonical. Folds synonyms (paper→paper_packaging) and niche streams into the
# nearest canonical bucket so the cross-region comparison is apples-to-apples.
#   - mercury / household_hazardous_waste / auto_switches (mercury switches) -> hazardous_materials
#     (the regulated thing is the toxic substance, not the host product).
#   - thermostats / lighting -> electronics (WEEE treats lamps & appliances as e-waste).
#   - plastics / plastic_products / packaging -> plastic_packaging (dominant form);
#     paper -> paper_packaging; medical_sharps -> pharmaceuticals; pesticides -> agriculture.
MATERIAL_ALIASES: dict[str, str] = {
    "paper": "paper_packaging",
    "packaging": "plastic_packaging",
    "plastics": "plastic_packaging",
    "plastic_products": "plastic_packaging",
    "thermostats": "electronics",
    "lighting": "electronics",
    "medical_sharps": "pharmaceuticals",
    "pesticides": "agriculture",
    "mercury": "hazardous_materials",
    "household_hazardous_waste": "hazardous_materials",
    "auto_switches": "hazardous_materials",
}

# Roll-up groupings for the cross-region comparison / UI. The per-bill material tags stay granular
# (plastic_packaging vs paper_packaging matters for EPR fees/recycled-content); a group just lets a
# view aggregate them under one top-level header. material_group() returns the group, else the slug.
MATERIAL_GROUPS: dict[str, list[str]] = {
    "packaging": ["plastic_packaging", "paper_packaging", "glass", "metals"],
}
_SLUG_TO_GROUP = {s: g for g, members in MATERIAL_GROUPS.items() for s in members}


def material_group(slug: str) -> str:
    """Top-level grouping for a canonical material slug (e.g. plastic_packaging -> packaging)."""
    return _SLUG_TO_GROUP.get(slug, slug)


def normalize_materials(mats: list[str] | None) -> list[str]:
    """Map a material list to the canonical set: apply aliases, bucket unknowns to 'other', dedup
    (order-preserving). Returns [] for empty input."""
    out: list[str] = []
    for m in mats or []:
        if not m:
            continue
        c = MATERIAL_ALIASES.get(m, m)
        if c not in CANONICAL_MATERIALS:
            c = "other"
        if c not in out:
            out.append(c)
    return out
