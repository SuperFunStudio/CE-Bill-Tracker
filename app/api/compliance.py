"""Compliance-action API — the "now what do I do" layer surfaced per state.

GET /compliance/pathways?state=XX returns one pathway per enacted EPR law in the state,
each carrying its next action (join_pro / file_individual_plan / register_with_state / …),
the administering entity (PRO or agency) inlined, the soonest deadline, and a fee flag.
Empty list => the state has no enacted EPR law; the frontend renders the "no law" message.
?bill_ids=1,2,3 is the per-bill form — the "what must I actually do" block on the deadline modal
and the bill page look their law up by id, so it must not inherit the US region default.
See app/models.py CompliancePathway/ComplianceEntity and scripts/build_compliance_pathways.py.

GET /compliance/fee-schedule returns the CA SB 54 (2027 draft) producer fee schedule —
pure in-code reference data (app/scoring/ca_sb54_fees.py, the same grounded anchor the
company-obligations scoring uses), no DB. Public/free, like /pathways. This is Layer B — the
curated, runnable per-material rate-table engine.

GET /compliance/fee-amounts (+ /summary) and /compliance/eco-modulation are Layer A — the fee facts
a measure actually STATES, read straight from the compliance_details.fee_amounts / eco_modulation
envelopes (no LLM), each cited to a verbatim source_excerpt. These are the API's differentiated
cross-jurisdiction dataset, so they're breadth-gated: the /summary aggregate is open+full, but the
row endpoints serve the full 40+ jurisdictions only to a Pro/admin caller and a US-only capped teaser
to everyone else (best-effort, never 401s). See docs/FEE_DATA_API_SPEC.md.
"""
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_optional_pro
from app.database import get_db
from app.models import Bill, ComplianceEntity, CompliancePathway
from app.schemas import (
    ComplianceEntityRef,
    CompliancePathwaySummary,
    EcoModulationResponse,
    EcoModulationRow,
    FeeAmountRow,
    FeeAmountsResponse,
    FeeAmountsSummary,
    FeeScheduleCategory,
    FeeSchedulePlasticAdder,
    FeeScheduleRate,
    FeeScheduleResponse,
    KeyCount,
    ProducerAttributionResponse,
    ProducerAttributionRow,
)
from app.scoring.ca_sb54_fees import (
    _PLASTIC_PPMF_ADDER,
    _PLASTIC_REUSE_ADDER,
    CA_SB54_2027_SCHEDULE,
    HIGH_SCENARIO_MULTIPLIER,
    LB_PER_TONNE,
    SCHEDULE_CITATION,
    SCHEDULE_SOURCE_URL,
    _cents_lb_to_per_tonne,
)
from app.scoring.materials import _CANONICAL_ALIASES
from app.scoring.producer_attribution import (
    coverage as attribution_coverage,
    jurisdictions_for_regime,
    resolve_attribution,
)
from app.synthesis.fee_kind import classify_fee_kind

router = APIRouter(prefix="/compliance", tags=["compliance"])

# Final 2027 rates land October 2026 (see ca_sb54_fees.py module docstring); until then
# these are the published draft ranges.
RATES_FINAL_EXPECTED = "October 2026"

# Breadth gate for the Layer-A row endpoints. A non-Pro caller sees only US rows, capped — the free
# teaser. The value of the dataset is the 40+-jurisdiction body behind the gate (docs §7).
FEE_TEASER_REGION = "US"
# Ceiling on a ?bill_ids= lookup — the callers ask for one bill (modal) or a page's worth, never bulk.
PATHWAY_BILL_ID_LIMIT = 200
FEE_TEASER_LIMIT = 25
_FEE_TEASER_NOTE = (
    "Showing the US teaser. Full cross-jurisdiction fee data (40+ jurisdictions), uncapped, "
    "requires an API plan — see /developers."
)


def _fee_rate(tier: str, name: str | None, base_cents: float, adder_cents: float,
              with_high: bool = False) -> FeeScheduleRate:
    total = base_cents + adder_cents
    per_tonne = _cents_lb_to_per_tonne(total)
    return FeeScheduleRate(
        tier=tier,
        format_name=name,
        base_cents_per_lb=base_cents,
        plastic_adder_cents_per_lb=adder_cents,
        total_cents_per_lb=total,
        usd_per_tonne=per_tonne,
        usd_per_tonne_high=round(per_tonne * HIGH_SCENARIO_MULTIPLIER) if with_high else None,
    )


