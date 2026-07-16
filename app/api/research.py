"""'Ask the Bills' — a deep, retrieval-grounded, cited analysis endpoint over the bill corpus (Pro).

Design (Atlas Circular deep-default mode — see docs/ATLAS_CIRCULAR_ROADMAP.md). SQL COMPUTES, the LLM
SYNTHESIZES. For every question we:
  1. resolve facets (jurisdiction via app/api/research_facets, dimension, free text) → a matched set;
  2. read the FULL-TEXT passages of the top ~50 most-relevant bills (SQL ts_headline, not summaries);
  3. compute exact aggregates, scoped to the facet set plus the corpus-wide baseline;
  4. run ONE Sonnet synthesis over that material → a thorough, cited markdown briefing.
The full matched set also drives a paginated table (GET /research/bills). Numbers come from SQL
(trustworthy), claims are cited to bills the model was actually given (traceable), and the model is
barred from asserting absence when the set is non-empty. Each answer is persisted (research_turns) as
the analysis layer that later becomes the Layer-1 knowledge cache. Batched map-reduce beyond ~50 bills
is the documented scale-up.
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import uuid

import anthropic
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, literal_column, or_, select, true
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.applinks import DASHBOARD_URL, bill_url
from app.api.auth import AuthedUser, require_admin
from app.api.research_facets import resolve_facets
from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models import Bill, BillProductCoverage, BillText, Jurisdiction, LitigationCase
from app.schemas import (
    BillSummary,
    ContentDraftCreate,
    ContentDraftOut,
    ContentDraftPage,
    ContentDraftPatch,
    ResearchAnswer,
    ResearchAskRequest,
    ResearchBillPage,
    ResearchChart,
    ResearchChartBar,
    ResearchCitation,
    ResearchSessionOut,
    ResearchTurnAdminItem,
    ResearchTurnAdminPage,
    ResearchTurnOut,
    SharedCitationOut,
    SharedSessionOut,
    SharedTurnOut,
    ShareOut,
)

router = APIRouter(prefix="/research", tags=["research"])
log = structlog.get_logger()

RESEARCH_MODEL = "claude-sonnet-4-6"
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=90.0, max_retries=1)

DIMENSION_KEYS = [
    "collection_targets", "recycled_content", "eco_modulation", "fee_amounts",
    "penalties", "bans_restrictions", "pro_structure", "labeling",
]


# 'english' as a SQL literal (regconfig), not a bind param — matches app/api/bills.py.
_ENGLISH = literal_column("'english'")
# Plain single-fragment headline for the LLM sample + citation snippets (no <mark>, unlike the
# search UI which does highlight). Only text tiers produce a snippet; the structured tier has none.
_HEADLINE_PLAIN = "MaxFragments=1,MaxWords=30,MinWords=12,StartSel=,StopSel="
# Below this many precise full-text hits we escalate (structured, then OR) rather than answer off a
# near-empty sample. 3 keeps genuinely-matched questions on the precise tier; only near-misses fall.
_MIN_TEXT_HITS = 3
_PAGE_SIZE = 25          # default page of the relevant-bill table
_MAX_PAGE_SIZE = 100     # ceiling per request (paging reaches the whole set across pages)

# Keyword → compliance-dimension map for the structured fallback tier: when precise full-text match
# is thin AND the question is clearly *about* a dimension, the relevant set is that dimension's bills
# (e.g. "compelling incentives" → eco_modulation), which is cleaner than OR-broadening the words.
# First match wins, so order encodes priority. Keys must match the compliance_details JSONB envelope.
_DIM_TRIGGERS: list[tuple[str, tuple[str, ...]]] = [
    # New (2026-07-13) — placed first so specific phrases win over generic "label"/"restrict"; each
    # degrades gracefully until its compliance_details envelope is populated (DIMENSION_EXPANSION_PLAN).
    ("repairability", ("repairability", "repair index", "repair score", "reparability", "durability label",
                       "durability standard", "durability score", "planned obsolescence",
                       "premature obsolescence", "product lifespan", "product lifetime",
                       "design for repair", "design for disassembly")),
    ("reuse_refill", ("reuse mandate", "reuse target", "reuse system", "reusable packaging", "refillable",
                      "refill station", "refill infrastructure", "reuse and refill", "returnable packaging",
                      "packaging reuse")),
    ("digital_product_passport", ("digital product passport", "product passport", "product traceability",
                                  "material traceability", "lifecycle data", "circularity assessment",
                                  "material composition disclosure", "supply chain transparency")),
    ("remanufacturing", ("remanufactur", "refurbishment standard", "refurbished", "industrial symbiosis",
                         "secondary raw material", "by-product synergy")),
    ("eco_modulation", ("eco-modulation", "eco modulation", "modulat", "bonus-malus", "bonus/malus",
                        "incentiv", "reward", "fee discount", "fee reduction")),
    ("recycled_content", ("recycled content", "recycled-content", "post-consumer", "post consumer",
                          "pcr ", "minimum content", "recycled material")),
    ("collection_targets", ("collection target", "recovery target", "recycling rate", "collection rate",
                            "recovery rate", "take-back", "take back", "diversion")),
    ("pro_structure", ("producer responsibility organization", "stewardship organization",
                       "collective scheme", "pro structure", " pro ", "stewardship plan")),
    ("labeling", ("label", "marking", "chasing arrows", "disclosure requirement", "on-pack")),
    ("penalties", ("penalt", "fine", "sanction", "enforcement", "non-compliance", "noncompliance")),
    ("fee_amounts", ("advance disposal fee", "disposal fee", "eco-fee", "levy", "fee amount",
                     "fee schedule", "producer fee")),
    ("bans_restrictions", ("ban ", "bans", "prohibit", "restrict", "phase-out", "phase out",
                           "phaseout")),
]


# Example markers that introduce an ILLUSTRATION ("...like France's repairability index") rather than
# a filter. A dimension keyword that only ever appears right after one of these is clarifying the ask,
# not defining the set — so it must not drive RULE 2.
_EXAMPLE_CUES = ("like ", "such as", "e.g", "eg ", "for example", "for instance", "including ",
                 "similar to", "e.x")


def _map_dimension(question: str) -> tuple[str | None, str | None]:
    """First matching (dimension, trigger-phrase) for the structured fallback, or (None, None)."""
    q = f" {question.lower()} "
    for dim, triggers in _DIM_TRIGGERS:
        for t in triggers:
            if t in q:
                return dim, t
    return None, None


def _trigger_is_illustrative(question: str, trigger: str | None) -> bool:
    """True when EVERY occurrence of the dimension trigger sits just after an example cue — i.e. the
    keyword only appears inside an illustrative aside and shouldn't be read as a filter. One bare
    (non-example) occurrence means it's a genuine topic, so return False and let RULE 2 use it."""
    if not trigger:
        return False
    ql = question.lower()
    idxs = [m.start() for m in re.finditer(re.escape(trigger), ql)]
    if not idxs:
        return False
    return all(any(cue in ql[max(0, i - 40):i] for cue in _EXAMPLE_CUES) for i in idxs)


# A "what are the most unique / unusual / different TYPES of bills" question wants a broad SPREAD across
# the corpus's distinct policy types, not a narrowing filter. Detected here (cheap, deterministic) to
# route to the diversity sampler (RULE 2.5) instead of the dimension fallback, which otherwise latches
# onto whatever dimension word appears (even one inside an example) and collapses the answer to it.
_DIVERSITY_TRIGGERS = (
    "most unique", "unique type", "unique kind", "unique bill", "unique law", "uniqueness",
    "unusual", "outlier", "outliers", "most distinctive", "distinctive", "one-of-a-kind",
    "different types", "different kinds", "different sorts", "what types", "what kinds",
    "range of", "variety of", "diverse", "diversity of", "novel", "uncommon", "most creative",
    "most interesting", "most surprising", "stand out", "standout",
)
# Framing words stripped from the tsquery on a diversity ask (they describe the QUERY, not the subject,
# so they must not AND-poison or junk-rank RULE 1/3) — a diversity-scoped superset of nothing else.
_DIVERSITY_WORDS = frozenset({
    "unique", "uniqueness", "unusual", "outlier", "outliers", "distinctive", "different", "types",
    "type", "kinds", "kind", "sorts", "sort", "variety", "diverse", "diversity", "novel",
    "uncommon", "rare", "most", "range", "creative", "interesting", "surprising", "standout",
})


