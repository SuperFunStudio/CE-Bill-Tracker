"""Corpus cross-check — measure a draft against ENACTED laws in the same material regime.

The fit score (app/evaluation/strength.py) says whether a draft carries the mechanisms its material's
economics demand. This layer answers the next question a user actually asks: "how might this land?" —
by pulling the enacted laws for the same material class, scoring each on the *same* mechanisms, and
attaching any documented real-world outcomes (bill_outcome). So the draft is read not against a
hand-wavy ideal but against the measures that already made it onto the books, some with results in.

Enacted analogs are positioned with the same rules as the draft (reusing strength.position), so an
"incremental-viable" draft is only ever compared to incremental-viable enacted laws, and a
"critical-mass" textiles draft to the textiles/footwear/film laws that share its brutal economics.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classification.sonnet_extractor import SonnetResult
from app.evaluation.strength import (
    _bases,
    position,
    requirements_for,
    result_from_compliance_details,
)
from app.models import Bill, BillOutcome
from app.schemas import (
    AnalogOutcome,
    CorpusAnalog,
    CorpusBaselinePoint,
    CorpusCrossCheck,
    RequirementResult,
)

# Cap on enacted rows positioned per request. The enacted+ce_relevant universe is bounded (hundreds),
# and the endpoint is Pro + rate-limited, so one pass over it is fine; the cap is an abuse backstop.
_CANDIDATE_LIMIT = 600
_DISPLAY_LIMIT = 6
_VALUE_BASES = {"value_recovered", "material_specific"}


def _outcome_metric(o: BillOutcome) -> str | None:
    if o.metric_display:
        return o.metric_display
    if o.metric_value is not None:
        return f"{o.metric_value:g} {o.metric_unit or ''}".strip() + (f" — {o.metric_label}" if o.metric_label else "")
    return o.metric_label


async def cross_check(
    db: AsyncSession,
    draft_result: SonnetResult,
    draft_reqs: list[RequirementResult],
    regime_key: str,
    material: str,
) -> CorpusCrossCheck | None:
    """Build the cross-check block, or None if there are no enacted analogs in this regime."""
    rows = (
        await db.execute(
            select(
                Bill.id, Bill.region, Bill.state, Bill.bill_number, Bill.title,
                Bill.status_date, Bill.reviewed, Bill.compliance_details,
            )
            .where(Bill.status == "enacted")
            .where(Bill.ce_relevant.is_(True))
            .where(Bill.compliance_details.isnot(None))
            .order_by(Bill.reviewed.desc(), Bill.status_date.desc().nullslast())
            .limit(_CANDIDATE_LIMIT)
        )
    ).all()

    # Position every enacted candidate; keep those that land in the draft's regime.
    analogs: list[dict] = []
    for r in rows:
        res = result_from_compliance_details(r.compliance_details)
        r_regime, r_material, *_ = position(res, r.title)
        if r_regime != regime_key:
            continue
        reqs, _ = requirements_for(res, regime_key)
        analogs.append({
            "row": r, "material": r_material, "same_material": r_material == material,
            "mechanisms": {rq.key: rq.status for rq in reqs},
            "met": sum(1 for rq in reqs if rq.status == "met"),
            "value_aligned": bool(_bases(res) & _VALUE_BASES),
            "has_basis": bool(_bases(res) - {""}),
        })
    if not analogs:
        return None

    # Attach documented outcomes for the analogs we actually have as bill rows.
    ids = [a["row"].id for a in analogs]
    outcome_rows = (await db.execute(
        select(BillOutcome).where(BillOutcome.bill_id.in_(ids)).order_by(BillOutcome.reviewed.desc())
    )).scalars().all()
    outcomes_by_bill: dict[int, list[AnalogOutcome]] = {}
    for o in outcome_rows:
        outcomes_by_bill.setdefault(o.bill_id, []).append(AnalogOutcome(
            direction=o.direction, summary=o.summary, metric=_outcome_metric(o),
            attribution=o.attribution, source_name=o.source_name, source_url=o.source_url,
        ))

    # Baseline: share of same-regime enacted analogs carrying each required (non-bonus) mechanism,
    # next to the draft's own status — the "did the ones that got enacted carry this?" comparison.
    n = len(analogs)
    scored_keys = [(rq.key, rq.label, rq.status) for rq in draft_reqs if rq.importance != "bonus"]
    baseline = [
        CorpusBaselinePoint(
            key=key, label=label, your_status=your,
            analog_share=round(sum(1 for a in analogs if a["mechanisms"].get(key) == "met") / n, 3),
        )
        for key, label, your in scored_keys
    ]
    with_basis = [a for a in analogs if a["has_basis"]]
    value_basis_share = (
        round(sum(1 for a in with_basis if a["value_aligned"]) / len(with_basis), 3) if with_basis else None
    )

    # Rank the display set: outcomes first (impact landed), then same material, reviewed, most mechanisms.
    def _rank(a: dict) -> tuple:
        has_outcome = a["row"].id in outcomes_by_bill
        return (has_outcome, a["same_material"], a["row"].reviewed, a["met"])

    top = sorted(analogs, key=_rank, reverse=True)[:_DISPLAY_LIMIT]
    display = [
        CorpusAnalog(
            bill_id=a["row"].id, region=a["row"].region, state=a["row"].state,
            bill_number=a["row"].bill_number, title=(a["row"].title or "")[:160] or None,
            year=a["row"].status_date.year if a["row"].status_date else None,
            material=a["material"], same_material=a["same_material"], reviewed=a["row"].reviewed,
            mechanisms=a["mechanisms"], outcomes=outcomes_by_bill.get(a["row"].id, []),
        )
        for a in top
    ]

    same_material_count = sum(1 for a in analogs if a["same_material"])
    note = (
        f"Measured against {n} enacted law{'s' if n != 1 else ''} in the same regime"
        + (f" ({same_material_count} share your material class)" if same_material_count else "")
        + ". Shares show how many of those on-the-books laws carry each mechanism."
    )
    return CorpusCrossCheck(
        regime=regime_key, analog_count=n, same_material_count=same_material_count,
        value_basis_share=value_basis_share, baseline=baseline, analogs=display, note=note,
    )
