"""LLM query-understanding router for the Atlas research engine (A1).

Splits query understanding into two stages:

  1. one cheap Haiku call parses arbitrary phrasing into facet slugs + a per-facet ROLE + a query
     intent, and a residual free_text;
  2. a deterministic binder validates every slug against the canonical vocabulary (the LLM can never
     invent a code) and resolves place *names* against the jurisdiction alias table.

The output degrades to the existing `Facets` contract (filter-role facets only) via `to_facets()`, so
`_scope_extra` / `_relevant_bills` are unchanged — this can run in shadow mode first.

Why an LLM here at all: the deterministic resolver (research_facets.py) already nails slug extraction,
places, and reference-role (measured against tests/eval/router_golden.json). Its two irreducible gaps
are (1) illustrative-vs-filter -- "EPR bills on electronics like phones" -> `phones` is an *example* of
the electronics filter, not a narrower filter -- and (2) intent (lookup/list/compare/count). This router
adds exactly those, and generalizes past the alias tables ("repairability" -> right_to_repair).
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classification.materials import CANONICAL_MATERIALS
from app.config import settings
from app.models import Jurisdiction
from app.synthesis.product_taxonomy import SLUGS as PRODUCT_SLUGS, vocab_block
from app.api.research_facets import Facets

HAIKU_MODEL = "claude-haiku-4-5-20251001"

# --- canonical vocabularies the binder validates against (LLM output is checked, never trusted) ----
MATERIAL_SLUGS: tuple[str, ...] = tuple(sorted(CANONICAL_MATERIALS - {"other"}))
# instrument_type values that actually carry a meaningful, filterable set in the corpus.
INSTRUMENT_SLUGS: tuple[str, ...] = (
    "epr", "right_to_repair", "deposit_return", "incentives", "labeling",
    "recycled_content", "preemption", "chemical_restriction", "product_stewardship",
)
# compliance-detail envelopes (mirror app/api/research.py _DIM_TRIGGERS keys). The last four are new
# (2026-07-13) and routable now; their compliance_details envelopes are not yet extracted, so retrieval
# degrades gracefully until the extraction re-run (see docs/DIMENSION_EXPANSION_PLAN.md).
DIMENSION_KEYS: tuple[str, ...] = (
    "eco_modulation", "recycled_content", "collection_targets", "pro_structure",
    "labeling", "penalties", "fee_amounts", "bans_restrictions",
    "repairability", "reuse_refill", "digital_product_passport", "remanufacturing",
)
INTENTS: tuple[str, ...] = ("lookup", "list", "compare", "count")


def _menu(slugs) -> str:
    return ", ".join(slugs)


ROUTE_TOOL = {
    "name": "route_query",
    "description": "Return the structured facet interpretation of the user's question. Do not answer "
                   "the question; only extract structure using the allowed vocabularies.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": list(INTENTS)},
            "places": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "place name as written (France, California, EU)"},
                        "role": {"type": "string", "enum": ["filter", "reference", "exclude"]},
                    },
                    "required": ["name", "role"],
                },
            },
            "materials": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "an exact material slug from the menu"},
                        "role": {"type": "string", "enum": ["filter", "illustration"]},
                    },
                    "required": ["slug", "role"],
                },
            },
            "instruments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "an exact instrument slug from the menu"},
                        "role": {"type": "string", "enum": ["filter", "illustration"]},
                    },
                    "required": ["slug", "role"],
                },
            },
            "products": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "an exact product slug from the menu"},
                        "role": {"type": "string", "enum": ["filter", "illustration"]},
                    },
                    "required": ["slug", "role"],
                },
            },
            "dimensions": {
                "type": "array",
                "items": {"type": "string", "description": "an exact dimension key from the menu"},
            },
            "free_text": {
                "type": "string",
                "description": "residual distinctive words to full-text search (law names, substances, "
                               "topics not in any menu); empty if nothing substantive remains",
            },
        },
        "required": ["intent", "places", "materials", "instruments", "products", "dimensions", "free_text"],
    },
}


SYSTEM = f"""You convert a user's natural-language question about circular-economy / EPR legislation \
into structured database facets by calling route_query. You do NOT answer the question — you only \
extract structure.

