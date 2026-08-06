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
from dataclasses import dataclass, field

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
    # Query-framing NOUNS — "what does the corpus have on the TOPIC of remanufacturing?" / "any
    # REFERENCES to X across the WHOLE CORPUS". These describe the question, not the subject, but survived
    # the filter and got AND-ed into websearch_to_tsquery, where each one intersects the real topic word:
    # 'whole' & 'topic' & 'remanufactur' matched only 3 bills (vs 69 for the topic alone), collapsing the
    # answer purely on phrasing. Stripping them keeps the tsquery on the actual subject.
    "topic", "topics", "whole", "reference", "references", "corpus", "corpora", "overall", "generally",
    "across", "throughout", "within",  # "ACROSS the corpus / regions" — framing preposition, never a subject
    # Comparative-framing chrome — "what can the rest of the regions LEARN from the US bills?". With a
    # place scoped, these survived into the tsquery and AND-poisoned Rule 1: US (8443 bills) had 8 that
    # happened to contain rest+regions+learn, starving the answer to 8, while foreign regions' non-
    # English text matched none and correctly fell through to the full-region listing. "region(s)" is
    # chrome in a jurisdiction tool; the topical "across/other regions" senses are handled by
    # _EVERYWHERE_CUES / _COMPARISON_CUES above, not here.
    "learn", "learns", "learned", "teach", "teaches", "lesson", "lessons", "rest", "others",
    "region", "regions", "regional", "jurisdiction", "jurisdictions",
    # Market-entry chrome — the way a CUSTOMER phrases the core question ("we plan to SELL shoes in the
    # EU and US MARKETS next year, what OBLIGATIONS do we have and what will our estimated COSTS be?").
    # These are business framing, not statute vocabulary, so AND-ing them into the tsquery intersects a
    # correctly-faceted scope down to near-nothing: that exact question resolved places + the footwear
    # product properly and then collapsed to 3 bills out of 18 in scope. Stripping them lets a
    # well-faceted market-access ask fall through to the scope listing, which is the honest answer set.
    # Dimension routing is unaffected — _map_dimension reads the raw question, not these terms.
    "sell", "sells", "selling", "sold", "market", "markets", "marketplace", "plan", "plans", "planning",
    "obligation", "obligations", "requirement", "requirements", "cost", "costs", "estimate",
    "estimated", "estimates", "next", "year", "years", "we", "our", "company", "business",
    "will", "would", "should", "need", "needs", "want", "wants",  # modals — never statute vocabulary
})


# Two kinds of "the named place isn't a hard filter" cue, which behave DIFFERENTLY for retrieval:
#
# _EVERYWHERE_CUES — a genuine "search the whole corpus" instruction. The named place is a pure
#   benchmark; retrieval must NOT scope to it ("comparable laws to France's AGEC across all regions"
#   → search everywhere, France is just the example).
#
# _COMPARISON_CUES — comparison/"learn from" framing ("how does California compare to other states?",
#   "what can other regions learn from Germany"). Here the named place is the SUBJECT of the comparison,
#   so it is still the retrieval ANCHOR — we scope to it (its bills are the evidence) but LABEL it a
#   reference for narration. Demoting it to no-scope (the old behavior) left the country name to poison a
#   free-text AND-match — fatal for a real comparison ("Germany vs China" retrieved neither corpus).
_EVERYWHERE_CUES = (
    "all regions", "all jurisdictions", "all countries", "every region", "every country",
    "whole corpus", "entire corpus", "across the corpus", "in the corpus", "the corpus",
    "across regions", "across jurisdictions",
    "globally", "worldwide", "world wide", "everywhere", "anywhere else", "elsewhere",
)
_COMPARISON_CUES = (
    "other regions", "other jurisdictions", "other countries", "other states",
    "compared to other", "comparable", "similar to", "similar law", "similar mechanism", "counterpart",
)

