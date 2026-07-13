"""Controlled product taxonomy for covered-product extraction (electronics + batteries).

This is the SINGLE source of truth for which sub-products a bill can cover, the same role
LEVERS plays in app/synthesis/design_levers.py. It is deliberately a Python module, not a DB
table: the taxonomy is reference data that evolves with the extractor and the frontend grid, so
versioning it with the code (rather than via a migration per tweak) keeps the vocabulary, the
extraction prompt, and the icon grid in lock-step.

Grounded in the Phase 0 audit of 345 electronics/battery-tagged EPR bills (38 states) plus the
CEW (Council of the Great Lakes Region / "model e-waste") covered-device list and the battery
stewardship bills' own definitions. Every slug here is something a real bill actually scopes.

Two axes a coverage row carries (see app/models.py::BillProductCoverage):
  • RELATIONSHIP — what obligation the bill imposes on the product. The audit showed the
    electronics bucket is ~half EPR / half right-to-repair, and they answer different questions:
        stewarded       — EPR "covered product": producer must fund/run end-of-life stewardship
        repairable      — right-to-repair: product must be serviceable (parts, manuals, tools)
        disposal_banned — landfill/disposal ban or material restriction on the product
        deposit_return  — deposit/refund-value mechanics attach to the product
  • STATUS — covered | exempt | conditional (covered only past a threshold, e.g. batteries >5 Wh).

`defined_by_reference` (a column, not a slug) marks products the bill covers only by pointing at an
existing statute ("as defined under ORS Chapter 459A") rather than enumerating them inline — the
accuracy ceiling flagged in the plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Obligation a bill can impose on a product. Kept narrow on purpose; extend deliberately.
RELATIONSHIPS = ("stewarded", "repairable", "disposal_banned", "deposit_return")
# Whether the product is in scope, carved out, or in only past a threshold.
STATUSES = ("covered", "exempt", "conditional")
# Top-level streams this taxonomy spans (the existing material_categories slugs).
CATEGORIES = ("electronics", "batteries", "textiles")


@dataclass(frozen=True)
class Product:
    """One leaf in the taxonomy — a thing a bill can scope, with grid-render metadata."""
    slug: str            # stable id used on coverage rows and in the API
    label: str           # human label for the grid
    category: str        # "electronics" | "batteries"
    group: str           # sub-grouping within the category (grid section header)
    icon: str            # lucide-react icon name the frontend grid renders
    # Chemistry / qualifier tags (batteries: lithium_ion, lead_acid…). Not products themselves.
    tags: tuple[str, ...] = field(default_factory=tuple)
    # Relationships that realistically apply (an EV battery is stewarded, never "repairable" here).
    relationships: tuple[str, ...] = RELATIONSHIPS
    # Whether a blanket "covers the whole class" law sweeps this product in automatically. False for
    # specialty/appliance items that are almost always scoped separately (a consumer-electronics
    # repair law's blanket clause shouldn't silently cover tractors or medical devices).
    blanket_expand: bool = True


# ---------------------------------------------------------------------------
# Electronics — grounded in CEW covered-device lists + observed bill prose.
# The "appliances" group is real, not noise: NY S-1459 / A-2164 sweep refrigerant-bearing white
# goods into the electronics bucket; right-to-repair bills (CT HB-6512) reach mobility devices.
# ---------------------------------------------------------------------------
_ELECTRONICS: tuple[Product, ...] = (
    # Displays
    Product("televisions", "Televisions", "electronics", "Displays", "tv"),
    Product("computer_monitors", "Monitors", "electronics", "Displays", "monitor"),
    # Computers
    Product("desktop_computers", "Desktops", "electronics", "Computers", "computer"),
    Product("laptops", "Laptops", "electronics", "Computers", "laptop"),
    Product("tablets", "Tablets", "electronics", "Computers", "tablet"),
    # Mobile
    Product("phones", "Phones", "electronics", "Mobile", "smartphone"),
    # Peripherals
    Product("printers", "Printers", "electronics", "Peripherals", "printer"),
    Product("computer_peripherals", "Keyboards & peripherals", "electronics", "Peripherals", "keyboard"),
    # Portable consumer electronics
    Product("e_readers", "E-readers", "electronics", "Portable", "book-open"),
    Product("cameras", "Cameras", "electronics", "Portable", "camera"),
    Product("media_players", "Audio / media players", "electronics", "Portable", "headphones"),
    Product("wearables", "Wearables", "electronics", "Portable", "watch"),
    # Entertainment / connected
    Product("game_consoles", "Game consoles", "electronics", "Entertainment", "gamepad-2"),
    Product("streaming_devices", "Set-top / streaming", "electronics", "Entertainment", "router"),
    # Appliances (white goods + small) — usually a separate stream, so not swept in by a blanket clause.
    Product("large_appliances", "Large appliances", "electronics", "Appliances", "refrigerator",
            blanket_expand=False),
    Product("small_appliances", "Small appliances", "electronics", "Appliances", "microwave",
            blanket_expand=False),
    # Specialty scopes seen in right-to-repair bills — always scoped explicitly, never via blanket.
    Product("medical_devices", "Medical devices", "electronics", "Specialty", "stethoscope",
            relationships=("repairable", "stewarded"), blanket_expand=False),
    Product("mobility_devices", "Mobility devices", "electronics", "Specialty", "accessibility",
            relationships=("repairable",), blanket_expand=False),
    Product("ag_industrial_equipment", "Ag / industrial equipment", "electronics", "Specialty", "tractor",
            relationships=("repairable",), blanket_expand=False),
    # Catch-alls
    Product("other_electronics", "Other electronics", "electronics", "Other", "cpu"),
)

# ---------------------------------------------------------------------------
# Batteries — organized on the FORMAT / application axis (how states actually scope them),
# with chemistry carried as tags. NY A-4641 (rechargeable ≥5 Wh), NY S-5663 (EV/hybrid),
# MA SD-1326 (lithium-ion) anchor these.
# ---------------------------------------------------------------------------
_BATTERIES: tuple[Product, ...] = (
    Product("rechargeable_portable", "Rechargeable / portable", "batteries", "Portable", "battery-charging",
            tags=("lithium_ion", "nickel"), relationships=("stewarded", "disposal_banned")),
    Product("single_use_primary", "Single-use (primary)", "batteries", "Portable", "battery",
            tags=("alkaline",), relationships=("stewarded", "disposal_banned")),
    Product("embedded_batteries", "Embedded in products", "batteries", "Portable", "battery-medium",
            tags=("lithium_ion",), relationships=("stewarded", "disposal_banned")),
    Product("ev_propulsion", "EV / propulsion", "batteries", "Large format", "car",
            tags=("lithium_ion",), relationships=("stewarded",)),
    Product("large_format_stationary", "Large-format / storage", "batteries", "Large format", "battery-full",
            tags=("lithium_ion", "lead_acid"), relationships=("stewarded", "disposal_banned")),
    Product("lead_acid", "Lead-acid", "batteries", "Large format", "battery-warning",
            tags=("lead_acid",), relationships=("stewarded", "disposal_banned")),
    Product("other_batteries", "Other batteries", "batteries", "Other", "battery-low"),
)

# ---------------------------------------------------------------------------
# Textiles — how apparel/textile EPR laws actually scope (CA SB-707, EU textile EPR, France's
# Refashion / AGEC). Laws distinguish worn apparel + footwear from household linens, often carve out
# accessories, and exempt industrial/commercial or specialty (PPE, medical) textiles. Relationships
# are stewarded (EPR) + disposal_banned (textile landfill bans) + repairable (France's repair bonus /
# repairability provisions for clothing & footwear); deposit-return doesn't apply to textiles.
# ---------------------------------------------------------------------------
_TEXTILE_REL = ("stewarded", "disposal_banned", "repairable")
_TEXTILES: tuple[Product, ...] = (
    Product("clothing", "Apparel / clothing", "textiles", "Apparel", "shirt", relationships=_TEXTILE_REL),
    Product("footwear", "Footwear", "textiles", "Apparel", "footprints", relationships=_TEXTILE_REL),
    Product("home_textiles", "Home textiles / linens", "textiles", "Household", "bed",
            relationships=_TEXTILE_REL),
    # Accessories (bags, belts, hats) are usually scoped explicitly, not swept in by a blanket clause.
    Product("fashion_accessories", "Accessories (bags, etc.)", "textiles", "Apparel", "shopping-bag",
            relationships=_TEXTILE_REL, blanket_expand=False),
    # Industrial / commercial textiles (uniforms, workwear) — typically a separate or exempt scope.
    Product("industrial_textiles", "Industrial / commercial", "textiles", "Specialty", "hard-hat",
            relationships=_TEXTILE_REL, blanket_expand=False),
    Product("other_textiles", "Other textiles", "textiles", "Other", "layers"),
)

PRODUCTS: tuple[Product, ...] = _ELECTRONICS + _BATTERIES + _TEXTILES

# Chemistry qualifiers a coverage row may tag (validated; not products).
BATTERY_CHEMISTRIES = ("lithium_ion", "lead_acid", "nickel", "alkaline", "other_chemistry")

# Fast lookups.
BY_SLUG: dict[str, Product] = {p.slug: p for p in PRODUCTS}
SLUGS: frozenset[str] = frozenset(BY_SLUG)


def products_for(category: str) -> list[Product]:
    """Taxonomy leaves for one stream, in declared (grid) order."""
    return [p for p in PRODUCTS if p.category == category]


def is_valid(slug: str, relationship: str | None = None) -> bool:
    """True if slug is a known product (and, if given, the relationship applies to it)."""
    p = BY_SLUG.get(slug)
    if p is None:
        return False
    return relationship is None or relationship in p.relationships


def vocab_block(category: str) -> str:
    """Render the category's products as a prompt-ready menu (slug — label [groups])."""
    lines: list[str] = []
    for p in products_for(category):
        tag = f" (tags: {', '.join(p.tags)})" if p.tags else ""
        lines.append(f"- {p.slug} — {p.label} [{p.group}]{tag}")
    return "\n".join(lines)