def _wants_diversity(question: str) -> bool:
    return any(t in question.lower() for t in _DIVERSITY_TRIGGERS)


# A "trend / over time / count-by-year" question wants the year distribution shown as a chart. Cheap
# deterministic trigger (the shadow router's intent=count is Haiku and not yet driving); the bars come
# from the SQL year aggregate, so the numbers are exact — the model never fabricates them.
_YEAR_CHART_TRIGGERS = (
    "over time", "by year", "per year", "each year", "year over year", "year-over-year",
    "trend", "timeline", "time series", "time-series", "chart", "graph", "plot",
    "how many.*introduced", "introduced.*over", "growth", "history of", "historical",
)


def _wants_year_chart(question: str) -> bool:
    q = question.lower()
    return any(re.search(t, q) if "." in t else t in q for t in _YEAR_CHART_TRIGGERS)


def _year_chart(question: str, agg_scoped: dict, scope_labels: list[str]) -> ResearchChart | None:
    """A bills-by-year bar chart from the SCOPED year aggregate, when the question asks for a trend and
    the set spans ≥2 years. Returns None otherwise (the AnswerChart component hides an absent chart)."""
    if not _wants_year_chart(question):
        return None
    by_year = (agg_scoped or {}).get("bills_by_year") or []
    if len({b["year"] for b in by_year}) < 2:
        return None
    bars = [ResearchChartBar(label=str(b["year"]), value=b["count"])
            for b in sorted(by_year, key=lambda b: b["year"])]
    suffix = f" — {', '.join(scope_labels)}" if scope_labels else ""
    return ResearchChart(title=f"Bills by year{suffix}", bars=bars)


def _lit_subquery():
    """Active-litigation counts per bill, so the relevant-bill table's Litigation column populates
    (mirrors app/api/bills.py._lit_subquery — kept local to avoid a cross-module private import)."""
    return (
        select(
            LitigationCase.related_law_id,
            func.count(LitigationCase.id).label("case_count"),
            func.max(LitigationCase.preemption_risk).label("max_risk"),
        )
        .where(LitigationCase.case_status == "active")
        .group_by(LitigationCase.related_law_id)
        .subquery()
    )


def _meta_doc():
    """An English tsvector over a bill's title + AI summary. text_tsv indexes only the (English-only)
    full statute body, so a non-English bill like France's AGEC is unreachable by body text even
    though the Explorer surfaces it by its (English-descriptor) title. Matching this metadata doc too
    lets the same titled bills the Explorer shows appear in Ask the Bills, in any language."""
    return func.to_tsvector(_ENGLISH, func.concat_ws(" ", Bill.title, Bill.ai_summary))


def _match_filter(tsq):
    """A bill is relevant if the query matches its full text OR its title/summary metadata."""
    return or_(BillText.text_tsv.op("@@")(tsq), _meta_doc().op("@@")(tsq))


async def _count_match(db: AsyncSession, tsq, extra=()) -> int:
    # LEFT join: title-only matches (no bill_texts row, or foreign body text) must still count.
    q = (select(func.count(func.distinct(Bill.id)))
         .select_from(Bill)
         .outerjoin(BillText, BillText.bill_id == Bill.id)
         .where(Bill.ce_relevant.is_(True))
         .where(_match_filter(tsq)))
    for c in extra:
        q = q.where(c)
    return (await db.scalar(q)) or 0


