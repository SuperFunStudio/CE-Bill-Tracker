"""'Ask the Bills' — a retrieval-grounded, cited Q&A endpoint over the bill corpus (Pro).

Design (see the plan): the LLM ROUTES and NARRATES; SQL COMPUTES. For every question we
  1. retrieve the top-K bills by full-text relevance (each with its extracted dimension statuses), and
  2. precompute a couple of exact whole-corpus aggregates (collection-target basis, dimension
     prevalence) — cheap GROUP BY queries whose numbers are ground truth.
Then ONE Sonnet call answers using ONLY that material: it must cite bills from the retrieved set,
may reference the exact aggregate numbers, picks which (if any) aggregate to chart, and abstains when
the material doesn't support an answer. This keeps numbers trustworthy (from SQL) and claims traceable
(to cited bills) — the two things a compliance product can't get wrong.
"""
from __future__ import annotations

import json

import anthropic
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, literal_column, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthedUser, require_admin
from app.api.research_facets import resolve_facets
from app.config import settings
from app.database import get_db
from app.models import Bill, BillText, Jurisdiction, LitigationCase
from app.schemas import (
    BillSummary,
    ResearchAnswer,
    ResearchAskRequest,
    ResearchBillPage,
    ResearchChart,
    ResearchChartBar,
    ResearchCitation,
)

router = APIRouter(prefix="/research", tags=["research"])
log = structlog.get_logger()

RESEARCH_MODEL = "claude-sonnet-4-6"
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=90.0, max_retries=1)

DIMENSION_KEYS = [
    "collection_targets", "recycled_content", "eco_modulation", "fee_amounts",
    "penalties", "bans_restrictions", "pro_structure", "labeling",
]
_DIM_LABEL = {
    "collection_targets": "Collection / recovery targets", "recycled_content": "Recycled-content minimums",
    "eco_modulation": "Eco-modulation", "fee_amounts": "Producer fees", "penalties": "Penalties",
    "bans_restrictions": "Bans & restrictions", "pro_structure": "PRO structure", "labeling": "Labeling",
}
_BASIS_LABEL = {
    "weight": "Weight (tonnage)", "value_recovered": "Value recovered (critical metals)",
    "units": "Units / count", "material_specific": "Material-specific", "unspecified": "Unspecified",
}

SYSTEM_PROMPT = """\
You are a research analyst for an EPR / circular-economy legislation database. Answer the user's \
question using ONLY the RETRIEVED BILLS and AGGREGATES provided — never outside knowledge. Rules:
- Cite every factual claim with a bill from the retrieved set, as [STATE BILL_NUMBER].
- You MAY state exact numbers from the AGGREGATES (they are computed over the whole corpus).
- The retrieved bills are the TOP of a larger matched set — SCOPE gives its total size (and how the \
question was interpreted, e.g. jurisdiction = France). The sample is a window onto that set.
- NEVER assert that something is absent from the corpus. If SCOPE.total > 0, the set is non-empty — \
describe only what the sample shows ("among the N France bills, the top results are…"), never "there \
are no records" / "no French bills exist". A true absence is ONLY when SCOPE.total = 0.
- Honor the interpretation: if SCOPE names a jurisdiction/filter, frame the answer to it \
("Interpreting this as France…") rather than answering about the whole corpus.
- Do NOT say "all bills" unless citing an AGGREGATE (which is complete). Otherwise "among the bills found…".
- If SCOPE.total = 0, say plainly nothing matched and what would broaden it. Do not guess.
- Write concise plain prose with short "- " bullets. Do NOT use markdown tables or headings — a chart
  is rendered separately for the numbers. Light **bold** for key terms is fine.
Respond with ONLY valid JSON:
{
  "answer": "<plain prose + '- ' bullets; concise, with [STATE BILL_NUMBER] citations>",
  "cited_bill_ids": [<ids of retrieved bills you cited>],
  "chart": "<collection_target_basis|dimension_prevalence|none>",
  "coverage_note": "<one line qualifying completeness, e.g. 'Based on the 12 most relevant bills' or 'Aggregate over all analyzed bills'>"
}
"""


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
_LLM_SAMPLE = 15         # top-N of the relevant set narrated by the LLM

