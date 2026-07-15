"""Facet resolution for the Atlas research engine — turns a natural-language question into structured
filters over the corpus, deterministically (no per-request LLM, so paging is stable and free).

The essential facet is **jurisdiction**: region/country isn't in a bill's (often foreign-language)
body text, so "examples from France" can't be served by full-text search — it must become a
`jurisdiction_id` filter. We resolve places by scanning the question against the `jurisdictions`
alias table ("France"/"French" -> FR node), expand to the subtree ("US" -> all states), and strip the
matched place words out of the residual free text so FTS runs on the substantive terms only.

Dimension + free-text handling stay in app/api/research.py; this module owns the geographic facet.
An LLM router for messy phrasing / follow-ups is a later add (A2) — deterministic is the right v1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Jurisdiction

# Words that shouldn't count as "meaningful" free text when deciding text-search vs a plain listing.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "from", "about", "any",
    "is", "are", "there", "what", "which", "how", "do", "does", "bills", "bill", "law", "laws",
    "records", "record", "examples", "example", "compare", "comparison", "show", "me", "us",  # "us" here is the pronoun; the country is caught as an uppercase code
    "list", "give", "tell", "find", "get", "that", "this", "these", "those", "their", "its",
    # Chrome words that describe the QUERY, not the subject — kept out of the tsquery so they can't
    # AND-poison a search. Conservative: only unambiguous query-framing words (NOT topic nouns like
    # "corpus"/"incentives" whose presence/absence affects dimension routing — that's LLM-router work).
    "database", "have", "has", "please", "can", "you", "your", "like", "such", "including",
    "cover", "covers", "covered", "covering",  # "which bills COVER laptops" — chrome, not a search term
    # Comparative-framing chrome — "what can the rest of the regions LEARN from the US bills?". With a
    # place scoped, these survived into the tsquery and AND-poisoned Rule 1: US (8443 bills) had 8 that
    # happened to contain rest+regions+learn, starving the answer to 8, while foreign regions' non-
    # English text matched none and correctly fell through to the full-region listing. "region(s)" is
    # chrome in a jurisdiction tool; the topical "across/other regions" senses are handled by
    # _EXPANSION_CUES above, not here.
    "learn", "learns", "learned", "teach", "teaches", "lesson", "lessons", "rest", "others",
    "region", "regions", "regional", "jurisdiction", "jurisdictions",
})


# Phrases that mean "search everywhere" — a named place is then a REFERENCE subject, not a scope
# filter. "Comparable laws to France's AGEC across all regions" must NOT lock retrieval to France.
_EXPANSION_CUES = (
    "all regions", "all jurisdictions", "all countries", "every region", "every country",
    "other regions", "other jurisdictions", "other countries", "other states",
    "whole corpus", "entire corpus", "across the corpus", "across regions", "across jurisdictions",
    "globally", "worldwide", "world wide", "everywhere", "anywhere else", "elsewhere",
    "compared to other", "comparable", "similar to", "similar law", "similar mechanism", "counterpart",
)


# Natural-language → canonical material_categories slug (see app/classification/materials.py). Lets
# "what does the corpus have about tires?" resolve to the material FACET (material_categories @>
# ['tires'], the clean 77-bill set) instead of a junk-polluted text search, and folds UK/US spellings
# (tyre/tire) so the user never has to. Aliases are lowercased; matched >=3-char whole words/phrases.
_MATERIAL_ALIASES: dict[str, list[str]] = {
    "tires": ["tire", "tires", "tyre", "tyres", "scrap tire", "waste tire"],
    "electronics": ["electronics", "electronic", "e-waste", "ewaste", "weee", "consumer electronics",
                    "appliance", "appliances", "electronic device", "electronic devices"],
    "batteries": ["battery", "batteries", "lithium-ion", "lithium ion", "lead-acid", "lead acid"],
    "plastic_packaging": ["plastic packaging", "plastics", "plastic", "single-use plastic",
                          "single use plastic", "plastic bottle", "plastic bottles"],
    "paper_packaging": ["paper packaging", "cardboard", "paperboard", "fiber packaging"],
    "glass": ["glass"],
    "metals": ["aluminum", "aluminium", "steel can", "metal can", "metal cans", "metals"],
    "paint": ["paint", "paints", "architectural paint", "coating"],
    "carpet": ["carpet", "carpets", "carpeting"],
    "mattresses": ["mattress", "mattresses", "bedding"],
    "vehicles": ["vehicle", "vehicles", "automobile", "automobiles", "end-of-life vehicle", "elv"],
    "construction": ["construction and demolition", "construction & demolition", "c&d waste",
                     "building material", "building materials"],
    "furniture": ["furniture"],
    "used_oil": ["used oil", "motor oil", "waste oil", "lubricant", "lubricating oil"],
    "pharmaceuticals": ["pharmaceutical", "pharmaceuticals", "drug", "drugs", "medication",
                        "medications", "medicine", "medicines", "sharps"],
    "solar_panels": ["solar panel", "solar panels", "solar module", "solar modules", "photovoltaic",
                     "solar"],
    "textiles": ["textile", "textiles", "clothing", "apparel", "fashion", "fabric"],
    "organics": ["organics", "organic waste", "compost", "composting", "food waste", "yard waste",
                 "food scraps"],
    "biobased": ["biobased", "bio-based", "bioplastic", "bioplastics", "biomaterial", "biomaterials"],
    "agriculture": ["agriculture", "agricultural", "pesticide", "pesticides", "farm waste"],
    "hazardous_materials": ["hazardous material", "hazardous materials", "hazardous waste",
                            "household hazardous", "mercury", "toxic substance"],
}
# Group names expand to member slugs (a bill can carry several packaging tags).
_MATERIAL_GROUPS: dict[str, list[str]] = {
    "packaging": ["plastic_packaging", "paper_packaging", "glass", "metals"],
}
_MATERIAL_LABELS: dict[str, str] = {s: s.replace("_", " ") for s in _MATERIAL_ALIASES}

# Natural-language → instrument_type slug. "EPR bills on electronics" should filter by the epr
# instrument (a structured field), not text-match "epr" — which is unreliable (bills say "extended
# producer responsibility", and the acronym rarely appears verbatim). Kept to unambiguous instruments.
_INSTRUMENT_ALIASES: dict[str, list[str]] = {
    "epr": ["epr", "extended producer responsibility"],
    "right_to_repair": ["right to repair", "right-to-repair"],
    "deposit_return": ["deposit return", "deposit-return", "bottle bill", "container deposit",
                       "deposit refund", "deposit scheme"],
}
_INSTRUMENT_LABELS: dict[str, str] = {
    "epr": "EPR", "right_to_repair": "right to repair", "deposit_return": "deposit return",
}

# Natural-language → bill_product_coverage.product_slug (see app/synthesis/product_taxonomy.py). The
# finest facet: "which bills cover laptops?" / "EV vs portable batteries" / "footwear EPR" filter via
# the extracted per-product coverage (electronics + batteries + textiles). Catch-all *_other slugs are
# intentionally not aliased (nobody queries "other electronics"). Lowercased; matched >=3-char phrases.
_PRODUCT_ALIASES: dict[str, list[str]] = {
    # Electronics
    "televisions": ["television", "televisions", "tvs"],
    "computer_monitors": ["monitor", "monitors", "computer monitor"],
    "desktop_computers": ["desktop", "desktops", "desktop computer"],
    "laptops": ["laptop", "laptops", "notebook computer"],
    "tablets": ["tablet", "tablets"],
    "phones": ["phone", "phones", "smartphone", "smartphones", "cell phone", "cellphone", "mobile phone"],
    "printers": ["printer", "printers"],
    "computer_peripherals": ["keyboard", "keyboards", "peripheral", "peripherals"],
    "e_readers": ["e-reader", "e-readers", "ereader", "kindle"],
    "cameras": ["camera", "cameras"],
    "media_players": ["media player", "audio player", "headphones", "earbuds"],
    "wearables": ["wearable", "wearables", "smartwatch", "smartwatches", "fitness tracker"],
    "game_consoles": ["game console", "game consoles", "gaming console"],
    "streaming_devices": ["streaming device", "set-top box", "set top box"],
    "large_appliances": ["large appliance", "large appliances", "refrigerator", "washing machine",
                         "white goods", "major appliance"],
    "small_appliances": ["small appliance", "small appliances", "microwave", "toaster"],
    "medical_devices": ["medical device", "medical devices", "medical equipment"],
    "mobility_devices": ["mobility device", "mobility devices", "wheelchair", "wheelchairs"],
    "ag_industrial_equipment": ["agricultural equipment", "farm equipment", "tractor", "tractors"],
    # Batteries
    "rechargeable_portable": ["rechargeable battery", "rechargeable batteries", "portable battery",
                              "portable batteries"],
    "single_use_primary": ["single-use battery", "primary battery", "disposable battery", "alkaline battery"],
    "embedded_batteries": ["embedded battery", "embedded batteries", "built-in battery"],
    "ev_propulsion": ["ev battery", "ev batteries", "electric vehicle battery", "propulsion battery",
                      "traction battery"],
    "large_format_stationary": ["stationary battery", "energy storage", "grid storage",
                                "large-format battery", "storage battery"],
    "lead_acid": ["lead-acid", "lead acid", "car battery", "automotive battery"],
    # Textiles
    "clothing": ["clothing", "clothes", "apparel", "garment", "garments"],
    "footwear": ["footwear", "shoe", "shoes", "sneakers"],
    "home_textiles": ["home textile", "home textiles", "linen", "linens", "bedding", "towels",
                      "household textile"],
    "fashion_accessories": ["fashion accessory", "fashion accessories", "handbag", "handbags"],
    "industrial_textiles": ["industrial textile", "industrial textiles", "workwear", "uniforms"],
}


def _match_products(question: str, stripped: str) -> tuple[list[str], list[str], str]:
    """Scan for specific product mentions → bill_product_coverage.product_slug (longest alias first
    so 'electric vehicle battery' beats 'battery')."""
    lower_q = f" {question.lower()} "
    slugs: list[str] = []
    pairs = sorted(
        [(a, slug) for slug, aliases in _PRODUCT_ALIASES.items() for a in aliases],
        key=lambda p: -len(p[0]))
    for alias, slug in pairs:
        if len(alias) < 3:
            continue
        pat = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
        if pat.search(lower_q) and slug not in slugs:
            slugs.append(slug)
            stripped = pat.sub(" ", stripped)
    labels = sorted({s.replace("_", " ") for s in slugs})
    return slugs, labels, stripped


def _match_materials(question: str, stripped: str) -> tuple[list[str], list[str], str]:
    """Scan for material/product mentions → canonical slugs (+ group expansion). Returns
    (slugs, labels, stripped_text_with_material_words_removed)."""
    lower_q = f" {question.lower()} "
    slugs: list[str] = []
    # (alias, slug) longest-first so "plastic packaging" wins over "plastic".
    pairs = sorted(
        ([(a, slug) for slug, aliases in _MATERIAL_ALIASES.items() for a in aliases]
         + [(g, g) for g in _MATERIAL_GROUPS]),
        key=lambda p: -len(p[0]))
    for alias, target in pairs:
        if len(alias) < 3:
            continue
        pat = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
        if pat.search(lower_q):
            members = _MATERIAL_GROUPS.get(target, [target])
            for s in members:
                if s not in slugs:
                    slugs.append(s)
            stripped = pat.sub(" ", stripped)
    labels = sorted({_MATERIAL_LABELS.get(s, s.replace("_", " ")) for s in slugs})
    return slugs, labels, stripped


def _match_instruments(question: str, stripped: str) -> tuple[list[str], list[str], str]:
    """Scan for instrument mentions (EPR, right-to-repair, deposit-return) → instrument_type slugs."""
    lower_q = f" {question.lower()} "
    slugs: list[str] = []
    pairs = sorted(
        [(a, slug) for slug, aliases in _INSTRUMENT_ALIASES.items() for a in aliases],
        key=lambda p: -len(p[0]))
    for alias, slug in pairs:
        pat = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
        if pat.search(lower_q) and slug not in slugs:
            slugs.append(slug)
            stripped = pat.sub(" ", stripped)
    labels = sorted({_INSTRUMENT_LABELS.get(s, s.replace("_", " ")) for s in slugs})
    return slugs, labels, stripped


@dataclass
class Facets:
    """Resolved structured interpretation of a question."""
    place_ids: list[int]      # subtree-expanded jurisdiction ids ([] = no geographic filter)
    place_labels: list[str]   # display names of the matched nodes ("France", "United States")
    reference_labels: list[str]  # places named only as a reference subject (expansion cue → not a filter)
    material_slugs: list[str]  # canonical material_categories slugs to filter on ([] = no material filter)
    material_labels: list[str]  # display names ("tires", "electronics")
    instrument_slugs: list[str]  # instrument_type slugs to filter on (epr, right_to_repair, …)
    instrument_labels: list[str]
    product_slugs: list[str]   # bill_product_coverage.product_slug filters (laptops, ev_propulsion, …)
    product_labels: list[str]
    free_text: str            # the question with matched place/material/instrument/product aliases removed
    raw_question: str

    def meaningful_terms(self) -> list[str]:
        return [w for w in re.findall(r"[a-z0-9]{3,}", self.free_text.lower()) if w not in _STOPWORDS]


async def _load_nodes(db: AsyncSession):
    return (await db.execute(
        select(Jurisdiction.id, Jurisdiction.name, Jurisdiction.path, Jurisdiction.aliases)
    )).all()


async def resolve_facets(db: AsyncSession, question: str) -> Facets:
    nodes = await _load_nodes(db)
    lower_q = f" {question.lower()} "
    stripped = question
    matched: dict[int, object] = {}  # jurisdiction id -> node row (dedupe)

    for n in nodes:
        for alias in n.aliases:  # stored lowercased
            if len(alias) >= 4:
                pat = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
                if pat.search(lower_q):
                    matched[n.id] = n
                    stripped = pat.sub(" ", stripped)
                    break
            else:
                # 2–3 char codes (US, EU, FR, CA) only match as a standalone UPPERCASE token, so the
                # pronoun "us" or the word "in" can't false-trigger a jurisdiction filter.
                pat = re.compile(r"\b" + re.escape(alias.upper()) + r"\b")
                if pat.search(question):
                    matched[n.id] = n
                    stripped = pat.sub(" ", stripped)
                    break

    place_labels = sorted({n.name for n in matched.values()})
    material_slugs, material_labels, stripped = _match_materials(question, stripped)
    instrument_slugs, instrument_labels, stripped = _match_instruments(question, stripped)
    product_slugs, product_labels, stripped = _match_products(question, stripped)
    free_text = re.sub(r"\s+", " ", stripped).strip()

    common = dict(material_slugs=material_slugs, material_labels=material_labels,
                  instrument_slugs=instrument_slugs, instrument_labels=instrument_labels,
                  product_slugs=product_slugs, product_labels=product_labels,
                  free_text=free_text, raw_question=question)

    # Expansion cue → the named place is a reference subject, not a scope filter: don't restrict by
    # jurisdiction (materials/instruments still apply — "carpet EPR like France's everywhere").
    if matched and any(cue in lower_q for cue in _EXPANSION_CUES):
        return Facets(place_ids=[], place_labels=[], reference_labels=place_labels, **common)

    matched_paths = {n.path for n in matched.values()}
    place_ids = [
        n.id for n in nodes
        if any(n.path == p or n.path.startswith(p + ".") for p in matched_paths)
    ]
    return Facets(place_ids=place_ids, place_labels=place_labels, reference_labels=[], **common)