async def _relevant_bills(
    db: AsyncSession, question: str, page: int = 1, page_size: int = _PAGE_SIZE, facets=None
) -> tuple[list, int, str]:
    """The FULL set of bills relevant to `question`, one page at a time — (rows, total, strategy),
    deterministic so paging is stable. Facet-hybrid: jurisdiction is resolved from the question
    (app/api/research_facets) into an authoritative filter, so "examples from France" returns FR bills
    by construction — never dependent on the word appearing in (foreign-language) body text. Ordered
    rules, first match wins:
      1. free-text (full text OR title/summary metadata) *within* the resolved scope;
      2. structured-by-dimension — only when NO place was named (a place means "list bills there");
      3. OR-broaden — only when no place was named and free text found nothing precise;
      4. listing — the base set (place-scoped, or the whole corpus) ranked by recency.
    The metadata arm reaches the same titled bills the Explorer shows (incl. non-English laws like
    AGEC). Match rules carry a `snippet` (ts_headline, body text falling back to title); listing/
    dimension rules don't (rows expose it via getattr default). Litigation columns join for the table.
    """
    page = max(1, page)
    page_size = max(1, min(page_size, _MAX_PAGE_SIZE))
    offset = (page - 1) * page_size
    lit = _lit_subquery()

    # facets default to the deterministic resolver; the shadow router passes its own (via to_facets())
    # so the SAME retrieval runs both ways for the results-diff. This param is also the flip point:
    # once the router graduates, /ask passes the router facets here.
    facets = facets or await resolve_facets(db, question)
    geo = facets.place_ids
    scoped = bool(facets.place_ids or facets.material_slugs or facets.instrument_slugs
                  or facets.product_slugs)
    extra = _scope_extra(facets)

    def _cols():
        return (Bill,
                func.coalesce(lit.c.case_count, 0).label("case_count"),
                lit.c.max_risk.label("max_risk"))

    def _place_strategy(base: str) -> str:
        tags = (facets.place_labels + facets.material_labels + facets.instrument_labels
                + facets.product_labels)
        return f"{base}·{','.join(tags)}" if tags else base

    def _match_page(tsq):
        # Rank = best of body-text and title/summary relevance (0 when a bill has no text row, so a
        # title-only match still ranks by its metadata score). Snippet falls back to title.
        text_rank = func.coalesce(func.ts_rank(BillText.text_tsv, tsq), 0.0)
        rank = func.greatest(text_rank, func.ts_rank(_meta_doc(), tsq))
        headline = func.ts_headline(
            _ENGLISH, func.coalesce(BillText.text, Bill.title, ""), tsq, _HEADLINE_PLAIN
        )
        q = (select(*_cols(), headline.label("snippet"))
             .outerjoin(BillText, BillText.bill_id == Bill.id)
             .outerjoin(lit, Bill.id == lit.c.related_law_id)
             .where(Bill.ce_relevant.is_(True))
             .where(_match_filter(tsq)))
        for c in extra:
            q = q.where(c)
        return q.order_by(rank.desc(), Bill.id.desc()).offset(offset).limit(page_size)

    def _plain_page(where_extra, interleave=False):
        q = (select(*_cols())
             .outerjoin(lit, Bill.id == lit.c.related_law_id)
             .where(Bill.ce_relevant.is_(True)))
        for c in list(extra) + list(where_extra):
            q = q.where(c)
        if interleave:
            # Round-robin at the COUNTRY level so a comparison ("France vs US") is balanced on page 1
            # — plain recency buries foreign bills (mostly no status_date), and partitioning by leaf
            # jurisdiction lets the US's 50 state nodes flood France's single node. split_part(path,2)
            # is the country segment ('world.us.us_ca' -> 'us', 'world.fr' -> 'fr').
            country = func.split_part(Jurisdiction.path, ".", 2)
            rn = func.row_number().over(
                partition_by=country,
                order_by=[Bill.status_date.desc().nullslast(), Bill.id.desc()],
            )
            q = q.join(Jurisdiction, Jurisdiction.id == Bill.jurisdiction_id)
            return q.order_by(rn.asc(), country).offset(offset).limit(page_size)
        return q.order_by(Bill.status_date.desc().nullslast(), Bill.id.desc()).offset(offset).limit(page_size)

    def _diversity_page():
        # Spread across the corpus's distinct policy TYPES: round-robin one representative per
        # instrument_type before a second from any (rn), rarest type first (freq asc) so genuine
        # outliers lead. Scoped by `extra` like every other rule. Deterministic (status_date desc, id
        # desc tiebreak) so paging is stable. instrument_type is the primary "kind of policy" axis;
        # material variety rides along because rare instruments (incentives, chemical_restriction)
        # carry the off-beat materials (organics, biobased) the common EPR bulk doesn't.
        itype = func.coalesce(Bill.instrument_type, "other")
        freq = func.count().over(partition_by=itype)
        rn = func.row_number().over(
            partition_by=itype,
            order_by=[Bill.status_date.desc().nullslast(), Bill.id.desc()])
        q = (select(*_cols())
             .outerjoin(lit, Bill.id == lit.c.related_law_id)
             .where(Bill.ce_relevant.is_(True)))
        for c in extra:
            q = q.where(c)
        return q.order_by(rn.asc(), freq.asc(), itype).offset(offset).limit(page_size)

    async def _count_plain(where_extra) -> int:
        q = select(func.count()).select_from(Bill).where(Bill.ce_relevant.is_(True))
        for c in list(extra) + list(where_extra):
            q = q.where(c)
        return (await db.scalar(q)) or 0

    terms = facets.meaningful_terms()
    diversity = _wants_diversity(question)
    # On a diversity ask, drop the framing words ("most unique types") from the tsquery so they can't
    # AND-poison or junk-rank the match — the subject words (if any) still drive RULE 1/3. For a normal
    # question `substantive` == `terms` (no diversity words present), so nothing changes.
    substantive = [t for t in terms if t not in _DIVERSITY_WORDS] if diversity else terms

    # RULE 1 — free-text (text OR title/summary metadata) within the resolved scope. Build the query
    # from stopword-filtered terms so meta-words in the question ("which bills law…", rare in statute
    # text) can't poison the AND-match and drop an otherwise-good hit.
    if substantive:
        tsq = func.websearch_to_tsquery(_ENGLISH, " ".join(substantive))
        n = await _count_match(db, tsq, extra)
        if n > 0:
            rows = (await db.execute(_match_page(tsq))).all()
            return rows, n, _place_strategy("text")

    # RULE 2 — structured-by-dimension, only when the user did NOT scope (place/material means "list
    # what's there"), it is NOT a diversity ask (which wants a spread, not one dimension), and the
    # dimension keyword is a real topic — not merely a word inside an illustrative aside ("...like
    # France's repairability index"), which must never hijack the whole retrieval.
    dim, trig = _map_dimension(question)
    if dim and not scoped and not diversity and not _trigger_is_illustrative(question, trig):
        where_dim = [Bill.compliance_details[dim]["status"].astext == "present"]
        d_total = await _count_plain(where_dim)
        if d_total > 0:
            rows = (await db.execute(_plain_page(where_dim))).all()
            return rows, d_total, f"dimension:{dim}"

    # RULE 2.5 — diversity/outlier spread: "what are the most unique TYPES of bills?" wants a broad
    # sample across the corpus's distinct policy types, not a narrowing filter. Fires even when scoped
    # (e.g. "what's unusual in France" → the spread within France). Falls through to listing if empty.
    if diversity:
        n = await _count_plain([])
        if n > 0:
            rows = (await db.execute(_diversity_page())).all()
            return rows, n, _place_strategy("diversity")

    # RULE 3 — OR-broaden, only when not scoped and free text found nothing precise.
    if substantive and not scoped:
        or_tsq = func.to_tsquery(_ENGLISH, " | ".join(substantive))
        n = await _count_match(db, or_tsq, extra)
        if n > 0:
            rows = (await db.execute(_match_page(or_tsq))).all()
            return rows, n, "text_broad"

    # RULE 4 — listing: the base set (place/material-scoped or whole corpus). Interleave across
    # jurisdictions when comparing 2+ named places so each shows on page 1; otherwise straight recency.
    interleave = len(facets.place_labels) > 1
    n = await _count_plain([])
    rows = (await db.execute(_plain_page([], interleave=interleave))).all() if n else []
    base = ("jurisdiction" if geo else "material" if facets.material_slugs
            else "product" if facets.product_slugs
            else "instrument" if facets.instrument_slugs else "all")
    return rows, n, _place_strategy(base)


def _scope_extra(facets) -> list:
    """The structured scope filters (jurisdiction + material + instrument) shared by retrieval and the
    scoped aggregates, so both apply the same facets. `?|` = the JSONB array overlaps any slug."""
    extra = []
    if facets.place_ids:
        extra.append(Bill.jurisdiction_id.in_(facets.place_ids))
    if facets.material_slugs:
        extra.append(Bill.material_categories.op("?|")(array(facets.material_slugs)))
    if facets.instrument_slugs:
        # Match the primary instrument_type OR the full instrument_types set (mirrors GET /bills).
        extra.append(or_(Bill.instrument_type.in_(facets.instrument_slugs),
                         Bill.instrument_types.op("?|")(array(facets.instrument_slugs))))
    if facets.product_slugs:
        # Bills that actually cover the named product (exclude explicit exemptions).
        covered = (select(BillProductCoverage.bill_id)
                   .where(BillProductCoverage.product_slug.in_(facets.product_slugs))
                   .where(BillProductCoverage.status != "exempt"))
        extra.append(Bill.id.in_(covered))
    return extra


def _row_to_summary(row) -> BillSummary:
    s = BillSummary.model_validate(row.Bill)
    s.litigation_case_count = row.case_count or 0
    s.max_preemption_risk = row.max_risk
    return s