@router.get("/fee-schedule", response_model=FeeScheduleResponse)
async def fee_schedule():
    """CA SB 54 (2027 draft) per-material-format producer fee schedule. Public reference data."""
    categories: list[FeeScheduleCategory] = []
    for category, spec in CA_SB54_2027_SCHEDULE.items():
        adder = spec["plastic_adder_cents_lb"]
        categories.append(
            FeeScheduleCategory(
                material_category=category,
                aliases=sorted(k for k, v in _CANONICAL_ALIASES.items() if v == category),
                includes_plastic_adder=adder > 0,
                note=spec.get("note"),
                rates=[
                    _fee_rate("best", spec["best_format"]["name"],
                              spec["best_format"]["base_cents_lb"], adder),
                    _fee_rate("representative", None,
                              spec["representative_base_cents_lb"], adder, with_high=True),
                    _fee_rate("worst", spec["worst_format"]["name"],
                              spec["worst_format"]["base_cents_lb"], adder),
                ],
            )
        )
    return FeeScheduleResponse(
        program="CA SB-54",
        basis=SCHEDULE_CITATION,
        source_url=SCHEDULE_SOURCE_URL,
        rates_final_expected=RATES_FINAL_EXPECTED,
        lb_per_tonne=LB_PER_TONNE,
        high_scenario_multiplier=HIGH_SCENARIO_MULTIPLIER,
        plastic_adder=FeeSchedulePlasticAdder(
            reuse_cents_per_lb=_PLASTIC_REUSE_ADDER,
            ppmf_cents_per_lb=_PLASTIC_PPMF_ADDER,
            total_cents_per_lb=_PLASTIC_REUSE_ADDER + _PLASTIC_PPMF_ADDER,
        ),
        categories=categories,
    )


# ---------------------------------------------------------------------------
# Producer attribution — WHO owes it, before any rate is applied
# ---------------------------------------------------------------------------


# Listed in the public schema since the "Who is the producer?" panel on /compliance became its
# first frontend caller (it was shipped unlisted while no UI consumed it).
@router.get(
    "/producer-attribution",
    response_model=ProducerAttributionResponse,
)
async def producer_attribution(
    jurisdiction: str | None = Query(
        default=None, description="Jurisdiction code, e.g. US-OR, UK, FR. Omit for all."
    ),
    regime: str = Query(
        default="packaging_epr",
        description="packaging_epr (default) | plastic_tax | sup_levy | drs | carryout_bag. "
                    "Attribution differs BY REGIME within one jurisdiction.",
    ),
    franchised: bool = Query(
        default=False, description="Business operates wholly or partly as a franchise."
    ),
    sourcing: str | None = Query(
        default=None,
        description="domestic_supplier | self_import | own_brand. Selects the branch in "
                    "jurisdictions where sourcing route flips liability (DE, IT, ES).",
    ),
):
    """Which party owes the packaging obligation, per jurisdiction and regime, with citations.

    Open and unauthenticated, deliberately — the same posture as /pathways and /fee-schedule.
    Knowing you are a covered producer in Oregon is the fact that makes someone subscribe;
    putting it behind the paywall would sell a locked answer to a question they can't yet ask.

    An absent (jurisdiction, regime) pair returns no row. Callers MUST render that as
    "unknown — verify this yourself", never as "not obligated": silence here means we hold
    no cited rule, which is not the same as an exemption.
    """
    codes = [jurisdiction] if jurisdiction else jurisdictions_for_regime(regime)
    rows = [
        r for r in (
            resolve_attribution(code, regime, franchised=franchised, sourcing=sourcing)
            for code in codes
        ) if r is not None
    ]
    return ProducerAttributionResponse(
        rows=[ProducerAttributionRow(**r) for r in rows],
        count=len(rows),
        coverage=attribution_coverage(),
    )


# ---------------------------------------------------------------------------
# Layer A — bill-sourced fee amounts + eco-modulation (from compliance_details)
# ---------------------------------------------------------------------------


def _parse_regions(regions: str | None) -> list[str] | None:
    """CSV of jurisdiction codes -> upper-cased list, or None for "all" (empty/missing/contains 'all').
    Local copy of the bills.py helper to avoid coupling the compliance router to the bills router."""
    if not regions:
        return None
    codes = [r.strip().upper() for r in regions.split(",") if r.strip()]
    if not codes or "ALL" in codes:
        return None
    return codes


def _resolve_regions(region: str | None, regions: str | None) -> list[str] | None:
    """Fee endpoints default to ALL regions (cross-jurisdiction is the value) — unlike bills.py's
    US-default. `regions` CSV wins; a single `region` narrows; None/"all" => no region filter."""
    if regions is not None:
        return _parse_regions(regions)
    if region is None or region.lower() == "all":
        return None
    return [region.upper()]