# Keyword → compliance-dimension map for the structured fallback tier: when precise full-text match
# is thin AND the question is clearly *about* a dimension, the relevant set is that dimension's bills
# (e.g. "compelling incentives" → eco_modulation), which is cleaner than OR-broadening the words.
# First match wins, so order encodes priority. Keys must match the compliance_details JSONB envelope.
_DIM_TRIGGERS: list[tuple[str, tuple[str, ...]]] = [
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


def _map_dimension(question: str) -> str | None:
    q = f" {question.lower()} "
    for dim, triggers in _DIM_TRIGGERS:
        if any(t in q for t in triggers):
            return dim
    return None


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
    db: AsyncSession, question: str, page: int = 1, page_size: int = _PAGE_SIZE
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

    facets = await resolve_facets(db, question)
    geo = facets.place_ids
    extra = [Bill.jurisdiction_id.in_(geo)] if geo else []

    def _cols():
        return (Bill,
                func.coalesce(lit.c.case_count, 0).label("case_count"),
                lit.c.max_risk.label("max_risk"))

    def _place_strategy(base: str) -> str:
        return f"{base}·{','.join(facets.place_labels)}" if facets.place_labels else base

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

    async def _count_plain(where_extra) -> int:
        q = select(func.count()).select_from(Bill).where(Bill.ce_relevant.is_(True))
        for c in list(extra) + list(where_extra):
            q = q.where(c)
        return (await db.scalar(q)) or 0

    terms = facets.meaningful_terms()

    # RULE 1 — free-text (text OR title/summary metadata) within the resolved scope. Build the query
    # from stopword-filtered terms so meta-words in the question ("which bills law…", rare in statute
    # text) can't poison the AND-match and drop an otherwise-good hit.
    if terms:
        tsq = func.websearch_to_tsquery(_ENGLISH, " ".join(terms))
        n = await _count_match(db, tsq, extra)
        if n > 0:
            rows = (await db.execute(_match_page(tsq))).all()
            return rows, n, _place_strategy("text")

    # RULE 2 — structured-by-dimension, only when no place was named.
    dim = _map_dimension(question)
    if dim and not geo:
        where_dim = [Bill.compliance_details[dim]["status"].astext == "present"]
        d_total = await _count_plain(where_dim)
        if d_total > 0:
            rows = (await db.execute(_plain_page(where_dim))).all()
            return rows, d_total, f"dimension:{dim}"

    # RULE 3 — OR-broaden, only when no place was named and free text found nothing precise.
    if terms and not geo:
        or_tsq = func.to_tsquery(_ENGLISH, " | ".join(terms))
        n = await _count_match(db, or_tsq, extra)
        if n > 0:
            rows = (await db.execute(_match_page(or_tsq))).all()
            return rows, n, "text_broad"

    # RULE 4 — listing: the base set (place-scoped or whole corpus). Interleave across jurisdictions
    # when comparing 2+ named places so each shows on page 1; otherwise straight recency.
    interleave = len(facets.place_labels) > 1
    n = await _count_plain([])
    rows = (await db.execute(_plain_page([], interleave=interleave))).all() if n else []
    return rows, n, (_place_strategy("jurisdiction") if geo else "all")


def _row_to_summary(row) -> BillSummary:
    s = BillSummary.model_validate(row.Bill)
    s.litigation_case_count = row.case_count or 0
    s.max_preemption_risk = row.max_risk
    return s


async def _aggregates(db: AsyncSession) -> dict:
    """Exact whole-corpus aggregates the answer may cite/chart (numbers are ground truth, not LLM)."""
    # Collection-target basis distribution (unnest targets; the founding-question axis).
    targets = func.jsonb_array_elements(
        Bill.compliance_details["collection_targets"]["targets"]
    ).table_valued("value").lateral()
    basis = func.jsonb_extract_path_text(targets.c.value, "basis")
    basis_rows = (
        await db.execute(
            select(basis.label("basis"), func.count().label("n"))
            .select_from(Bill)
            .join(targets, true())
            .where(Bill.ce_relevant.is_(True))
            .where(Bill.compliance_details["collection_targets"]["status"].astext == "present")
            .group_by(basis)
            .order_by(func.count().desc())
        )
    ).all()
    # Per-dimension "present" counts in one pass.
    prevalence_row = (
        await db.execute(
            select(
                *[
                    func.count()
                    .filter(Bill.compliance_details[d]["status"].astext == "present")
                    .label(d)
                    for d in DIMENSION_KEYS
                ]
            ).where(Bill.ce_relevant.is_(True))
        )
    ).first()
    return {
        "collection_target_basis": [{"basis": r.basis or "unspecified", "count": r.n} for r in basis_rows],
        "dimension_prevalence": {d: getattr(prevalence_row, d) for d in DIMENSION_KEYS},
    }


def _build_chart(kind: str, agg: dict) -> ResearchChart | None:
    if kind == "collection_target_basis":
        bars = [ResearchChartBar(label=_BASIS_LABEL.get(r["basis"], r["basis"]), value=r["count"])
                for r in agg["collection_target_basis"]]
        return ResearchChart(title="How collection targets are measured", bars=bars) if bars else None
    if kind == "dimension_prevalence":
        bars = [ResearchChartBar(label=_DIM_LABEL[d], value=n)
                for d, n in sorted(agg["dimension_prevalence"].items(), key=lambda x: -x[1]) if n]
        return ResearchChart(title="Bills addressing each dimension", bars=bars) if bars else None
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

    # Page 1 of the FULL relevant-bill set (paged, uncapped total). The LLM narrates the top slice of
    # this same set, so the answer and the table the user pages through are consistent by construction.
    page_rows, total, strategy = await _relevant_bills(db, question, page=1, page_size=_PAGE_SIZE)
    sample = page_rows[:_LLM_SAMPLE]
    facets = await resolve_facets(db, question)  # for the SCOPE the model must honor (never assert absence)
    agg = await _aggregates(db)

    # Compact, model-facing view of the retrieved sample — ref + snippet + which dimensions are present.
    retrieved = []
    for r in sample:
        b = r.Bill
        year = b.status_date.year if b.status_date else None
        cd = b.compliance_details or {}
        present = [d for d in DIMENSION_KEYS if isinstance(cd.get(d), dict) and cd[d].get("status") == "present"]
        retrieved.append({
            "id": b.id, "ref": f"{b.state} {b.bill_number or '?'}",
            "region": b.region, "year": year, "title": (b.title or "")[:140],
            "snippet": (getattr(r, "snippet", None) or "").strip()[:280], "present_dimensions": present,
        })

    scope = {"total": total, "strategy": strategy}
    if facets.place_labels:
        scope["jurisdiction"] = facets.place_labels
    user_msg = (
        f"QUESTION: {question}\n\n"
        f"SCOPE (the matched set the sample is drawn from):\n{json.dumps(scope, ensure_ascii=False)}\n\n"
        f"AGGREGATES (exact, whole-corpus):\n{json.dumps(agg, ensure_ascii=False)}\n\n"
        f"RETRIEVED BILLS (top {len(retrieved)} of {total} matched):\n"
        f"{json.dumps(retrieved, ensure_ascii=False)}"
    )
    resp = await _client.messages.create(
        model=RESEARCH_MODEL, max_tokens=1500, temperature=0,
        system=SYSTEM_PROMPT, messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group()) if m else {}

    # Citations: only bills in the sample the model actually saw (it cannot cite outside that set).
    by_id = {r.Bill.id: r for r in sample}
    cited_ids = [i for i in (data.get("cited_bill_ids") or []) if i in by_id]
    citations = []
    for i in cited_ids:
        r = by_id[i]
        b = r.Bill
        citations.append(ResearchCitation(
            bill_id=b.id, region=b.region, state=b.state, bill_number=b.bill_number,
            year=b.status_date.year if b.status_date else None,
            snippet=(getattr(r, "snippet", None) or "").strip()[:280] or None,
        ))

    bills = ResearchBillPage(
        total=total, page=1, page_size=_PAGE_SIZE, strategy=strategy,
        items=[_row_to_summary(r) for r in page_rows],
    )
    return ResearchAnswer(
        answer=data.get("answer", "").strip() or "I couldn't find enough in the corpus to answer that.",
        citations=citations,
        chart=_build_chart(data.get("chart", "none"), agg),
        coverage_note=data.get("coverage_note"),
        bills=bills,
    )


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