async def _aggregates(db: AsyncSession, extra=()) -> dict:
    """Exact aggregates (ground truth, not LLM). `extra` scopes them to the question's facet set (e.g.
    a jurisdiction), so numbers reflect the question instead of always being whole-corpus. Called with
    no extra for the corpus-wide baseline; a comparison answer gets both ('122 in France of 146 total')."""
    # Collection-target basis distribution (unnest targets; the founding-question axis).
    targets = func.jsonb_array_elements(
        Bill.compliance_details["collection_targets"]["targets"]
    ).table_valued("value").lateral()
    basis = func.jsonb_extract_path_text(targets.c.value, "basis")
    basis_q = (
        select(basis.label("basis"), func.count().label("n"))
        .select_from(Bill)
        .join(targets, true())
        .where(Bill.ce_relevant.is_(True))
        .where(Bill.compliance_details["collection_targets"]["status"].astext == "present")
    )
    for c in extra:
        basis_q = basis_q.where(c)
    basis_rows = (await db.execute(basis_q.group_by(basis).order_by(func.count().desc()))).all()
    # Per-dimension "present" counts in one pass.
    prev_q = select(
        *[func.count().filter(Bill.compliance_details[d]["status"].astext == "present").label(d)
          for d in DIMENSION_KEYS]
    ).where(Bill.ce_relevant.is_(True))
    for c in extra:
        prev_q = prev_q.where(c)
    prevalence_row = (await db.execute(prev_q)).first()
    # Product/material coverage — how many bills cover each material_category. Answers "how many
    # different product types are covered" exactly from SQL instead of guessing from a sample.
    mat = func.jsonb_array_elements_text(Bill.material_categories).table_valued("value").lateral()
    mat_q = (select(mat.c.value.label("material"), func.count().label("n"))
             .select_from(Bill).join(mat, true()).where(Bill.ce_relevant.is_(True)))
    for c in extra:
        mat_q = mat_q.where(c)
    mat_rows = (await db.execute(mat_q.group_by(mat.c.value).order_by(func.count().desc()))).all()
    # Per-PRODUCT coverage (electronics/batteries/textiles only — the extracted subset). Self-gating:
    # included only when the scoped set actually has product rows, so it's silent for unrelated
    # questions (a France query gets no product breakdown) and answers "which bills cover laptops" exactly.
    pc_bill = func.count(func.distinct(BillProductCoverage.bill_id)).label("n")
    pc_q = (select(BillProductCoverage.product_slug.label("product"), pc_bill)
            .join(Bill, Bill.id == BillProductCoverage.bill_id)
            .where(Bill.ce_relevant.is_(True))
            .where(BillProductCoverage.status != "exempt"))
    for c in extra:
        pc_q = pc_q.where(c)
    pc_rows = (await db.execute(pc_q.group_by(BillProductCoverage.product_slug).order_by(pc_bill.desc()))).all()
    # Bills-by-year — the same status_date basis the Insights momentum chart uses (extract year, drop
    # nulls). Foreign law is now dated (scripts/backfill_foreign_dates.py derives a year from CELEX /
    # title), so this is no longer US-only. `undated` is reported alongside so the model can state the
    # coverage honestly ("N of the set carry no date yet") instead of falsely claiming absence — the
    # exact failure that motivated this (a starved sample made it deny corpus-wide year data existed).
    year = func.extract("year", Bill.status_date)
    year_q = (select(year.label("yr"), func.count().label("n"))
              .select_from(Bill).where(Bill.ce_relevant.is_(True))
              .where(Bill.status_date.isnot(None)))
    for c in extra:
        year_q = year_q.where(c)
    year_rows = (await db.execute(year_q.group_by(year).order_by(year))).all()
    undated_q = (select(func.count()).select_from(Bill).where(Bill.ce_relevant.is_(True))
                 .where(Bill.status_date.is_(None)))
    for c in extra:
        undated_q = undated_q.where(c)
    undated = (await db.scalar(undated_q)) or 0
    agg = {
        "collection_target_basis": [{"basis": r.basis or "unspecified", "count": r.n} for r in basis_rows],
        "dimension_prevalence": {d: getattr(prevalence_row, d) for d in DIMENSION_KEYS},
        "material_coverage": [{"material": r.material, "count": r.n} for r in mat_rows],
        "bills_by_year": [{"year": int(r.yr), "count": r.n} for r in year_rows if r.yr is not None],
        "undated_bills": undated,
    }
    if pc_rows:
        agg["product_coverage"] = {
            "note": "covered-product counts (electronics/batteries/textiles EPR bills only)",
            "products": [{"product": r.product, "count": r.n} for r in pc_rows],
        }
    return agg


# --- Deep synthesis: the DEFAULT answer mode. Read full-text passages from the matched set (not 15
# summaries) and synthesize a cited briefing. Proven on prod ("stewardship plan recommendations").
# See docs/ATLAS_CIRCULAR_ROADMAP.md + memory atlas-circular-rebrand. -------------------------------
_DEEP_READ = 50          # max bills whose full-text passages we read into one synthesis call (v1);
                         # batched map-reduce beyond this is the documented scale-up.

_DEEP_SYSTEM = """\
You are a policy-research analyst for a circular-economy / EPR legislation database. You are given the
QUESTION, the SCOPE (how it was interpreted + how many bills matched), exact AGGREGATES, and BILL
MATERIAL — real excerpts from the FULL TEXT of the most relevant bills (or a bill's summary when no
text passage matched). Write a thorough, genuinely useful, CITED answer grounded ONLY in this material.
Rules:
- Cite each supported point inline with the bill(s), EXACTLY as [STATE BILL_NUMBER] using the `ref`
  field from the BILL MATERIAL verbatim (e.g. [MD HB331], [FR JORFTEXT000041553759]). Cite only bills
  present in the BILL MATERIAL.
- Where a requirement/finding recurs across bills, say so and cite several; flag single-bill outliers.
- You MAY state exact numbers from AGGREGATES. If both a scoped and corpus-wide count are given, reason
  about coverage from them ("122 of the 146 corpus-wide sit in France; the rest are elsewhere").
- NEVER claim something is absent when SCOPE.total > 0 — describe what the material shows. A true zero
  is only when SCOPE.total = 0.
- For "over time / by year / trend" questions, use AGGREGATES.bills_by_year (exact per-year counts from
  the corpus, not the read sample) to describe the distribution. If AGGREGATES.undated_bills > 0, say so
  plainly ("N bills carry no date yet and are excluded from the year breakdown") — this is a coverage
  caveat, NOT evidence that year data is missing. Never infer from the read sample that the corpus lacks
  dates; the year counts are authoritative.
- If SCOPE.note is present, follow it: it says how this set was assembled and what to emphasize (e.g. a
  diversity sample → describe the RANGE of distinct/outlier bill TYPES, citing a representative bill or
  two per type, and call out genuine single-bill outliers rather than summarizing one theme).
- Be concrete and practical — this should help someone act.
Output the answer as MARKDOWN directly (no JSON, no preamble): short "## " section headers, "- "
bullets, **bold** key terms, inline [STATE BILL_NUMBER] citations. No markdown tables.
"""


async def _passages_for(db: AsyncSession, ids: list[int], terms: list[str]) -> dict[int, str]:
    """Full-text ts_headline passages for the given bills, keyed to the question terms. Only bills
    whose text matches a term get a passage; the rest fall back to their summary at pack time."""
    if not ids or not terms:
        return {}
    tsq = func.to_tsquery(_ENGLISH, " | ".join(terms))
    headline = func.ts_headline(
        _ENGLISH, BillText.text, tsq,
        "MaxFragments=4,MinWords=10,MaxWords=26,FragmentDelimiter= / ")
    rows = (await db.execute(
        select(BillText.bill_id, headline.label("h"))
        .where(BillText.bill_id.in_(ids))
        .where(BillText.text_tsv.op("@@")(tsq)))).all()
    return {r.bill_id: (r.h or "").strip() for r in rows if (r.h or "").strip()}


def _pack_material(rows, passages: dict[int, str]) -> list[dict]:
    packed = []
    for r in rows:
        b = r.Bill
        cd = b.compliance_details or {}
        present = [d for d in DIMENSION_KEYS if isinstance(cd.get(d), dict) and cd[d].get("status") == "present"]
        excerpt = passages.get(b.id) or (b.ai_summary or "")
        packed.append({
            "id": b.id, "ref": f"{b.state} {b.bill_number or '?'}", "region": b.region,
            "year": b.status_date.year if b.status_date else None,
            "title": (b.title or "")[:140], "dimensions": present,
            "excerpt": (excerpt or "").strip()[:800],
        })
    return packed