def _gate_regions(codes: list[str] | None, is_pro: bool) -> tuple[list[str] | None, bool]:
    """Apply the breadth gate. A non-Pro caller is forced to the US teaser regardless of what they
    asked for; Pro/admin keeps the resolved scope. Returns (effective_codes, is_teaser)."""
    if is_pro:
        return codes, False
    return [FEE_TEASER_REGION], True


async def _fetch_fee_rows(
    db: AsyncSession,
    *,
    codes: list[str] | None,
    state: str | None,
    status: str | None,
    basis: str | None,
    currency: str | None,
) -> list[dict]:
    """Lateral-unnest the fee_amounts.rates[] of every ce_relevant bill whose envelope is `present`.

    Returns ALL matching entries (no SQL LIMIT/OFFSET) — the set is small (~1.3k rows corpus-wide), and
    the derived fee_kind + material_category filters and pagination are applied in Python so they stay
    correct. Scalar fields are pulled as text (r->>'…') so a malformed amount can't crash a ::numeric cast.
    """
    clauses = [
        "b.ce_relevant = true",
        "b.compliance_details->'fee_amounts'->>'status' = 'present'",
    ]
    params: dict = {}
    if codes is not None:
        clauses.append("b.region IN :regions")
        params["regions"] = codes
    if state:
        clauses.append("b.state = :state")
        params["state"] = state.upper()
    if status:
        clauses.append("b.status = :status")
        params["status"] = status
    if basis:
        clauses.append("r->>'basis' = :basis")
        params["basis"] = basis
    if currency:
        clauses.append("upper(r->>'currency') = :currency")
        params["currency"] = currency.upper()

    sql = f"""
        SELECT b.id AS bill_id, b.region, b.state, b.bill_number, b.title AS bill_title,
               b.status, b.source_url, b.material_categories,
               r->>'basis'    AS basis,
               r->>'amount'   AS amount,
               r->>'currency' AS currency,
               r->>'material' AS material,
               b.compliance_details->'fee_amounts'->>'source_excerpt' AS source_excerpt,
               b.compliance_details->>'extraction_version' AS extraction_version
        FROM bills b
        CROSS JOIN LATERAL jsonb_array_elements(b.compliance_details->'fee_amounts'->'rates') AS r
        WHERE {' AND '.join(clauses)}
        ORDER BY b.last_action_date DESC NULLS LAST, b.id
    """
    stmt = text(sql)
    if codes is not None:
        stmt = stmt.bindparams(bindparam("regions", expanding=True))
    res = await db.execute(stmt, params)
    return [dict(m) for m in res.mappings().all()]


