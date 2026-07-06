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
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthedUser, require_admin
from app.config import settings
from app.database import get_db
from app.models import Bill, BillText
from app.schemas import (
    ResearchAnswer,
    ResearchAskRequest,
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
- Retrieved bills are a relevance-ranked SAMPLE, not the whole corpus. Do NOT say "all bills" unless \
you are citing an AGGREGATE (which is complete). Otherwise say "among the bills found…".
- If the material does not support an answer, say so plainly and say what's missing. Do not guess.
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


async def _retrieve(db: AsyncSession, question: str, k: int = 15) -> list:
    """Top-K ce_relevant bills by full-text relevance to the question, each with a highlighted snippet.
    Reuses the same Postgres FTS as GET /bills/search (Layer B)."""
    tsq = func.websearch_to_tsquery("english", question)
    rank = func.ts_rank(BillText.text_tsv, tsq)
    headline = func.ts_headline(
        "english", BillText.text, tsq, "MaxFragments=1,MaxWords=30,MinWords=12,StartSel=,StopSel="
    )
    stmt = (
        select(Bill, headline.label("snippet"))
        .join(BillText, BillText.bill_id == Bill.id)
        .where(Bill.ce_relevant.is_(True))
        .where(BillText.text_tsv.op("@@")(tsq))
        .order_by(rank.desc())
        .limit(k)
    )
    return list((await db.execute(stmt)).all())


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

    rows = await _retrieve(db, question)
    agg = await _aggregates(db)

    # Compact, model-facing view of the retrieved bills — ref + snippet + which dimensions are present.
    retrieved = []
    for r in rows:
        b = r.Bill
        year = b.status_date.year if b.status_date else None
        cd = b.compliance_details or {}
        present = [d for d in DIMENSION_KEYS if isinstance(cd.get(d), dict) and cd[d].get("status") == "present"]
        retrieved.append({
            "id": b.id, "ref": f"{b.state} {b.bill_number or '?'}",
            "region": b.region, "year": year, "title": (b.title or "")[:140],
            "snippet": (r.snippet or "").strip()[:280], "present_dimensions": present,
        })

    user_msg = (
        f"QUESTION: {question}\n\n"
        f"AGGREGATES (exact, whole-corpus):\n{json.dumps(agg, ensure_ascii=False)}\n\n"
        f"RETRIEVED BILLS (relevance-ranked sample):\n{json.dumps(retrieved, ensure_ascii=False)}"
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

    # Citations: only bills that were actually retrieved (the model cannot cite outside the set).
    by_id = {r.Bill.id: r for r in rows}
    cited_ids = [i for i in (data.get("cited_bill_ids") or []) if i in by_id]
    citations = []
    for i in cited_ids:
        r = by_id[i]
        b = r.Bill
        citations.append(ResearchCitation(
            bill_id=b.id, region=b.region, state=b.state, bill_number=b.bill_number,
            year=b.status_date.year if b.status_date else None,
            snippet=(r.snippet or "").strip()[:280] or None,
        ))

    return ResearchAnswer(
        answer=data.get("answer", "").strip() or "I couldn't find enough in the corpus to answer that.",
        citations=citations,
        chart=_build_chart(data.get("chart", "none"), agg),
        coverage_note=data.get("coverage_note"),
    )