async def _deep_answer(question: str, scope: dict, agg_scoped: dict, agg_corpus, packed: list,
                       history: list[dict] | None = None) -> str:
    """One synthesis call → the markdown briefing (returned directly, not JSON, so a long answer can't
    be broken by truncated-JSON parsing). Citations are recovered from the [REF] mentions afterward.
    On a follow-up, `history` (prior [{question, answer}] turns) is prepended so references like "those"
    or "compare that to Japan" resolve; the BILL MATERIAL is still freshly retrieved for THIS turn."""
    agg_block: dict = {"scoped": agg_scoped}
    if agg_corpus is not None:
        agg_block["corpus_wide"] = agg_corpus
    convo = ""
    if history:
        # Prior answers can be long; a short tail per turn is enough to resolve references without
        # blowing the context or re-citing stale bills (this turn cites only THIS turn's material).
        turns = "\n\n".join(
            f"Q{i+1}: {h['question']}\nA{i+1}: {(h.get('answer') or '')[:1200]}"
            for i, h in enumerate(history))
        convo = (f"CONVERSATION SO FAR (for context — resolve references against it, but ground every "
                 f"citation ONLY in the BILL MATERIAL below):\n{turns}\n\n")
    user_msg = (
        f"{convo}"
        f"QUESTION: {question}\n\n"
        f"SCOPE:\n{json.dumps(scope, ensure_ascii=False)}\n\n"
        f"AGGREGATES:\n{json.dumps(agg_block, ensure_ascii=False)}\n\n"
        f"BILL MATERIAL ({len(packed)} bills, full-text excerpts):\n"
        f"{json.dumps(packed, ensure_ascii=False)}"
    )
    resp = await _client.messages.create(
        model=RESEARCH_MODEL, max_tokens=4096, temperature=0,
        system=_DEEP_SYSTEM, messages=[{"role": "user", "content": user_msg}])
    return resp.content[0].text.strip()


_REWRITE_SYSTEM = (
    "You rewrite a user's FOLLOW-UP question in a research conversation into a single, standalone search "
    "query that captures everything needed to retrieve the right bills WITHOUT the conversation. Resolve "
    "pronouns and references ('those', 'that', 'the enacted ones', 'same but for Japan') using the prior "
    "turns, and carry forward any still-applicable scope (jurisdiction, material, instrument) unless the "
    "follow-up overrides or drops it.\n"
    "PRESERVE THE ANALYTICAL FRAME of the thread: if the conversation asks what OTHER regions can learn "
    "FROM a place, or compares X against Y, keep that same direction/verb and only substitute the new "
    "entity the follow-up introduces. Example: prior 'what can the rest of the regions learn from the "
    "Chinese bills?' + follow-up 'what about Japan?' -> 'what can the rest of the regions learn from the "
    "Japanese bills?' (NOT 'what can Japan learn').\n"
    "Output ONLY the rewritten query text — no preamble, no quotes."
)


async def _rewrite_followup(history: list[dict], question: str) -> str:
    """Condense (thread + follow-up) into a standalone retrieval query via one cheap Haiku call. The
    rewritten query then flows through the SAME deterministic resolve_facets / _relevant_bills path, so
    no follow-up-specific retrieval logic is needed. Best-effort: on any failure, fall back to the raw
    question (retrieval still works, just without carried context)."""
    if not history:
        return question
    convo = "\n".join(f"Q: {h['question']}\nA: {(h.get('answer') or '')[:500]}" for h in history)
    try:
        resp = await _client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=200, temperature=0,
            system=_REWRITE_SYSTEM,
            messages=[{"role": "user", "content": f"CONVERSATION:\n{convo}\n\nFOLLOW-UP: {question}\n\n"
                                                  f"Standalone query:"}])
        text = "".join(getattr(b, "text", "") for b in resp.content).strip()
        return text or question
    except Exception as e:  # noqa: BLE001 — never let the rewrite break the ask
        log.warning("research_followup_rewrite_failed", error=str(e))
        return question


async def _load_history(db: AsyncSession, uid: str, session_id: str):
    """Load an owned session's prior turns as [{question, answer}] + the next seq. Returns ([], 1, None)
    when the session is missing or not owned by `uid` (→ caller silently starts a fresh session)."""
    from app.models import ResearchSession, ResearchTurn
    try:
        sess = await db.get(ResearchSession, uuid.UUID(str(session_id)))
    except (ValueError, TypeError):
        return [], 1, None
    if not sess or sess.owner_uid != uid:
        return [], 1, None
    rows = (await db.execute(
        select(ResearchTurn.question, ResearchTurn.answer, ResearchTurn.seq)
        .where(ResearchTurn.session_id == sess.id).order_by(ResearchTurn.seq))).all()
    history = [{"question": r.question, "answer": (r.answer or {}).get("text", "")} for r in rows]
    next_seq = (max((r.seq for r in rows), default=0)) + 1
    return history, next_seq, sess.id


async def _persist_turn(uid, question, facets, strategy, total, answer_text, cited_ids, bill_ids,
                        shadow=None, session_id=None, seq=1, retrieval_query=None):
    """Persist the answer as a research_session + turn — the analysis layer that later becomes the
    Layer-1 knowledge cache. Uses its OWN fresh session (not the request's, which was released before
    the long LLM call) so a healthy connection does the write. When `session_id` is given (a follow-up),
    the turn is APPENDED at `seq`; otherwise a new session is created at seq=1. Returns the session id so
    the caller can hand it back for threading. Best-effort; the caller swallows failures so a save error
    never breaks the answer."""
    from app.models import ResearchSession, ResearchTurn
    async with AsyncSessionLocal() as s:
        if session_id is None:
            sess = ResearchSession(owner_uid=uid, title=question[:200])
            s.add(sess)
            await s.flush()
            session_id = sess.id
        fac = {"places": facets.place_labels, "reference": facets.reference_labels, "strategy": strategy}
        if shadow:
            fac["shadow_router"] = shadow  # A1 shadow-mode comparison (router vs deterministic); not used for retrieval
        s.add(ResearchTurn(
            session_id=session_id, seq=seq, question=question,
            rewritten_query=(retrieval_query if retrieval_query is not None else facets.free_text),
            facets=fac,
            strategy=(strategy or "")[:40],  # column is VARCHAR(40); multi-material strategies overflow
            answer={"text": answer_text, "cited_bill_ids": cited_ids},
            bill_ids=bill_ids, bill_total=total))
        await s.commit()
        return session_id


# --- Shadow-mode LLM router (A1) -----------------------------------------------------------------
# Runs the LLM query router (app/api/research_router.py) alongside the deterministic resolver on every
# ask, logs + persists the comparison, but does NOT drive retrieval yet. Fired concurrently with the
# Sonnet synthesis (which makes no DB calls), so it adds ~no latency. Flip to router-driven retrieval
# only after the shadow diffs on real traffic look right. See tests/eval/README.md.
_query_router = None


def _get_router():
    global _query_router
    if _query_router is None:
        from app.api.research_router import QueryRouter
        _query_router = QueryRouter()
    return _query_router


def _facet_diff(det_slugs, router_slugs):
    d, r = set(det_slugs), set(router_slugs)
    only_d, only_r = sorted(d - r), sorted(r - d)
    return {"only_deterministic": only_d, "only_router": only_r} if (only_d or only_r) else None