Hard rules:
- Emit ONLY slugs that appear verbatim in the menus below. If a concept is not in a menu, do NOT invent \
a slug — leave those words in free_text.
- Emit place NAMES as the user wrote them (France, California, EU), never codes.

Roles (materials / instruments / products): each is either
- "filter": the user wants results restricted to it, OR
- "illustration": it is only an EXAMPLE clarifying a broader filter, not a restriction itself.
  Decisive example: "EPR bills on electronics like phones and laptops" -> material electronics = filter; \
products phones, laptops = ILLUSTRATION (they illustrate 'electronics'; they are not the filter). \
Contrast: "which bills cover laptops?" -> product laptops = FILTER. The words "like", "such as", \
"e.g.", "including", "for example" almost always introduce illustrations.

Roles (places): "filter" restricts to that jurisdiction; "reference" means it is named only as a \
comparison subject, not a scope ("laws comparable to France's AGEC across all regions" -> France = \
reference); "exclude" means explicitly excluded ("everywhere except California" -> California = exclude).

intent: "lookup" (find a specific named law), "list" (enumerate matching bills), "compare" (contrast \
jurisdictions/approaches), "count" (how many).

materials vs products: materials are broad streams (electronics, textiles, batteries); products are \
specific catalog items (laptops, footwear, ev_propulsion). A product mention is often an illustration \
of its material.

packaging: when the user says "packaging" generically (not one specific type), emit ALL FOUR packaging \
materials with the same role: plastic_packaging, paper_packaging, glass, metals. Only narrow to one when \
the user specifies it ("plastic packaging", "cardboard").

recycled_content and labeling exist as BOTH an instrument and a dimension: use the DIMENSION when the \
question is about the requirement/rule ("recycled content mandate", "labeling requirement"); use the \
instrument only when naming the policy type in the abstract. For requirement phrasings, prefer these \
dimensions: take-back / collection / recovery targets -> collection_targets; bans / prohibitions / \
phase-outs -> bans_restrictions; penalties / fines -> penalties; disposal/eco-fees or fee schedules -> \
fee_amounts; eco-modulation / bonus-malus -> eco_modulation; PRO / stewardship-org structure -> pro_structure; \
repair index / repairability or durability score / parts & manuals availability / planned obsolescence / \
design-for-repair -> repairability; reuse mandate or target / refillable or returnable packaging / refill \
infrastructure -> reuse_refill; digital product passport / product traceability / lifecycle-data or \
material-composition disclosure -> digital_product_passport; remanufacturing / refurbishment standard / \
industrial symbiosis -> remanufacturing.

instruments vs dimensions: an instrument is the KIND of policy mechanism (epr, deposit_return, \
right_to_repair, incentives, ...). A dimension is a specific compliance ENVELOPE a question zooms into \
(eco_modulation, collection_targets, penalties, fee_amounts, pro_structure, bans_restrictions, ...). \
Prefer instrument for the noun form ("EPR", "deposit return"); prefer dimension for the requirement \
form ("recycled content rules", "penalties", "take-back targets"). You may infer a slug from a synonym \
not spelled out (e.g. "repairability" -> right_to_repair, "bottle bill" -> deposit_return).

free_text: the residual distinctive words after removing filler ("bills", "laws", "records", "show me") \
and everything captured as a facet (including place names). NEVER repeat a word in free_text that you \
captured as a facet — if "e-waste" became material electronics, drop "e-waste"; if "packaging" became \
the packaging materials, drop "packaging". Keep law names (AGEC), substances (PFAS), and topics not in \
any menu; leave free_text empty if nothing distinctive remains.