# _CONTRAST_CUES — the named place is a FOIL, not the target: the question asks what exists BEYOND it,
# or what it LACKS. "Which foreign countries have laws with no US analog?", "materials underrepresented
# in the US", "what are we missing domestically". Left to Rule 4 (plain filter) these silently returned
# 100% US bills on questions explicitly about foreign law — the dominant cause of the US/EU citation
# skew (confirmed by the funnel probe: 4/5 global asks scoped to United States → 0 foreign reads).
# Directionality matters: "US law with no FOREIGN analog" wants US bills, so cues are US-foil-directional
# (they encode that the US is what we're looking PAST), not generic negations. High-precision on purpose
# — the LLM router is the recall backstop; a missed contrast just falls back to today's behavior.
_CONTRAST_CUES = (
    "foreign countr", "foreign law", "foreign jurisdiction", "foreign nation",
    "other than the us", "outside the us", "outside the united states", "beyond the us",
    "non-us ", "non us ",
    "no us analog", "no us analogue", "no us equivalent", "no us counterpart",
    "no analog in the us", "no equivalent in the us", "without a us",
    "underrepresented in us", "under-represented in us", "underrepresented in the us",
    "under-represented in the us", "missing domestically", "missing in the us", "lacking in the us",
    "what are we missing", "we are missing", "we're missing",
    "exclusively in foreign", "only in foreign", "absent in the us", "absent from the us",
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
    "disposal_ban": ["disposal ban", "landfill ban", "disposal prohibition", "landfill prohibition",
                     "waste disposal ban"],
    "organics_diversion": ["organics diversion", "organic waste diversion", "food waste diversion",
                           "organics recycling", "mandatory composting", "organic waste ban"],
}
_INSTRUMENT_LABELS: dict[str, str] = {
    "epr": "EPR", "right_to_repair": "right to repair", "deposit_return": "deposit return",
    "disposal_ban": "disposal ban", "organics_diversion": "organics diversion",
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


# Natural-language → circular-economy CYCLE wing (see app/classification/cycles.py). "biological
# cycle" / "technical (artificial) cycle" is the butterfly-diagram split; it resolves to a wing slug
# that _scope_extra expands to the wing's inclusive material set. Kept to unambiguous multiword cues.
_CYCLE_ALIASES: dict[str, list[str]] = {
    "biological": ["biological cycle", "biological loop", "biological wing", "biosphere"],
    "technical": ["technical cycle", "technical loop", "technical wing", "technosphere",
                  "artificial cycle", "artificial loop"],
}
_CYCLE_LABELS: dict[str, str] = {"biological": "biological cycle", "technical": "technical cycle"}


def _match_cycles(question: str, stripped: str) -> tuple[list[str], list[str], str]:
    """Scan for cycle-wing mentions ("biological cycle", "technical/artificial cycle") → wing slugs."""
    lower_q = f" {question.lower()} "
    slugs: list[str] = []
    pairs = sorted(
        [(a, slug) for slug, aliases in _CYCLE_ALIASES.items() for a in aliases],
        key=lambda p: -len(p[0]))
    for alias, slug in pairs:
        pat = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
        if pat.search(lower_q) and slug not in slugs:
            slugs.append(slug)
            stripped = pat.sub(" ", stripped)
    labels = sorted({_CYCLE_LABELS[s] for s in slugs})
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
    # Derived circular-economy wing filter (biological/technical). Defaulted so other Facets
    # constructors (e.g. the shadow router) keep working without supplying it.
    cycle_slugs: list[str] = field(default_factory=list)   # "biological" / "technical"
    cycle_labels: list[str] = field(default_factory=list)
    # Blocs whose member states were pulled into place_ids ("European Union"). Narration input only —
    # it tells synthesis the scope spans a framework tier and a transposition tier. See expand_place_ids.
    bloc_expansions: list[str] = field(default_factory=list)
    # Jurisdictions that are in scope only as COMPARATORS ("...compare to the EU and US"). A subset of
    # place_ids, used to down-weight them in the interleave so the subjects keep the bulk of the read
    # set. Empty for an ordinary multi-place comparison, where every named place is a subject.
    secondary_place_ids: list[int] = field(default_factory=list)

    def meaningful_terms(self) -> list[str]:
        return [w for w in re.findall(r"[a-z0-9]{3,}", self.free_text.lower()) if w not in _STOPWORDS]


# Blocs whose named scope is a MARKET, not just the bloc's own acts. The EU sits at `world.eu` with no
# children — France is `world.fr`, a SIBLING — so subtree expansion alone resolves "the EU" to EU-level
# acts and nothing else. That is wrong for the question producers actually ask: a directive binds member
# states, and the obligation that lands on a company placing goods on the market is the national
# transposition. On prod that gap is the difference between 3 footwear bills and 18 (France alone carries
# 11), and 218 vs 535 corpus-wide. Membership is a stable published fact, so it lives in code rather than
# a migration; the member nodes stay separate jurisdictions, so rollups and ranks are unaffected — the
# expansion widens RETRIEVAL only, and synthesis presents the two tiers separately (see _DEEP_SYSTEM).
_BLOC_MEMBERS: dict[str, frozenset[str]] = {
    "EU": frozenset({"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
                     "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}),
}


async def _load_nodes(db: AsyncSession):
    return (await db.execute(
        select(Jurisdiction.id, Jurisdiction.name, Jurisdiction.path, Jurisdiction.aliases,
               Jurisdiction.code, Jurisdiction.level)
    )).all()


def expand_place_ids(nodes, matched_paths: set, expand_blocs: bool = True) -> tuple[list[int], list[str]]:
    """Jurisdiction ids for a set of matched paths: the usual path-subtree expansion, PLUS member states
    for any matched bloc (see _BLOC_MEMBERS). Returns (ids, expanded_bloc_names) — the second element is
    narration input so the answer can say the scope covers the bloc and its members, and stays empty when
    nothing was expanded. Shared by the deterministic resolver and the LLM router so both scope alike."""
    ids = {n.id for n in nodes
           if any(n.path == p or n.path.startswith(p + ".") for p in matched_paths)}
    expanded: list[str] = []
    # `expand_blocs=False` is for places the question merely COMPARES AGAINST rather than scopes to.
    # "How does China compare to the EU?" means the EU's own acts; expanding it to 27 member states there
    # turns a 5-way comparison into a 23-country round-robin that starves the actual subjects (measured:
    # China dropped to 5 bills and Japan to 4 out of a 100-bill read set).
    for bloc in ([n for n in nodes if (n.code or "") in _BLOC_MEMBERS and n.path in matched_paths]
                 if expand_blocs else []):
        members = _BLOC_MEMBERS[bloc.code]
        member_nodes = [n for n in nodes if (n.code or "") in members]
        if member_nodes:
            expanded.append(bloc.name)
            for m in member_nodes:
                ids.update(n.id for n in nodes
                           if n.path == m.path or n.path.startswith(m.path + "."))
    return sorted(ids), expanded


def _is_us_place(node) -> bool:
    """True for the US (national node or any US state) — the foil in a US-centric contrast question.
    The country is the 2nd path segment ('world.us' / 'world.us.us_ca' -> 'us', 'world.fr' -> 'fr'),
    matching split_part(path,'.',2) used in research.py's country rollups."""
    parts = (node.path or "").split(".")
    return len(parts) >= 2 and parts[1] == "us"


async def resolve_facets(db: AsyncSession, question: str) -> Facets:
    nodes = await _load_nodes(db)
    lower_q = f" {question.lower()} "
    stripped = question
    matched: dict[int, object] = {}  # jurisdiction id -> node row (dedupe)

    for n in nodes:
        # The WORLD root is never a place FILTER. Its subtree is every jurisdiction, so scoping to it is a
        # no-op at best — and actively harmful when unioned with a real anchor: "what can China teach the
        # rest of the world?" matched World via its 'world' alias, dissolved China's scope into the whole
        # corpus, and returned EU/US/AU/KE bills and not one Chinese bill. The genuine "search everywhere"
        # sense is already carried by _EVERYWHERE_CUES, which doesn't need a node to filter on.
        if (n.level or "") == "world":
            continue
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
    cycle_slugs, cycle_labels, stripped = _match_cycles(question, stripped)
    product_slugs, product_labels, stripped = _match_products(question, stripped)
    free_text = re.sub(r"\s+", " ", stripped).strip()

    common = dict(material_slugs=material_slugs, material_labels=material_labels,
                  instrument_slugs=instrument_slugs, instrument_labels=instrument_labels,
                  cycle_slugs=cycle_slugs, cycle_labels=cycle_labels,
                  product_slugs=product_slugs, product_labels=product_labels,
                  free_text=free_text, raw_question=question)

    matched_paths = {n.path for n in matched.values()}
    place_ids, bloc_expansions = expand_place_ids(nodes, matched_paths)
    common["bloc_expansions"] = bloc_expansions

    # 1) Explicit "search everywhere" + a named place → the place is a pure benchmark, don't scope by
    #    jurisdiction (materials/instruments still apply — "carpet EPR like France's everywhere").
    if matched and any(cue in lower_q for cue in _EVERYWHERE_CUES):
        return Facets(place_ids=[], place_labels=[], reference_labels=place_labels, **common)

    # 1.5) Contrastive / exclusion framing where a DOMESTIC place (the US) is a FOIL, not the target:
    #    "foreign countries with no US analog", "materials underrepresented in the US", "what are we
    #    missing domestically". Plain-filtered (Rule 4) these silently returned 100% US bills on questions
    #    explicitly about foreign law — the dominant driver of the US/EU skew. Demote the US foil to a
    #    reference; keep any OTHER named place as the anchor, else go corpus-wide (which also re-enables the
    #    region-balanced read, since nothing is geo-scoped). Guarded on a US foil actually being named, so a
    #    stray "foreign countries" cue alongside a non-US anchor ("France vs foreign countries") falls
    #    through to normal handling instead of wrongly unscoping.
    if matched and any(cue in lower_q for cue in _CONTRAST_CUES):
        foils = sorted({n.name for n in matched.values() if _is_us_place(n)})
        if foils:
            anchors = [n for n in matched.values() if not _is_us_place(n)]
            if anchors:
                anchor_paths = {n.path for n in anchors}
                anchor_ids, anchor_blocs = expand_place_ids(nodes, anchor_paths)
                return Facets(place_ids=anchor_ids, place_labels=sorted({n.name for n in anchors}),
                              reference_labels=foils, **{**common, "bloc_expansions": anchor_blocs})
            return Facets(place_ids=[], place_labels=[], reference_labels=place_labels, **common)

    # 2) Two or more named places → a head-to-head comparison ("Germany vs China"): scope to ALL of them
    #    as filters so retrieval returns each corpus (interleaved), instead of a free-text match on bills
    #    that merely mention the names.
    if len(matched) >= 2:
        return Facets(place_ids=place_ids, place_labels=place_labels, reference_labels=[], **common)

    # 3) A single named place under a comparison / "learn from" cue → still the retrieval ANCHOR (scope to
    #    it) but LABELED a reference for narration. This is the fix for reference→no-scope junk: the old
    #    code cleared scope here, leaving the country name to poison a free-text AND-match.
    if matched and any(cue in lower_q for cue in _COMPARISON_CUES):
        return Facets(place_ids=place_ids, place_labels=[], reference_labels=place_labels, **common)

    # 4) Plain filter (zero or one place, no cue).
    return Facets(place_ids=place_ids, place_labels=place_labels, reference_labels=[], **common)