def _coerce_amount(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _coerce_json_list(val) -> list | None:
    """material_categories / criteria come back as a JSON string or an already-decoded list depending on
    the driver's JSONB codec — normalize to a Python list."""
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except json.JSONDecodeError:
            return None
    return val if isinstance(val, list) else None


def _build_fee_rows(
    records: list[dict],
    *,
    fee_kind: str | None = None,
    has_amount: bool | None = None,
    material_category: str | None = None,
) -> list[FeeAmountRow]:
    """Type, classify, and filter raw DB records into FeeAmountRow. Pure (no I/O) so it's unit-tested
    without a database. Applies the derived-fee_kind, has_amount, and material_category filters here."""
    out: list[FeeAmountRow] = []
    for m in records:
        amount = _coerce_amount(m.get("amount"))
        if has_amount is True and amount is None:
            continue
        if has_amount is False and amount is not None:
            continue
        if material_category:
            mats = _coerce_json_list(m.get("material_categories"))
            if not (mats and material_category in mats):
                continue
        kind = classify_fee_kind(m.get("basis"), m.get("material"))
        if fee_kind and kind != fee_kind:
            continue
        excerpt = m.get("source_excerpt")
        ev = m.get("extraction_version")
        out.append(
            FeeAmountRow(
                bill_id=m["bill_id"],
                region=m["region"],
                state=m["state"],
                bill_number=m.get("bill_number"),
                bill_title=m.get("bill_title"),
                status=m.get("status"),
                source_url=m.get("source_url"),
                basis=m.get("basis"),
                amount=amount,
                currency=m.get("currency"),
                material=m.get("material"),
                fee_kind=kind,
                grounded=bool(excerpt),
                source_excerpt=excerpt,
                extraction_version=int(ev) if ev and str(ev).isdigit() else None,
            )
        )
    return out


@router.get("/fee-amounts", response_model=FeeAmountsResponse)
async def fee_amounts(
    region: str | None = Query(default=None, description="Jurisdiction family (default: all). Non-Pro is forced to US."),
    regions: str | None = Query(default=None, description="CSV of codes; wins over `region`."),
    state: str | None = None,
    status: str | None = None,
    basis: str | None = Query(default=None, description="per_ton|per_unit|flat|eco_modulated|percent_revenue|unspecified"),
    fee_kind: str | None = Query(default=None, description="producer_fee|registration|incentive|penalty|threshold|admin_cost|unspecified"),
    currency: str | None = Query(default=None, description="ISO 4217, e.g. USD, EUR, GBP"),
    has_amount: bool | None = Query(default=None, description="true = only entries with a numeric amount"),
    material_category: str | None = None,
    limit: int = Query(default=100, le=5000),
    offset: int = 0,
    is_pro: bool = Depends(get_optional_pro),
    db: AsyncSession = Depends(get_db),
):
    """Bill-sourced fee amounts, one row per stated rate, cited. US-teaser for non-Pro; full for Pro."""
    codes, teaser = _gate_regions(_resolve_regions(region, regions), is_pro)
    records = await _fetch_fee_rows(
        db, codes=codes, state=state, status=status, basis=basis, currency=currency
    )
    rows = _build_fee_rows(
        records, fee_kind=fee_kind, has_amount=has_amount, material_category=material_category
    )
    page_limit = min(limit, FEE_TEASER_LIMIT) if teaser else limit
    page = rows[offset : offset + page_limit]
    return FeeAmountsResponse(
        rows=page,
        count=len(page),
        total_available=len(rows),
        teaser=teaser,
        note=_FEE_TEASER_NOTE if teaser else None,
    )


@router.get("/fee-amounts/summary", response_model=FeeAmountsSummary)
async def fee_amounts_summary(db: AsyncSession = Depends(get_db)):
    """Open, full aggregate over the bill-sourced fee entries — the breadth teaser + chartable stat."""
    records = await _fetch_fee_rows(db, codes=None, state=None, status=None, basis=None, currency=None)
    rows = _build_fee_rows(records)  # classify all, no filtering
    bills_with_fees: set[int] = set()
    bills_with_numeric: set[int] = set()
    numeric = 0
    by_basis: dict[str, int] = {}
    by_fee_kind: dict[str, int] = {}
    by_currency: dict[str, int] = {}
    by_region: dict[str, int] = {}
    for r in rows:
        bills_with_fees.add(r.bill_id)
        if r.amount is not None:
            bills_with_numeric.add(r.bill_id)
            numeric += 1
        by_basis[r.basis or "unspecified"] = by_basis.get(r.basis or "unspecified", 0) + 1
        by_fee_kind[r.fee_kind] = by_fee_kind.get(r.fee_kind, 0) + 1
        if r.currency:
            by_currency[r.currency.upper()] = by_currency.get(r.currency.upper(), 0) + 1
        by_region[r.region] = by_region.get(r.region, 0) + 1

    def _counts(d: dict[str, int]) -> list[KeyCount]:
        return [KeyCount(key=k, count=v) for k, v in sorted(d.items(), key=lambda kv: -kv[1])]

    return FeeAmountsSummary(
        bills_with_fees=len(bills_with_fees),
        bills_with_numeric=len(bills_with_numeric),
        total_rate_entries=len(rows),
        numeric_rate_entries=numeric,
        by_basis=_counts(by_basis),
        by_fee_kind=_counts(by_fee_kind),
        by_currency=_counts(by_currency),
        by_region=_counts(by_region),
    )


@router.get("/eco-modulation", response_model=EcoModulationResponse)
async def eco_modulation(
    region: str | None = Query(default=None, description="Jurisdiction family (default: all). Non-Pro is forced to US."),
    regions: str | None = None,
    state: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, le=5000),
    offset: int = 0,
    is_pro: bool = Depends(get_optional_pro),
    db: AsyncSession = Depends(get_db),
):
    """Eco-modulation criteria (design attributes that raise/lower fees) per measure, cited. One row per
    bill. US-teaser for non-Pro; full for Pro."""
    codes, teaser = _gate_regions(_resolve_regions(region, regions), is_pro)
    clauses = [
        "b.ce_relevant = true",
        "b.compliance_details->'eco_modulation'->>'status' = 'present'",
    ]
    params: dict = {}
    if codes is not None:
        clauses.append("b.region IN :regions")
        params["regions"] = codes
    if state:
        clauses.append("b.state = :state")
        params["state"] = state.upper()
    if status:
        clauses.append("b.status = :status")
        params["status"] = status
    sql = f"""
        SELECT b.id AS bill_id, b.region, b.state, b.bill_number, b.title AS bill_title,
               b.status, b.source_url,
               b.compliance_details->'eco_modulation'->'criteria' AS criteria,
               b.compliance_details->'eco_modulation'->>'source_excerpt' AS source_excerpt
        FROM bills b
        WHERE {' AND '.join(clauses)}
        ORDER BY b.last_action_date DESC NULLS LAST, b.id
    """
    stmt = text(sql)
    if codes is not None:
        stmt = stmt.bindparams(bindparam("regions", expanding=True))
    records = [dict(m) for m in (await db.execute(stmt, params)).mappings().all()]
    all_rows = [
        EcoModulationRow(
            bill_id=m["bill_id"],
            region=m["region"],
            state=m["state"],
            bill_number=m.get("bill_number"),
            bill_title=m.get("bill_title"),
            status=m.get("status"),
            source_url=m.get("source_url"),
            criteria=_coerce_json_list(m.get("criteria")) or [],
            grounded=bool(m.get("source_excerpt")),
            source_excerpt=m.get("source_excerpt"),
        )
        for m in records
    ]
    page_limit = min(limit, FEE_TEASER_LIMIT) if teaser else limit
    page = all_rows[offset : offset + page_limit]
    return EcoModulationResponse(
        rows=page,
        count=len(page),
        total_available=len(all_rows),
        teaser=teaser,
        note=_FEE_TEASER_NOTE if teaser else None,
    )