MENUS
materials: {_menu(MATERIAL_SLUGS)}
instruments: {_menu(INSTRUMENT_SLUGS)}
dimensions: {_menu(DIMENSION_KEYS)}
products:
{vocab_block("electronics")}
{vocab_block("batteries")}
{vocab_block("textiles")}
"""


@dataclass
class RoutedFacets:
    """Router output, role-aware. Filter-role slugs drive retrieval; illustrations are kept separate
    (for ranking/display, never as hard AND filters)."""
    intent: str
    place_ids: list[int] = field(default_factory=list)
    place_labels: list[str] = field(default_factory=list)
    reference_labels: list[str] = field(default_factory=list)
    exclude_place_ids: list[int] = field(default_factory=list)
    exclude_place_labels: list[str] = field(default_factory=list)
    material_slugs: list[str] = field(default_factory=list)
    material_illustrations: list[str] = field(default_factory=list)
    instrument_slugs: list[str] = field(default_factory=list)
    instrument_illustrations: list[str] = field(default_factory=list)
    product_slugs: list[str] = field(default_factory=list)
    product_illustrations: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    free_text: str = ""
    raw_question: str = ""
    interpretation: dict = field(default_factory=dict)  # raw validated LLM output, for display/debug

    def to_facets(self) -> Facets:
        """Degrade to the existing deterministic Facets contract: FILTER-role facets only, so
        _scope_extra / _relevant_bills behave exactly as today (illustrations never become AND
        filters). Shadow-mode adapter."""
        return Facets(
            place_ids=self.place_ids, place_labels=self.place_labels,
            reference_labels=self.reference_labels,
            material_slugs=self.material_slugs,
            material_labels=[s.replace("_", " ") for s in self.material_slugs],
            instrument_slugs=self.instrument_slugs,
            instrument_labels=[s.replace("_", " ") for s in self.instrument_slugs],
            product_slugs=self.product_slugs,
            product_labels=sorted({s.replace("_", " ") for s in self.product_slugs}),
            free_text=self.free_text, raw_question=self.raw_question,
        )


def _split_by_role(items, valid: set, roles=("filter", "illustration")):
    """Validate slugs against `valid`, split into (filter_slugs, illustration_slugs). Invalid slugs
    are dropped (the LLM was told to leave unknowns in free_text)."""
    keep = {r: [] for r in roles}
    for it in items or []:
        slug = (it or {}).get("slug")
        role = (it or {}).get("role", "filter")
        if slug in valid and role in keep and slug not in keep[role]:
            keep[role].append(slug)
    return keep[roles[0]], keep[roles[1]]


def _subtree_ids(nodes, matched_paths: set) -> list[int]:
    return [n.id for n in nodes
            if any(n.path == p or n.path.startswith(p + ".") for p in matched_paths)]


def _match_place(nodes, name: str):
    """All jurisdiction nodes matching an emitted place name (by name or alias, case-insensitive).
    Returns >1 for genuinely ambiguous names (e.g. Georgia = US state + country)."""
    t = name.strip().lower()
    return [n for n in nodes if n.name.lower() == t or t in {a.lower() for a in (n.aliases or [])}]


async def _bind(db: AsyncSession, data: dict, question: str) -> RoutedFacets:
    nodes = (await db.execute(
        select(Jurisdiction.id, Jurisdiction.name, Jurisdiction.path, Jurisdiction.aliases))).all()

    filt_paths, ref_labels, excl_paths, filt_labels, excl_labels = set(), [], set(), [], []
    for p in data.get("places", []):
        matches = _match_place(nodes, (p or {}).get("name", ""))
        if not matches:
            continue
        role = (p or {}).get("role", "filter")
        if role == "reference":
            ref_labels += [n.name for n in matches]
        elif role == "exclude":
            excl_paths |= {n.path for n in matches}
            excl_labels += [n.name for n in matches]
        else:
            filt_paths |= {n.path for n in matches}
            filt_labels += [n.name for n in matches]

    mat_f, mat_i = _split_by_role(data.get("materials"), set(MATERIAL_SLUGS))
    ins_f, ins_i = _split_by_role(data.get("instruments"), set(INSTRUMENT_SLUGS))
    prd_f, prd_i = _split_by_role(data.get("products"), set(PRODUCT_SLUGS))
    dims = [d for d in data.get("dimensions", []) if d in DIMENSION_KEYS]
    intent = data.get("intent") if data.get("intent") in INTENTS else "list"

    return RoutedFacets(
        intent=intent,
        place_ids=_subtree_ids(nodes, filt_paths), place_labels=sorted(set(filt_labels)),
        reference_labels=sorted(set(ref_labels)),
        exclude_place_ids=_subtree_ids(nodes, excl_paths), exclude_place_labels=sorted(set(excl_labels)),
        material_slugs=mat_f, material_illustrations=mat_i,
        instrument_slugs=ins_f, instrument_illustrations=ins_i,
        product_slugs=prd_f, product_illustrations=prd_i,
        dimensions=dims, free_text=(data.get("free_text") or "").strip(), raw_question=question,
        interpretation=data,
    )


def _cache_key(question: str) -> str:
    """Normalize whitespace so trivially-different spacings share a cache slot. Case is preserved —
    the LLM (and downstream uppercase-code place match) can be case-sensitive."""
    return " ".join(question.split())


class QueryRouter:
    """Routes a question to facets via one Haiku call, with a per-question parse cache.

    The cache is the fix for two things: (1) temperature=0 is NOT fully deterministic, so re-routing the
    same question (e.g. paging re-resolves the active ask) could otherwise return a different parse and
    shift the result set between pages — the cache guarantees identical questions get identical facets
    within this instance; (2) it halves cost for repeated asks/paging. NOTE: this is per-process. For
    paging stability ACROSS Cloud Run replicas, /research/ask should also persist the resolved facets in
    research_turn.facets (migration 037) and let /research/bills read those instead of re-routing.
    """

    def __init__(self, client: anthropic.AsyncAnthropic | None = None, cache_size: int = 512):
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=60.0, max_retries=2)
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._inflight: dict[str, asyncio.Future] = {}
        self._cache_size = cache_size
        self.hits = 0
        self.misses = 0

    async def _call(self, question: str) -> dict:
        """The Haiku call: forced tool-use returns the validated-shape (but unbound) facet dict."""
        resp = await self._client.messages.create(
            model=HAIKU_MODEL, max_tokens=800, temperature=0,
            tools=[ROUTE_TOOL], tool_choice={"type": "tool", "name": "route_query"},
            system=SYSTEM, messages=[{"role": "user", "content": question}],
        )
        block = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        return dict(block.input) if block else {}

    async def route_raw(self, question: str, use_cache: bool = True) -> dict:
        key = _cache_key(question)
        if use_cache and key in self._cache:
            self._cache.move_to_end(key)
            self.hits += 1
            return self._cache[key]
        # Collapse a burst of identical in-flight questions onto one API call (no await between the
        # membership check and the future insert, so this is race-free under asyncio).
        if use_cache and key in self._inflight:
            self.hits += 1
            return await self._inflight[key]
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        if use_cache:
            self._inflight[key] = fut
        self.misses += 1
        try:
            data = await self._call(question)
        except Exception as e:
            if not fut.done():
                fut.set_exception(e)
            raise
        finally:
            self._inflight.pop(key, None)
        if use_cache:
            self._cache[key] = data
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        if not fut.done():
            fut.set_result(data)
        return data

    async def route(self, db: AsyncSession, question: str, use_cache: bool = True) -> RoutedFacets:
        return await _bind(db, await self.route_raw(question, use_cache=use_cache), question)