async def _shadow_route(question: str, det, det_total: int, det_top_ids: list) -> dict | None:
    """Best-effort shadow comparison. On a fresh session: route `question`, diff the facets vs the
    deterministic `det`, AND re-run the SAME retrieval with the router's facets to record the actual
    RESULTS delta (total + top-page bill-set difference) vs the deterministic result the user got.
    MUST NOT raise — it runs in a gather() with synthesis, so an exception here would break the answer."""
    try:
        async with AsyncSessionLocal() as s:
            rf = await _get_router().route(s, question)
            r_rows, r_total, r_strategy = await _relevant_bills(
                s, question, page=1, page_size=_PAGE_SIZE, facets=rf.to_facets())
            r_ids = [row.Bill.id for row in r_rows]
        diff = {k: v for k, v in {
            "materials": _facet_diff(det.material_slugs, rf.material_slugs),
            "instruments": _facet_diff(det.instrument_slugs, rf.instrument_slugs),
            "products": _facet_diff(det.product_slugs, rf.product_slugs),
            "places": _facet_diff(det.place_labels, rf.place_labels),
        }.items() if v}
        d, r = set(det_top_ids), set(r_ids)
        results = {
            "det_total": det_total, "router_total": r_total, "router_strategy": r_strategy,
            "top_overlap": len(d & r), "top_only_deterministic": sorted(d - r),
            "top_only_router": sorted(r - d),
        }
        has_illus = bool(rf.material_illustrations or rf.product_illustrations or rf.instrument_illustrations)
        shadow = {
            "intent": rf.intent,
            "router": {
                "places": rf.place_labels, "reference": rf.reference_labels, "exclude": rf.exclude_place_labels,
                "materials": rf.material_slugs, "instruments": rf.instrument_slugs,
                "products": rf.product_slugs, "dimensions": rf.dimensions,
                "material_illustrations": rf.material_illustrations,
                "product_illustrations": rf.product_illustrations,
                "instrument_illustrations": rf.instrument_illustrations,
                "free_text": rf.free_text,
            },
            "diff": diff, "results": results, "has_illustrations": has_illus,
        }
        log.info("research_shadow_router", q=question[:120], intent=rf.intent, diff=diff or None,
                 det_total=det_total, router_total=r_total,
                 top_changed=len(d ^ r), illus=has_illus)
        return shadow
    except Exception as e:  # noqa: BLE001 — shadow must never affect the ask
        log.warning("research_shadow_router_failed", error=str(e))
        return None


