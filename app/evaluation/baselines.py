"""Strong-bill baseline templates — each regime's "model bill" encoded as the eight compliance envelopes
at their strong settings, so a draft can be diffed dimension-by-dimension against the ideal for its
material class (rendered with the same dimensions.ts as bill detail).

Why 'strong' differs by regime (see app/evaluation/strength.py): critical-mass materials demand the full
engineered-critical-mass stack — mandated value-based collection, a pooled-financed PRO, design bans,
material-ID labeling, fees that fund reverse logistics. Incremental-viable materials are strong when the
bill simply internalizes the externality, so their template is lean and marks the heavy machinery
`not_applicable` (a deliberate "not needed here"), not `missing`.

The regime-key strings are duplicated from strength.py on purpose: strength imports THIS module, so this
module must not import strength back. `{material}` placeholders are filled with the positioned material
at response time; percent/by_year values encode the SHAPE (mandated, value-based, ramped), not a calendar.
"""
from __future__ import annotations

import copy

_CRITICAL = "critical_mass"
_INCREMENTAL = "incremental_viable"

_CRITICAL_TEMPLATE = {
    "collection_targets": {
        "status": "present",
        "targets": [{"material": "{material}", "percent": 90, "by_year": "ramp target", "basis": "value_recovered"}],
        "source_excerpt": "Mandated collection ramped toward near-total coverage — the minimum-viable-"
        "circulation threshold — measured by value recovered, not raw weight.",
    },
    "pro_structure": {
        "status": "present", "model": "single_pro", "needs_assessment": True, "named_pros": [],
        "source_excerpt": "A producer responsibility organization with pooled producer financing funds "
        "collection, sortation, and the decomposer layer no single firm will build alone.",
    },
    "eco_modulation": {
        "status": "present",
        "criteria": ["recyclability", "recycled_content", "durability", "repairability", "reusability"],
        "source_excerpt": "Fees modulated on the design attributes that make a dispersed stream sortable "
        "and recoverable.",
    },
    "fee_amounts": {
        "status": "present",
        "rates": [{"basis": "eco_modulated", "amount": None, "currency": "USD", "material": "{material}"}],
        "source_excerpt": "Producer fees scaled to actually fund reverse logistics below break-even route "
        "density.",
    },
    "bans_restrictions": {
        "status": "present",
        "items": [{"target": "non-recyclable / non-sortable {material}", "type": "design_ban", "effective_date": "phase-in"}],
        "source_excerpt": "Design bans remove material that can't be sorted or recovered from the stream.",
    },
    "labeling": {
        "status": "present",
        "requirements": [
            {"type": "material_id", "on_pack": True, "detail": "Standardized material identification for sortation."},
            {"type": "disposal_instructions", "on_pack": True, "detail": "How to return / recycle the product."},
        ],
        "source_excerpt": "On-product material-ID labeling lets sorters route the stream.",
    },
    "recycled_content": {
        "status": "present",
        "minimums": [{"material": "{material}", "percent": 30, "by_year": "ramp target"}],
        "source_excerpt": "Recycled-content minimums thicken demand for the secondary material the "
        "collection system produces.",
    },
    "penalties": {
        "status": "present", "max_amount": None, "currency": "USD", "per": "violation",
        "source_excerpt": "Enforcement penalties for non-participation.",
    },
}

_INCREMENTAL_TEMPLATE = {
    "fee_amounts": {
        "status": "present",
        "rates": [{"basis": "per_unit", "amount": None, "currency": "USD", "material": "{material}"}],
        "source_excerpt": "A fee or advance-recovery obligation internalizes the disposal externality so "
        "the durable, repairable product isn't undercut by the disposable one. This is the whole job here.",
    },
    "eco_modulation": {
        "status": "present", "criteria": ["durability", "repairability", "recycled_content"],
        "source_excerpt": "Eco-modulation rewards the durability and repairability the first mover already "
        "captures as brand and warranty-cost value.",
    },
    "collection_targets": {
        "status": "present",
        "targets": [{"material": "{material}", "percent": None, "by_year": "target", "basis": "value_recovered"}],
        "source_excerpt": "A recovery floor measured by value recovered — light-touch, because the "
        "established reverse channel already carries the volume.",
    },
    "recycled_content": {
        "status": "present",
        "minimums": [{"material": "{material}", "percent": 25, "by_year": "target"}],
        "source_excerpt": "A recycled-content floor.",
    },
    "penalties": {
        "status": "present", "max_amount": None, "currency": "USD", "per": "violation",
        "source_excerpt": "An enforcement backstop.",
    },
    # The heavy critical-mass machinery is NOT required for a high-value, already-circulating material —
    # mark it not_applicable so the diff reads "not needed in this regime", not "missing".
    "pro_structure": {"status": "not_applicable"},
    "bans_restrictions": {"status": "not_applicable"},
    "labeling": {"status": "not_applicable"},
}

_TEMPLATES = {_CRITICAL: _CRITICAL_TEMPLATE, _INCREMENTAL: _INCREMENTAL_TEMPLATE}


def _fill(node, material: str):
    if isinstance(node, str):
        return node.replace("{material}", material)
    if isinstance(node, dict):
        return {k: _fill(v, material) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill(v, material) for v in node]
    return node


def baseline_for(regime_key: str, material: str) -> dict:
    """The strong model bill for this regime, as a compliance_details-shaped envelope map with the
    positioned material filled in. Falls back to the critical-mass template for an unknown regime."""
    template = _TEMPLATES.get(regime_key, _CRITICAL_TEMPLATE)
    return _fill(copy.deepcopy(template), material or "covered products")
