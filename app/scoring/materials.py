"""Canonical material-category vocabulary.

Bills and companies grew slightly different vocabularies for the same materials — bills
carry `glass` / `metals`, companies carry `glass_packaging` / `aluminum_packaging`. That
mismatch meant glass/metal exposure never intersected when matching a company to enacted
laws. This module is the single source of truth that normalizes both sides to one form.

Canonical form is the company/material vocabulary (the `_packaging` suffix), because that
is what company material volumes and the CA SB 54 fee schedule are keyed on. Anything not
in the alias map normalizes to itself (electronics, batteries, paint, …).
"""
from __future__ import annotations

# raw token -> canonical category. Keys are lowercased; lookups lowercase first.
_CANONICAL_ALIASES: dict[str, str] = {
    "glass": "glass_packaging",
    "metals": "aluminum_packaging",
    "metal": "aluminum_packaging",
    "metal_packaging": "aluminum_packaging",
    "aluminum": "aluminum_packaging",
    "plastic": "plastic_packaging",
    "paper": "paper_packaging",
    "fiber": "paper_packaging",
    "paper_products": "paper_packaging",
}


def canonical_material_category(category: str | None) -> str | None:
    """Normalize a single material-category token to its canonical form."""
    if not category:
        return category
    key = category.strip().lower()
    return _CANONICAL_ALIASES.get(key, key)


def canonical_set(categories) -> set[str]:
    """Normalize an iterable of category tokens to a set of canonical forms."""
    return {c for c in (canonical_material_category(x) for x in (categories or [])) if c}