@router.post("/ask", response_model=ResearchAnswer)
async def ask_the_bills(
    body: ResearchAskRequest,
    # Admin-gated for now: shipping to prod for internal dogfooding before it opens to Pro. Flip this
    # dependency to require_pro to graduate it (and the /ask page guard + nav item's adminOnly flag).
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ResearchAnswer:
    question = (body.question or "").strip()
    if len(question) < 3:
        return ResearchAnswer(answer="Please ask a fuller question.", citations=[], coverage_note=None)

    # Thread continuity: if a valid owned session was passed, this is a FOLLOW-UP. Load its prior turns
    # and condense (thread + this question) into a standalone retrieval query, so the deterministic
    # retrieval path below is unchanged — it just runs on the rewritten query. First turns are untouched
    # (history empty → retrieval_q == question → no extra LLM call).
    history, seq, session_id = [], 1, None
    if body.session_id:
        history, seq, session_id = await _load_history(db, _user.uid, body.session_id)
    retrieval_q = await _rewrite_followup(history, question) if history else question

    facets = await resolve_facets(db, retrieval_q)
    geo_extra = _scope_extra(facets)  # jurisdiction + material scope for the scoped aggregates

    # The full matched set drives the table (page 1); the top _DEEP_READ are read DEEPLY — their
    # full-text passages, not summaries — and synthesized into a cited answer. Retrieval runs on the
    # (possibly rewritten) standalone query, with the resolved facets passed so it isn't re-resolved.
    page_rows, total, strategy = await _relevant_bills(db, retrieval_q, page=1, page_size=_PAGE_SIZE, facets=facets)
    read_rows, _, _ = await _relevant_bills(db, retrieval_q, page=1, page_size=_DEEP_READ, facets=facets)

    terms = facets.meaningful_terms()
    passages = await _passages_for(db, [r.Bill.id for r in read_rows], terms)
    packed = _pack_material(read_rows, passages)

    # Scoped aggregates (numbers that reflect the question) + the corpus-wide baseline when scoped, so
    # a comparison answer can reason "N of M corpus-wide sit in <place>".
    agg_scoped = await _aggregates(db, geo_extra)
    agg_corpus = await _aggregates(db) if geo_extra else None

    scope: dict = {"total": total, "strategy": strategy, "read": len(packed)}
    if facets.place_labels:
        scope["jurisdiction"] = facets.place_labels
    if facets.material_labels:
        scope["material"] = facets.material_labels
    if facets.product_labels:
        scope["product"] = facets.product_labels
    if facets.instrument_labels:
        scope["instrument"] = facets.instrument_labels
    if facets.reference_labels:
        scope["reference"] = facets.reference_labels
    if strategy.startswith("diversity"):
        scope["note"] = ("This set is a DIVERSITY SAMPLE across the corpus's distinct policy types "
                         "(instrument_type clusters, rarest first — one+ representative each), NOT an "
                         "exhaustive keyword match. Describe the most unique / outlier bill TYPES you "
                         "see, citing representative bills for each; flag true single-bill outliers.")

    # Release the request's DB connection before the ~30s synthesis so it isn't held idle (and dropped)
    # across the LLM call; the read data is already materialized and persistence uses a fresh session.
    read_bill_ids = [r.Bill.id for r in read_rows]
    await db.close()

    # Synthesis (Sonnet, DB-free) and the shadow router (Haiku, own session) run concurrently — the
    # router finishes within the synthesis window, so shadow mode costs ~no added latency.
    answer_text, shadow = await asyncio.gather(
        _deep_answer(question, scope, agg_scoped, agg_corpus, packed, history=history),
        _shadow_route(retrieval_q, facets, total, [r.Bill.id for r in page_rows]),
    )
    answer_text = answer_text or "I couldn't find enough in the corpus to answer that."

    # Citations: bills from the read set whose ref (e.g. "MD HB331") appears in the answer. Recovered
    # from the markdown rather than a JSON field, so a long/truncated answer still yields citations.
    citations, cited_ids = [], []
    for r in read_rows:
        b = r.Bill
        ref = f"{b.state} {b.bill_number}" if b.bill_number else None
        if ref and ref in answer_text and b.id not in cited_ids:
            cited_ids.append(b.id)
            citations.append(ResearchCitation(
                bill_id=b.id, region=b.region, state=b.state, bill_number=b.bill_number,
                year=b.status_date.year if b.status_date else None,
                snippet=(passages.get(b.id) or "").strip()[:280] or None,
                bill=_row_to_summary(r)))

    coverage = (f"Synthesized from the {len(packed)} most relevant of {total} matched bills."
                if total > len(packed) else f"Synthesized from all {total} matched bills.")

    # Persist the answer (analysis layer / future Layer-1 cache). Best-effort — never break the answer.
    # Appends to the existing session on a follow-up, else mints one; returns the id for threading.
    try:
        session_id = await _persist_turn(
            _user.uid, question, facets, strategy, total, answer_text, cited_ids, read_bill_ids,
            shadow=shadow, session_id=session_id, seq=seq, retrieval_query=retrieval_q)
    except Exception as e:  # noqa: BLE001
        log.warning("research_persist_failed", error=str(e))

    bills = ResearchBillPage(
        total=total, page=1, page_size=_PAGE_SIZE, strategy=strategy,
        items=[_row_to_summary(r) for r in page_rows],
    )
    # A bills-by-year chart when the question asks for a trend — exact bars from the SQL year aggregate.
    # Triggered on the rewritten query so a follow-up like "show that over time" still fires.
    scope_labels = (facets.place_labels + facets.material_labels + facets.instrument_labels
                    + facets.product_labels)
    chart = _year_chart(retrieval_q, agg_scoped, scope_labels)
    return ResearchAnswer(answer=answer_text, citations=citations, chart=chart,
                          coverage_note=coverage, bills=bills,
                          session_id=str(session_id) if session_id else None, seq=seq,
                          retrieval_query=(retrieval_q if retrieval_q != question else None))


@router.get("/bills", response_model=ResearchBillPage)
async def research_bills(
    question: str = Query(..., min_length=3, description="The same question asked at /research/ask."),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ResearchBillPage:
    """SQL-only pagination over the FULL relevant-bill set for a question — no LLM call. The Ask page's
    Prev/Next hit this for pages 2+, re-running the same deterministic cascade as /research/ask and
    slicing, so Next is cheap and the set is identical to what the answer narrated."""
    rows, total, strategy = await _relevant_bills(db, question, page=page, page_size=page_size)
    return ResearchBillPage(
        total=total, page=page, page_size=page_size, strategy=strategy,
        items=[_row_to_summary(r) for r in rows],
    )


@router.get("/session/{session_id}", response_model=ResearchSessionOut)
async def research_session(
    session_id: str,
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ResearchSessionOut:
    """Load an owned research thread with its turns in order — so the Ask page can restore/continue a
    conversation. 404 if the session doesn't exist or isn't owned by the caller (no cross-user reads)."""
    from fastapi import HTTPException
    from app.models import ResearchSession, ResearchTurn
    try:
        sid = uuid.UUID(session_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="No such session.")
    sess = await db.get(ResearchSession, sid)
    if not sess or sess.owner_uid != _user.uid:
        raise HTTPException(status_code=404, detail="No such session.")
    rows = (await db.execute(
        select(ResearchTurn.seq, ResearchTurn.question, ResearchTurn.rewritten_query, ResearchTurn.answer,
               ResearchTurn.bill_total)
        .where(ResearchTurn.session_id == sid).order_by(ResearchTurn.seq))).all()
    return ResearchSessionOut(
        session_id=str(sid), title=sess.title,
        turns=[ResearchTurnOut(
            seq=r.seq, question=r.question, retrieval_query=r.rewritten_query,
            answer=(r.answer or {}).get("text"), bill_total=r.bill_total or 0) for r in rows],
    )


# ============================================================================
# Admin research log · sharing · content staging (the Substack content engine)
# ============================================================================
# All three surfaces read the same persisted research_turns. Two of them (a public shared thread, a
# staged article) render the answer OUTSIDE the app — a standalone page or a Substack paste — where the
# in-app citation modal doesn't exist. So the inline [STATE BILL_NUMBER] markers are rewritten to
# battleofbills.com/?bill=<id> deep links (the SAME link the email alerts already use, see
# app/alerts/applinks). link_citations does the rewrite; _ref_map_for builds the ref->id table.

_CITE_TOKEN = re.compile(r"\[([^\[\]]+)\]")


async def _ref_map_for(db: AsyncSession, bill_ids: list[int]) -> dict[str, int]:
    """{'MD HB331': 4021, ...} for the given bills — the table that turns a citation marker into a deep
    link. Keyed on the same 'STATE BILL_NUMBER' ref the synthesis prompt emits verbatim."""
    ids = [i for i in dict.fromkeys(bill_ids) if i is not None]
    if not ids:
        return {}
    rows = (await db.execute(
        select(Bill.id, Bill.state, Bill.bill_number).where(Bill.id.in_(ids)))).all()
    return {f"{r.state} {r.bill_number}": r.id for r in rows if r.bill_number}


def link_citations(text: str | None, ref_to_id: dict[str, int]) -> str:
    """Rewrite inline [STATE BILL_NUMBER] markers to markdown deep links [STATE BILL_NUMBER](url) so a
    cited answer stays clickable outside the app. Markers with no matching bill are left verbatim; the
    stored answer carries no links yet, so this never double-links."""
    if not text or not ref_to_id:
        return text or ""

    def repl(m: "re.Match[str]") -> str:
        bid = ref_to_id.get(m.group(1).strip())
        return f"[{m.group(1)}]({bill_url(bid)})" if bid is not None else m.group(0)

    return _CITE_TOKEN.sub(repl, text)


def _cited_ids(turn) -> list[int]:
    """The bills a turn's answer actually cites (falls back to the full ranked set for older turns)."""
    ans = turn.answer or {}
    return list(ans.get("cited_bill_ids") or turn.bill_ids or [])


async def _get_session_or_404(db: AsyncSession, session_id: str):
    from app.models import ResearchSession
    try:
        sid = uuid.UUID(str(session_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="No such session.")
    sess = await db.get(ResearchSession, sid)
    if not sess:
        raise HTTPException(status_code=404, detail="No such session.")
    return sess


# --- Admin research log: every ask, across every owner --------------------------------------------
@router.get("/admin/turns", response_model=ResearchTurnAdminPage)
async def admin_research_turns(
    q: str | None = Query(default=None, description="Substring filter on the question."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ResearchTurnAdminPage:
    """The full research history — newest first — so an admin can audit questions and mine good answers
    for publishable content. Each turn's answer comes back with its citations already rewritten to
    /?bill=<id> deep links, and carries the parent session's share state for inline share/draft actions."""
    from app.models import ResearchSession, ResearchTurn
    stmt = (select(ResearchTurn, ResearchSession)
            .join(ResearchSession, ResearchTurn.session_id == ResearchSession.id))
    if q:
        stmt = stmt.where(ResearchTurn.question.ilike(f"%{q}%"))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ResearchTurn.created_at.desc()).limit(limit).offset(offset))).all()

    # One ref->id lookup for every bill cited on this page, then link each answer against it.
    all_ids = [i for t, _ in rows for i in _cited_ids(t)]
    ref_map = await _ref_map_for(db, all_ids)
    items = []
    for t, s in rows:
        ans = (t.answer or {}).get("text")
        items.append(ResearchTurnAdminItem(
            turn_id=str(t.id), session_id=str(s.id), session_title=s.title, owner_uid=s.owner_uid,
            seq=t.seq, question=t.question,
            answer=link_citations(ans, ref_map) if ans else None,
            strategy=t.strategy, bill_total=t.bill_total or 0, cited_count=len(_cited_ids(t)),
            visibility=s.visibility, share_token=s.share_token, created_at=t.created_at))
    return ResearchTurnAdminPage(total=total, items=items)


# --- Sharing: an unguessable, revocable link to a whole thread ------------------------------------
def _share_url(token: str) -> str:
    # Query-param form (not a /r/<token> path): the dashboard is a static export, so the reader page is
    # a single static /r/ route that pulls the token from the query string — same reason bill deep links
    # use /?bill=<id> rather than a dynamic route.
    return f"{DASHBOARD_URL}/r/?token={token}"


@router.post("/session/{session_id}/share", response_model=ShareOut)
async def share_session(
    session_id: str,
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ShareOut:
    """Mint (or reuse) an unguessable share link for a research thread and flip it to link-visible. The
    token is only ever handed out here; the public read at /research/shared/{token} matches on it."""
    sess = await _get_session_or_404(db, session_id)
    if not sess.share_token:
        sess.share_token = secrets.token_urlsafe(16)
    sess.visibility = "link"
    await db.commit()
    return ShareOut(session_id=str(sess.id), visibility="link", share_token=sess.share_token,
                    share_url=_share_url(sess.share_token))


@router.post("/session/{session_id}/unshare", response_model=ShareOut)
async def unshare_session(
    session_id: str,
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ShareOut:
    """Revoke sharing: back to private AND drop the token, so a link that already leaked stops working
    (re-sharing mints a fresh one)."""
    sess = await _get_session_or_404(db, session_id)
    sess.visibility = "private"
    sess.share_token = None
    await db.commit()
    return ShareOut(session_id=str(sess.id), visibility="private")


@router.get("/shared/{token}", response_model=SharedSessionOut)
async def shared_session(token: str, db: AsyncSession = Depends(get_db)) -> SharedSessionOut:
    """PUBLIC read of a shared research thread — no auth. Resolves ONLY when the session is explicitly
    link-shared and the token matches, so a private or never-shared thread can't leak. Citations render
    as outbound /?bill=<id> links (there's no in-app modal on a standalone page)."""
    from app.models import ResearchSession, ResearchTurn
    tok = (token or "").strip()
    if len(tok) < 8:
        raise HTTPException(status_code=404, detail="Not found.")
    sess = (await db.execute(
        select(ResearchSession).where(ResearchSession.share_token == tok,
                                      ResearchSession.visibility == "link"))).scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Not found.")
    turns = (await db.execute(
        select(ResearchTurn).where(ResearchTurn.session_id == sess.id)
        .order_by(ResearchTurn.seq))).scalars().all()

    all_ids = [i for t in turns for i in _cited_ids(t)]
    ref_map = await _ref_map_for(db, all_ids)
    bills = {}
    if all_ids:
        brows = (await db.execute(
            select(Bill).where(Bill.id.in_(list(dict.fromkeys(all_ids)))))).scalars().all()
        bills = {b.id: b for b in brows}

    turns_out = []
    for t in turns:
        ans = (t.answer or {}).get("text")
        cites = []
        for bid in _cited_ids(t):
            b = bills.get(bid)
            if not b or not b.bill_number:
                continue
            cites.append(SharedCitationOut(
                bill_id=b.id, ref=f"{b.state} {b.bill_number}", region=b.region,
                year=b.status_date.year if b.status_date else None, url=bill_url(b.id)))
        turns_out.append(SharedTurnOut(
            seq=t.seq, question=t.question,
            answer=link_citations(ans, ref_map) if ans else None, citations=cites))
    return SharedSessionOut(title=sess.title, created_at=sess.created_at, turns=turns_out)


# --- Content staging: distill a turn into an editable, linkable article draft ---------------------
_EDITORIAL_SYSTEM = """\
You are an editor turning an internal policy-research Q&A into a short, publishable article for a
circular-economy / EPR policy newsletter — a sharp Substack post read by producers, compliance teams,
and policy staff. You are given the QUESTION and the grounded ANSWER (markdown, with inline
[STATE BILL_NUMBER] citation markers).
Return a JSON object with EXACTLY these keys:
- "title": a specific, non-clickbait headline (<= 90 chars) — concrete about the finding, not "A look at…".
- "dek": one-sentence standfirst saying what the reader will learn (<= 160 chars).
- "body": the article body in markdown. Open with a 1-2 sentence lede on why this matters, then present
  the answer's substance. You MAY lightly restructure and tighten and add connective prose, but DO NOT
  invent facts, numbers, or bills beyond the ANSWER. PRESERVE every [STATE BILL_NUMBER] citation marker
  EXACTLY as written and keep it beside the claim it supports (they become links downstream). Use "## "
  subheads and "- " bullets. Do not repeat the title inside the body.
Output ONLY the JSON object — no preamble, no code fence.
"""


async def _editorialize(question: str, answer_text: str) -> dict | None:
    """One best-effort LLM pass: raw answer -> {title, dek, body} shaped like an article, citation
    markers preserved for the downstream link pass. None on any failure (caller falls back to verbatim)."""
    try:
        resp = await _client.messages.create(
            model=RESEARCH_MODEL, max_tokens=2200, temperature=0.3,
            system=_EDITORIAL_SYSTEM,
            messages=[{"role": "user", "content": f"QUESTION: {question}\n\nANSWER:\n{answer_text}"}])
        raw = "".join(getattr(b, "text", "") for b in resp.content).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.rstrip().endswith("```"):
                raw = raw.rstrip()[:-3]
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("body"):
            return {"title": str(data.get("title") or question)[:300],
                    "dek": (str(data["dek"]) if data.get("dek") else None),
                    "body": str(data["body"])}
    except Exception as e:  # noqa: BLE001 — editorial is optional polish, never block staging
        log.warning("content_editorial_failed", error=str(e))
    return None


def _draft_out(d) -> ContentDraftOut:
    return ContentDraftOut(
        id=str(d.id),
        source_session_id=str(d.source_session_id) if d.source_session_id else None,
        source_seq=d.source_seq, title=d.title, dek=d.dek, body_markdown=d.body_markdown,
        status=d.status, created_by=d.created_by, created_at=d.created_at, updated_at=d.updated_at)


@router.post("/drafts", response_model=ContentDraftOut)
async def create_content_draft(
    body: ContentDraftCreate,
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentDraftOut:
    """Send a research turn to the staging area: run the editorial pass (optional) + the citation link
    pass, then persist an editable ContentDraft. `body_markdown` comes out Substack-ready — its
    [STATE BILL_NUMBER] markers already rewritten to /?bill=<id> deep links."""
    from app.models import ContentDraft, ResearchTurn
    sess = await _get_session_or_404(db, body.session_id)
    tq = select(ResearchTurn).where(ResearchTurn.session_id == sess.id)
    if body.seq is not None:
        tq = tq.where(ResearchTurn.seq == body.seq)
    turn = (await db.execute(tq.order_by(ResearchTurn.seq.desc()).limit(1))).scalars().first()
    if not turn:
        raise HTTPException(status_code=404, detail="No such turn in that session.")
    answer_text = (turn.answer or {}).get("text") or ""
    if not answer_text.strip():
        raise HTTPException(status_code=400, detail="That turn has no answer to stage.")

    # Materialize everything the write needs, then release the request connection before the ~15s
    # editorial call (same reason /ask does: don't hold an idle connection across an LLM round-trip).
    ref_map = await _ref_map_for(db, _cited_ids(turn))
    question, seq, sess_id = turn.question, turn.seq, sess.id
    await db.close()

    title, dek, body_src = question[:300], None, answer_text
    if body.editorial:
        ed = await _editorialize(question, answer_text)
        if ed:
            title, dek, body_src = ed["title"], ed["dek"], ed["body"]
    body_md = link_citations(body_src, ref_map)

    async with AsyncSessionLocal() as s:
        draft = ContentDraft(
            source_session_id=sess_id, source_seq=seq, title=title, dek=dek,
            body_markdown=body_md, status="staged", created_by=_user.email)
        s.add(draft)
        await s.commit()
        await s.refresh(draft)
        return _draft_out(draft)


@router.get("/drafts", response_model=ContentDraftPage)
async def list_content_drafts(
    status: str | None = Query(default=None, description="Filter by staged | draft | published."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentDraftPage:
    from app.models import ContentDraft
    stmt = select(ContentDraft)
    if status:
        stmt = stmt.where(ContentDraft.status == status)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ContentDraft.updated_at.desc()).limit(limit).offset(offset))).scalars().all()
    return ContentDraftPage(total=total, items=[_draft_out(d) for d in rows])


async def _get_draft_or_404(db: AsyncSession, draft_id: str):
    from app.models import ContentDraft
    try:
        did = uuid.UUID(str(draft_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="No such draft.")
    d = await db.get(ContentDraft, did)
    if not d:
        raise HTTPException(status_code=404, detail="No such draft.")
    return d


@router.get("/drafts/{draft_id}", response_model=ContentDraftOut)
async def get_content_draft(
    draft_id: str,
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentDraftOut:
    return _draft_out(await _get_draft_or_404(db, draft_id))


_DRAFT_STATUSES = {"staged", "draft", "published"}


@router.patch("/drafts/{draft_id}", response_model=ContentDraftOut)
async def update_content_draft(
    draft_id: str,
    patch: ContentDraftPatch,
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentDraftOut:
    d = await _get_draft_or_404(db, draft_id)
    if patch.title is not None:
        d.title = patch.title[:300]
    if patch.dek is not None:
        d.dek = patch.dek or None
    if patch.body_markdown is not None:
        d.body_markdown = patch.body_markdown
    if patch.status is not None:
        if patch.status not in _DRAFT_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_DRAFT_STATUSES)}.")
        d.status = patch.status
    await db.commit()
    await db.refresh(d)
    return _draft_out(d)


@router.delete("/drafts/{draft_id}")
async def delete_content_draft(
    draft_id: str,
    _user: AuthedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    d = await _get_draft_or_404(db, draft_id)
    await db.delete(d)
    await db.commit()
    return {"deleted": True, "id": str(draft_id)}