def _parse_bill_ids(raw: str | None) -> list[int] | None:
    """CSV of bill ids -> int list, capped. Non-numeric entries are dropped rather than 422-ing, so a
    stray value can't break the deadline modal's lookup. Returns None when nothing usable was given."""
    if not raw:
        return None
    ids = [int(p) for p in (s.strip() for s in raw.split(",")) if p.isdigit()]
    return ids[:PATHWAY_BILL_ID_LIMIT] or None


@router.get("/pathways", response_model=list[CompliancePathwaySummary])
async def list_pathways(
    state: str | None = Query(default=None, description="Sub-jurisdiction code (e.g. CA, EU)"),
    region: str | None = Query(default=None, description="Jurisdiction family: US (default), EU, or all"),
    regions: str | None = Query(default=None, description="CSV of codes (multi-select); wins over `region`."),
    bill_ids: str | None = Query(
        default=None,
        description="CSV of bill ids. Scopes to exactly those bills and drops the US region default — "
                    "the per-bill lookup the deadline modal / bill page use.",
    ),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(CompliancePathway, Bill, ComplianceEntity)
        .join(Bill, Bill.id == CompliancePathway.bill_id)
        .outerjoin(ComplianceEntity, ComplianceEntity.id == CompliancePathway.entity_id)
        .order_by(
            CompliancePathway.next_deadline_date.is_(None),
            CompliancePathway.next_deadline_date,
            Bill.bill_number,
        )
    )
    # An explicit bill_ids lookup is its own scope — the caller already knows which laws it wants, so
    # the US region default must NOT silently drop a foreign bill's pathway.
    ids = _parse_bill_ids(bill_ids)
    if ids is not None:
        q = q.where(CompliancePathway.bill_id.in_(ids))
    # Region scoping: a `regions` CSV or a single `region` win; a bare caller (state-only, no region)
    # keeps the historical US default so existing state-page fetches are unaffected. "all" (or an
    # all-containing CSV) drops the filter entirely — every region's pathways (now that they exist).
    if region is not None or regions is not None:
        codes = _resolve_regions(region, regions)
        if codes:
            q = q.where(Bill.region.in_(codes))
    elif ids is None:
        q = q.where(Bill.region == "US")
    if state:
        q = q.where(Bill.state == state.upper())
    rows = (await db.execute(q)).all()
    out: list[CompliancePathwaySummary] = []
    for p, bill, entity in rows:
        out.append(
            CompliancePathwaySummary(
                bill_id=p.bill_id,
                bill_number=bill.bill_number,
                bill_title=bill.title,
                material_categories=bill.material_categories,
                management_model=p.management_model,
                action_type=p.action_type,
                action_summary=p.action_summary,
                registration_url=p.registration_url,
                next_deadline_date=p.next_deadline_date,
                has_fee=p.has_fee,
                entity=ComplianceEntityRef.model_validate(entity) if entity else None,
            )
        )
    return out
