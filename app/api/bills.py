from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Integer, and_, case, func, literal_column, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CAP_INSIGHTS_IMPACT, get_optional_capability, get_optional_pro
from app.classification.sonnet_extractor import EXTRACTION_VERSION
from app.database import get_db
from app.models import (
    Bill,
    BillOutcome,
    BillText,
    ComplianceDeadline,
    LitigationCase,
    LitigationEvent,
)
from app.schemas import (
    BillDetail,
    BillFullText,
    BillOutcomeSummary,
    BillSearchHit,
    BillStancePoint,
    BillSummary,
    BillTimelinePoint,
    CollectionTargetBasisPoint,
    DeadlineStats,
    DeadlineSummary,
    InstrumentMaterialCell,
    LawsInForcePoint,
    LitigationCaseSummary,
    RegionCoverage,
    StateMapSummary,
    TextCoverageStats,
)

router = APIRouter(prefix="/bills", tags=["bills"])

# The Upcoming Deadlines list is the Pro product. Anonymous/free callers get true aggregate counts
# (DeadlineStats, ungated — they drive conversion) plus only the soonest few rows as a taste; the full
# merged list is served only to a verified Pro seat. See docs/SECURITY_ASSESSMENT.md C-1.
DEADLINE_TEASER_LIMIT = 5

# Same shape for the documented-outcomes feed (CAP_INSIGHTS_IMPACT): the homepage ticker rotates a
# handful, the Insights impact table is the full set.
OUTCOME_TEASER_LIMIT = 6
DEADLINE_PAST_CAP_DAYS = 5 * 365


def _lit_subquery():
    return (
        select(
            LitigationCase.related_law_id,
            func.count(LitigationCase.id).label("case_count"),
            func.max(LitigationCase.preemption_risk).label("max_risk"),
        )
        # Screened-relevant only. A bill's litigation badge is a claim that its law is under
        # challenge; before the relevance gate, a bill matched to an unrelated docket carried that
        # badge — and its preemption risk — on no evidence at all.
        .where(LitigationCase.case_status == "active", LitigationCase.ce_relevant.is_(True))
        .group_by(LitigationCase.related_law_id)
        .subquery()
    )


# The eight extracted compliance dimensions filterable from the bills list (must match the envelope
# keys in compliance_details — see app/classification/sonnet_extractor.py). Whitelisted so the
# ?dimensions filter can only reach known JSONB keys.
_DIMENSION_KEYS = {
    "eco_modulation", "recycled_content", "penalties", "collection_targets",
    "pro_structure", "bans_restrictions", "fee_amounts", "labeling",
}


@router.get("", response_model=list[BillSummary])
async def list_bills(
    state: str | None = None,
    # Jurisdiction family filter. Omitted = US only (preserves the existing US-only dashboard
    # behavior); "EU" returns EU rows; "all" returns every region. See migration 031.
    region: str | None = None,
    # Multi-region filter (CSV of codes, e.g. "US,EU,FR"; "all"/empty = every region) — the global
    # region filter passes this. Takes precedence over `region` when present. See _parse_regions.
    regions: str | None = None,
    status: str | None = None,
    material_category: str | None = None,
    ce_relevant: bool | None = None,
    min_confidence: float = 0.0,
    urgency: str | None = None,
    instrument_type: str | None = None,
    # policy_stance + year power the Insights chart drill-down: a (year, status) timeline point or a
    # (year, stance) momentum bar maps to exactly these filters, so clicking it lists the bills behind
    # it (each with its source_url). `year` filters on the year of status_date — the same bucketing the
    # timeline/momentum endpoints use — so the drill-down list matches the bar's count.
    policy_stance: str | None = None,
    # CSV of compliance-dimension keys (e.g. "eco_modulation,collection_targets"); a bill matches only
    # if EACH listed dimension is `present` in its compliance_details. See _DIMENSION_KEYS.
    dimensions: str | None = None,
    year: int | None = None,
    # year_from/year_to bound status_date year — the per-cycle (biennium) drill-down passes the two
    # years of a biennium so a cycle bar lists exactly its bills.
    year_from: int | None = None,
    year_to: int | None = None,
    # "Search by date" (docs/SCOPE_FACET_AND_MATERIAL_NAVIGATION.md §9). Two dates a CSO uses
    # differently: effective_* range the extracted compliance date (when an obligation takes effect —
    # forward planning), activity_* range coalesce(last_action_date, status_date) (when a bill moved —
    # monitoring). Both are inclusive DATE bounds. effective_date is day-precise by construction; the
    # activity range applies a year-overlap rule for year-only foreign rows (see below).
    effective_from: date | None = None,
    effective_to: date | None = None,
    activity_from: date | None = None,
    activity_to: date | None = None,
    limit: int = Query(default=100, le=5000),
    offset: int = 0,
    response: Response = None,  # noqa: B008 — FastAPI injects; used only to set Cache-Control
    db: AsyncSession = Depends(get_db),
):
    # Shared-cacheable for 5 minutes. This is the hottest endpoint on the site — the homepage asks for
    # the whole relevant corpus on every load — and it was going out with no Cache-Control at all, so
    # every visitor round-tripped to Postgres for a corpus that only changes on an ingestion cadence.
    # A traffic spike therefore hit the DB once per visitor for identical bytes.
    #
    # 300s is chosen against how the data actually moves (ingestion is hourly at best), not against
    # how fresh it feels: a bill that appears five minutes late is invisible to a reader, while a
    # thundering herd on a shared link is not. stale-while-revalidate lets a CDN keep serving during
    # the refresh instead of stampeding the origin at expiry.
    if response is not None:
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"

    lit_sub = _lit_subquery()
    q = (
        select(Bill, func.coalesce(lit_sub.c.case_count, 0).label("case_count"), lit_sub.c.max_risk)
        .outerjoin(lit_sub, Bill.id == lit_sub.c.related_law_id)
    )
    # Default to US so existing callers (the US dashboard) are unaffected by EU rows landing in the
    # same table. region="all" opts into every region; an explicit code (e.g. "EU") filters to it.
    # The multi-region `regions` CSV (global filter) wins when present: a code list narrows to those,
    # "all"/empty drops the filter entirely.
    if regions is not None:
        codes = _parse_regions(regions)
        if codes:
            q = q.where(Bill.region.in_(codes))
    elif region is None:
        q = q.where(Bill.region == "US")
    elif region.lower() != "all":
        q = q.where(Bill.region == region.upper())
    if state:
        q = q.where(Bill.state == state.upper())
    if status:
        q = q.where(Bill.status == status)
    if ce_relevant is not None:
        q = q.where(Bill.ce_relevant == ce_relevant)
    if min_confidence > 0:
        q = q.where(Bill.confidence_score >= min_confidence)
    if material_category:
        q = q.where(Bill.material_categories.contains([material_category]))
    if urgency:
        q = q.where(Bill.urgency == urgency)
    if instrument_type:
        # Match the instrument anywhere in the law's set (not just its primary), so filtering e.g.
        # "recycled_content" also surfaces EPR laws that carry a recycled-content mandate. Falls back
        # to the primary for any row whose instrument_types wasn't backfilled.
        q = q.where(
            Bill.instrument_types.contains([instrument_type])
            | (Bill.instrument_types.is_(None) & (Bill.instrument_type == instrument_type))
        )
    if policy_stance:
        q = q.where(Bill.policy_stance == policy_stance)
    if dimensions:
        # AND semantics: narrow to bills where every requested dimension is present (a bill that both
        # eco-modulates AND sets collection targets). Unknown keys are ignored (whitelist).
        for dim in {d.strip() for d in dimensions.split(",")} & _DIMENSION_KEYS:
            q = q.where(Bill.compliance_details[dim]["status"].astext == "present")
    if year is not None:
        q = q.where(func.extract("year", Bill.status_date) == year)
    if year_from is not None:
        q = q.where(func.extract("year", Bill.status_date) >= year_from)
    if year_to is not None:
        q = q.where(func.extract("year", Bill.status_date) <= year_to)
    if effective_from is not None:
        q = q.where(Bill.effective_date >= effective_from)
    if effective_to is not None:
        q = q.where(Bill.effective_date <= effective_to)
    if activity_from is not None or activity_to is not None:
        # Activity range on coalesce(last_action_date, status_date). A year-only row (foreign: no
        # last_action_date + a Jan-1 status_date placeholder) matches on YEAR overlap, so a mid-year
        # range still includes a bill dated only to that year instead of dropping it on the fake Jan-1.
        # Rows with no date at all (both NULL) fall out — the NULL comparisons resolve to false. §9b.
        activity = func.coalesce(Bill.last_action_date, Bill.status_date)
        is_year_only = and_(
            Bill.last_action_date.is_(None),
            func.extract("month", Bill.status_date) == 1,
            func.extract("day", Bill.status_date) == 1,
        )
        status_year = func.extract("year", Bill.status_date)
        if activity_from is not None:
            q = q.where(
                or_(
                    and_(~is_year_only, activity >= activity_from),
                    and_(is_year_only, status_year >= activity_from.year),
                )
            )
        if activity_to is not None:
            q = q.where(
                or_(
                    and_(~is_year_only, activity <= activity_to),
                    and_(is_year_only, status_year <= activity_to.year),
                )
            )
    q = q.order_by(Bill.last_action_date.desc().nullslast()).limit(limit).offset(offset)
    rows = (await db.execute(q)).all()
    results = []
    for row in rows:
        s = BillSummary.model_validate(row.Bill)
        s.litigation_case_count = row.case_count
        s.max_preemption_risk = row.max_risk
        results.append(s)
    return results


# Full-text search highlighting. <mark> wraps the matched term; ts_headline joins fragments on this
# sentinel (the default ' ... ' is ambiguous with real ellipses in bill text) and we split on it.
# 'english' is passed as a SQL literal, not a bind param, so Postgres resolves it as a regconfig
# rather than mistaking it for the document/query argument.
_ENGLISH = literal_column("'english'")
_MARK_START = "<mark>"
_MARK_END = "</mark>"
_FRAG_SEP = "[[[FRAG]]]"
_HEADLINE_OPTS = (
    f"StartSel={_MARK_START},StopSel={_MARK_END},"
    f"MaxFragments=3,MinWords=5,MaxWords=18,FragmentDelimiter={_FRAG_SEP}"
)


@router.get("/search", response_model=list[BillSearchHit])
async def search_bills(
    q: str = Query(..., min_length=2, description="Full-text query; supports quoted phrases and OR."),
    # Same multi-region semantics as GET /bills: CSV of codes narrows, "all"/empty = every region.
    # Scoping happens BEFORE the rank limit — without it a region-filtered explorer asking for a term
    # its own jurisdiction never uses would get `limit` out-of-region hits instead of an honest empty
    # result (the English tsvector ranks US/EU text highest, so the leak is systematically Western).
    regions: str | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Full-text search over the persisted bill text (`bill_texts`), returning each matching bill with
    `ts_headline` snippets where the term appears. Distinct from `GET /bills`, which is the
    snapshot-baked metadata list and never carries full text. Ranked by `ts_rank`; only ce_relevant,
    text-indexed bills can match, so a term absent from a bill's summary is still found in its text."""
    tsq = func.websearch_to_tsquery(_ENGLISH, q)
    lit_sub = _lit_subquery()
    headline = func.ts_headline(_ENGLISH, BillText.text, tsq, _HEADLINE_OPTS)
    rank = func.ts_rank(BillText.text_tsv, tsq)
    stmt = (
        select(
            Bill,
            func.coalesce(lit_sub.c.case_count, 0).label("case_count"),
            lit_sub.c.max_risk,
            headline.label("headline"),
        )
        .join(BillText, BillText.bill_id == Bill.id)
        .outerjoin(lit_sub, Bill.id == lit_sub.c.related_law_id)
        .where(Bill.ce_relevant.is_(True))
        .where(BillText.text_tsv.op("@@")(tsq))
        .order_by(rank.desc())
    )
    region_codes = _parse_regions(regions)
    if region_codes:
        stmt = stmt.where(Bill.region.in_(region_codes))
    stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).all()
    hits: list[BillSearchHit] = []
    for row in rows:
        hit = BillSearchHit.model_validate(row.Bill)
        hit.litigation_case_count = row.case_count
        hit.max_preemption_risk = row.max_risk
        hit.snippets = [s.strip() for s in (row.headline or "").split(_FRAG_SEP) if s.strip()]
        hit.text_indexed = True
        hits.append(hit)
    return hits


@router.get("/text-coverage", response_model=TextCoverageStats)
async def bill_text_coverage(by_region: bool = False, db: AsyncSession = Depends(get_db)):
    """Counts of ce_relevant bills with vs. without indexed full text, so the deep-search UI can say
    'covers N of M bills' — keeping an empty full-text result honest (not in our index ≠ nonexistent).
    ?by_region=true adds a per-region breakdown incl. how many are analyzed at the current dimension
    schema version, so an 'across all bills' claim can be qualified per region instead of overstated."""
    total = await db.scalar(
        select(func.count()).select_from(Bill).where(Bill.ce_relevant.is_(True))
    )
    indexed = await db.scalar(
        select(func.count())
        .select_from(BillText)
        .join(Bill, Bill.id == BillText.bill_id)
        .where(Bill.ce_relevant.is_(True), BillText.text.isnot(None))
    )
    regions: list[RegionCoverage] | None = None
    if by_region:
        has_text = BillText.text.isnot(None)
        # extraction_version is a JSONB key on compliance_details; NULL/missing coalesces to 0 (< current).
        analyzed = func.coalesce(
            Bill.compliance_details["extraction_version"].as_integer(), 0
        ) >= EXTRACTION_VERSION
        rows = (
            await db.execute(
                select(
                    Bill.region,
                    func.count().label("total"),
                    func.count().filter(has_text).label("indexed"),
                    func.count().filter(has_text, analyzed).label("analyzed"),
                )
                .select_from(Bill)
                .outerjoin(BillText, BillText.bill_id == Bill.id)
                .where(Bill.ce_relevant.is_(True))
                .group_by(Bill.region)
                .order_by(func.count().desc())
            )
        ).all()
        regions = [
            RegionCoverage(
                region=r.region or "?", total_bills=r.total,
                indexed_bills=r.indexed, analyzed_bills=r.analyzed,
            )
            for r in rows
        ]
    return TextCoverageStats(indexed_bills=indexed or 0, total_bills=total or 0, by_region=regions)


@router.get("/map-summary", response_model=list[StateMapSummary])
async def get_map_summary(
    region: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    # The map is per-jurisdiction within one region; default US (the US states choropleth). EU uses a
    # member-states view, not this endpoint, until Phase B. region="all" returns every region's codes.
    q = (
        select(
            Bill.state,
            func.count().filter(Bill.status == "enacted").label("enacted_count"),
            func.count()
            .filter(Bill.status.in_(["introduced", "in_committee", "passed_chamber"]))
            .label("pending_count"),
            func.count().filter(Bill.ce_relevant).label("total_relevant"),
        )
        .where(Bill.ce_relevant == True)
        .group_by(Bill.state)
    )
    if region is None:
        q = q.where(Bill.region == "US")
    elif region.lower() != "all":
        q = q.where(Bill.region == region.upper())
    rows = (await db.execute(q)).all()
    return [
        StateMapSummary(
            state=row.state,
            enacted_count=row.enacted_count,
            pending_count=row.pending_count,
            total_relevant=row.total_relevant,
            material_categories=[],
        )
        for row in rows
    ]


def _parse_regions(regions: str | None) -> list[str] | None:
    """Parse the Insights `regions` CSV query param into upper-cased jurisdiction codes.

    Returns None for "all regions" (empty, missing, or containing "all") — i.e. no region filter.
    The Insights views below always GROUP BY region so the frontend can render one series per region
    in compare mode; the param only narrows WHICH regions are returned.
    """
    if not regions:
        return None
    codes = [r.strip().upper() for r in regions.split(",") if r.strip()]
    if not codes or "ALL" in codes:
        return None
    return codes


@router.get("/timeline", response_model=list[BillTimelinePoint])
async def get_bill_timeline(
    instrument_type: str | None = None,
    material_category: str | None = None,
    regions: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Per-year, per-status, per-region counts of EPR-relevant bills, bucketed by year of status_date.

    Powers the Insights timeline: cumulate the `enacted` series for "laws on the books over
    time", and toggle the other statuses to see the "shots on goal" (introductions) behind them.
    Grouped by region so the chart can compare jurisdictions; `regions` (CSV) narrows the set.
    """
    year = func.extract("year", Bill.status_date)
    q = (
        select(year.cast(Integer).label("year"), Bill.status, Bill.region, func.count().label("count"))
        .where(Bill.ce_relevant == True)
        .where(Bill.status_date.isnot(None))
        .where(Bill.status.isnot(None))
        .group_by("year", Bill.status, Bill.region)
        .order_by("year")
    )
    if instrument_type:
        q = q.where(Bill.instrument_type == instrument_type)
    if material_category:
        q = q.where(Bill.material_categories.contains([material_category]))
    region_codes = _parse_regions(regions)
    if region_codes:
        q = q.where(Bill.region.in_(region_codes))
    rows = (await db.execute(q)).all()
    return [
        BillTimelinePoint(year=row.year, status=row.status, count=row.count, region=row.region)
        for row in rows
    ]


@router.get("/stance-momentum", response_model=list[BillStancePoint])
async def get_stance_momentum(
    instrument_type: str | None = None,
    material_category: str | None = None,
    min_confidence: float = 0.7,
    regions: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Per-year, per-region counts of EPR-relevant bills by policy_stance — the Insights "momentum" view.

    Answers "is the field advancing or being rolled back?" by bucketing each bill under the year of
    its most recent status change and its stance (advances / weakens / neutral). A confidence floor
    (default 0.7) keeps low-confidence classifications out of the aggregate, since stance is the
    noisiest classifier axis. neutral is included in the response; the chart leaves it off the axis.
    Grouped by region so the chart can compare jurisdictions; `regions` (CSV) narrows the set.
    """
    year = func.extract("year", Bill.status_date)
    q = (
        select(
            year.cast(Integer).label("year"),
            Bill.policy_stance,
            Bill.region,
            func.count().label("count"),
        )
        .where(Bill.ce_relevant == True)
        .where(Bill.status_date.isnot(None))
        .where(Bill.policy_stance.isnot(None))
        .where(Bill.confidence_score >= min_confidence)
        .group_by("year", Bill.policy_stance, Bill.region)
        .order_by("year")
    )
    if instrument_type:
        q = q.where(Bill.instrument_type == instrument_type)
    if material_category:
        q = q.where(Bill.material_categories.contains([material_category]))
    region_codes = _parse_regions(regions)
    if region_codes:
        q = q.where(Bill.region.in_(region_codes))
    rows = (await db.execute(q)).all()
    return [
        BillStancePoint(year=row.year, stance=row.policy_stance, count=row.count, region=row.region)
        for row in rows
    ]


@router.get("/instrument-material-matrix", response_model=list[InstrumentMaterialCell])
async def get_instrument_material_matrix(
    min_confidence: float = 0.7,
    regions: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Counts of EPR-relevant bills per (instrument_type × material_category × region) — the Insights
    coverage heatmap. material_categories is a JSONB array, so it's unnested: a bill tagging three
    materials lands in three cells. Cells with no bills simply have no row (the white space). Grouped
    by region so the chart can compare jurisdictions; `regions` (CSV) narrows the set.

    `status` (e.g. "enacted") filters to a single bill status. The charts default to enacted-only so
    US regions — which carry a large introduced-bill pipeline — are compared on the same footing as
    foreign/EU regions, which we track only once they're law.
    """
    # Unnest the JSONB material array as a LATERAL set-returning function joined per bill row.
    material = func.jsonb_array_elements_text(Bill.material_categories).table_valued("value").lateral()
    q = (
        select(
            Bill.instrument_type.label("instrument_type"),
            material.c.value.label("material_category"),
            Bill.region,
            func.count().label("count"),
        )
        .select_from(Bill)
        .join(material, true())
        .where(Bill.ce_relevant == True)
        .where(Bill.instrument_type.isnot(None))
        .where(Bill.material_categories.isnot(None))
        .where(Bill.confidence_score >= min_confidence)
        .group_by(Bill.instrument_type, material.c.value, Bill.region)
    )
    if status:
        q = q.where(Bill.status == status)
    region_codes = _parse_regions(regions)
    if region_codes:
        q = q.where(Bill.region.in_(region_codes))
    rows = (await db.execute(q)).all()
    return [
        InstrumentMaterialCell(
            instrument_type=row.instrument_type,
            material_category=row.material_category,
            count=row.count,
            region=row.region,
        )
        for row in rows
    ]


@router.get("/collection-target-basis", response_model=list[CollectionTargetBasisPoint])
async def get_collection_target_basis(
    regions: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Distribution of how collection/recovery targets are *measured* — by weight, units, value
    recovered (critical metals), or material-specific — across EPR-relevant bills, per region.
    Unnests compliance_details->collection_targets->targets (a JSONB array), so a bill with several
    targets contributes several rows. Only bills whose collection_targets envelope is `present` count.
    Grouped by region so the chart can compare jurisdictions; `regions` (CSV) narrows the set."""
    targets = func.jsonb_array_elements(
        Bill.compliance_details["collection_targets"]["targets"]
    ).table_valued("value").lateral()
    # targets.c.value is an untyped table-valued column, so pull the field with jsonb_extract_path_text
    # rather than the getitem operator (which needs a JSONB-typed expression).
    basis = func.jsonb_extract_path_text(targets.c.value, "basis")
    q = (
        select(basis.label("basis"), Bill.region, func.count().label("count"))
        .select_from(Bill)
        .join(targets, true())
        .where(Bill.ce_relevant == True)
        .where(Bill.compliance_details["collection_targets"]["status"].astext == "present")
        .group_by(basis, Bill.region)
        .order_by(func.count().desc())
    )
    region_codes = _parse_regions(regions)
    if region_codes:
        q = q.where(Bill.region.in_(region_codes))
    rows = (await db.execute(q)).all()
    return [
        CollectionTargetBasisPoint(basis=row.basis or "unspecified", count=row.count, region=row.region)
        for row in rows
    ]


@router.get("/laws-in-force", response_model=list[LawsInForcePoint])
async def get_laws_in_force(
    regions: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Per-year, per-region counts of enacted CE laws that came INTO FORCE that year.

    The year is the extracted `effective_date` (the only date foreign regulations carry — they have no
    introduced→enacted pipeline, so the timeline/momentum charts are empty for them), falling back to
    `status_date` for US enacted laws that weren't Sonnet-extracted. The frontend cumulates these into
    a "laws on the books over time" line per region — the momentum view that works cross-jurisdiction.
    """
    # In-force year = effective_date's year when it's a well-formed date, else the status_date year.
    # A JSONB text cast to date can throw on malformed values, so guard with a regex and take the
    # leading YYYY directly rather than ::date.
    eff_year = case(
        (Bill.compliance_details["effective_date"].astext.op("~")(r"^\d{4}-\d{2}-\d{2}"),
         func.substring(Bill.compliance_details["effective_date"].astext, 1, 4).cast(Integer)),
        else_=None,
    )
    yr = func.coalesce(eff_year, func.extract("year", Bill.status_date).cast(Integer)).label("year")
    q = (
        select(yr, Bill.region, func.count().label("count"))
        .where(Bill.ce_relevant == True)
        .where(Bill.status == "enacted")
        .group_by("year", Bill.region)
        .having(yr.isnot(None))
        .order_by("year")
    )
    region_codes = _parse_regions(regions)
    if region_codes:
        q = q.where(Bill.region.in_(region_codes))
    rows = (await db.execute(q)).all()
    return [LawsInForcePoint(year=row.year, region=row.region, count=row.count) for row in rows]


@router.get("/outcomes", response_model=list[BillOutcomeSummary])
async def list_bill_outcomes(
    direction: str | None = None,
    state: str | None = None,
    region: str | None = None,  # US (default), EU, or "all"
    reviewed_only: bool = True,
    has_impact: bool = Depends(get_optional_capability(CAP_INSIGHTS_IMPACT)),
    db: AsyncSession = Depends(get_db),
):
    """Documented real-world outcomes of enacted laws — the Insights "Real-World Impact" feed.

    Each row is a curated, source-backed effect (positive | negative | mixed). Ordered most-recent
    first by as_of_date so the freshest documented impacts lead. `reviewed_only` defaults TRUE so this
    PUBLIC feed only ever exposes human-vetted figures — unvetted candidates from
    scripts/propose_bill_outcomes.py (reviewed=false) are invisible here and live only in the
    admin review console (GET /admin/outcomes). Do not flip the default without an admin gate.
    """
    q = select(BillOutcome)
    if direction:
        q = q.where(BillOutcome.direction == direction)
    if region is None:
        q = q.where(BillOutcome.region == "US")
    elif region.lower() != "all":
        q = q.where(BillOutcome.region == region.upper())
    if state:
        q = q.where(BillOutcome.state == state.upper())
    if reviewed_only:
        q = q.where(BillOutcome.reviewed.is_(True))
    q = q.order_by(BillOutcome.as_of_date.desc().nullslast(), BillOutcome.id.desc())
    # The full documented-impact set is the Insights "Real-World Impact" table (CAP_INSIGHTS_IMPACT).
    # Everyone else gets the newest few, which is exactly what the free homepage ticker rotates
    # through — so the teaser is the free surface's real requirement, not a degraded version of it.
    if not has_impact:
        q = q.limit(OUTCOME_TEASER_LIMIT)
    rows = (await db.execute(q)).scalars().all()
    return [BillOutcomeSummary.model_validate(r) for r in rows]


@router.get("/{bill_id}", response_model=BillDetail)
async def get_bill(
    bill_id: int,
    db: AsyncSession = Depends(get_db),
):
    lit_sub = _lit_subquery()
    q = (
        select(Bill, func.coalesce(lit_sub.c.case_count, 0).label("case_count"), lit_sub.c.max_risk)
        .outerjoin(lit_sub, Bill.id == lit_sub.c.related_law_id)
        .where(Bill.id == bill_id)
    )
    # one_or_none, not one: an unknown id is a client error, not a server fault. `.one()` raised
    # NoResultFound here, which surfaced as a bare 500 — so every typo'd or stale bill id looked like
    # the API was broken rather than the id being wrong.
    row = (await db.execute(q)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")
    d = BillDetail.model_validate(row.Bill)
    d.litigation_case_count = row.case_count
    d.max_preemption_risk = row.max_risk
    # compliance_details rides along in full, for everyone. The gate is on BREADTH, not depth: one
    # bill's record is free (it's a reading of statute text we already serve free at /bills/{id}/text
    # and publish as HTML on /bill/{id}/{slug}), while every CROSS-bill view stays paid — the list
    # endpoint omits the field entirely (BillSummary), /bills/deadlines/upcoming serves non-Pro a
    # teaser, and the /compliance fee-row endpoints keep their jurisdiction-breadth gate. That is the
    # product: the corpus-wide view, not any single record.
    # This is the C-1 remediation as written (docs/SECURITY_ASSESSMENT.md: "it lives only on per-bill
    # BillDetail now"); the later non-Pro drop on this endpoint has been deliberately removed.
    return d


@router.get("/{bill_id}/text", response_model=BillFullText)
async def get_bill_text(bill_id: int, db: AsyncSession = Depends(get_db)):
    """The bill's persisted full statute text (the `bill_texts` side table), read by id. Free — a
    single-bill text read is not the bulk harvest that's gated. Returns text=None when we haven't
    ingested this bill's text yet, so the modal falls back to its source link rather than an empty box."""
    row = (
        await db.execute(
            select(BillText.text, BillText.char_len, BillText.source).where(
                BillText.bill_id == bill_id
            )
        )
    ).first()
    if row is None:
        return BillFullText(bill_id=bill_id)
    return BillFullText(bill_id=bill_id, text=row.text, char_len=row.char_len, source=row.source)


@router.get("/{bill_id}/litigation-cases", response_model=list[LitigationCaseSummary])
async def get_bill_litigation_cases(bill_id: int, db: AsyncSession = Depends(get_db)):
    event_count_sub = (
        select(LitigationEvent.case_id, func.count(LitigationEvent.id).label("event_count"))
        .group_by(LitigationEvent.case_id)
        .subquery()
    )
    q = (
        select(LitigationCase, func.coalesce(event_count_sub.c.event_count, 0).label("event_count"))
        .outerjoin(event_count_sub, LitigationCase.id == event_count_sub.c.case_id)
        .where(LitigationCase.related_law_id == bill_id, LitigationCase.ce_relevant.is_(True))
        .order_by(LitigationCase.preemption_risk.desc().nullslast())
    )
    rows = (await db.execute(q)).all()
    results = []
    for row in rows:
        s = LitigationCaseSummary.model_validate(row.LitigationCase)
        s.event_count = row.event_count
        results.append(s)
    return results


def _parse_iso_date(val) -> date | None:
    if not isinstance(val, str) or not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


async def _merge_deadlines(
    db: AsyncSession, *, days_ahead: int, state: str | None, include_past: bool,
    region: str | None = None, regions: list[str] | None = None,
) -> list[DeadlineSummary]:
    """The full deadline set the Upcoming Deadlines page needs, merged server-side: explicit
    ComplianceDeadline rows plus the implementation/enforcement dates the classifier pulled into each
    bill's compliance_details (effective_date, compliance_date, and the deadlines[] array). Deduped by
    (state, date, type) with the explicit rows winning. This used to be done client-side by pulling
    every bill's compliance_details to the browser — the leak C-1 closed."""
    today = date.today()
    horizon = today + timedelta(days=days_ahead)
    floor = today - timedelta(days=DEADLINE_PAST_CAP_DAYS) if include_past else today
    state_u = state.upper() if state else None
    # Region scoping, in precedence order:
    #   regions=[..]  -> multi-select: rows/bills whose region is IN the list (the deadline page's
    #                    RegionFilter uses this for 2+ picks).
    #   region="all"  -> span every region (the page's "All regions" default).
    #   region=CODE   -> a single region.
    #   (neither)     -> default US, so a bare caller (e.g. JurisdictionProfile) keeps the US calendar
    #                    and isn't polluted by EU rows.
    regions_u = [r.upper() for r in regions if r] if regions else None
    region_u = None if (regions_u or (region and region.lower() == "all")) else (region or "US").upper()

    seen: set[tuple] = set()
    out: list[DeadlineSummary] = []

    def push(*, id_, rg, st, dtype, ddate, desc, who, bill_id, bill_number, bill_title, materials):
        if ddate is None or ddate < floor or ddate > horizon:
            return
        if state_u and (st or "").upper() != state_u:
            return
        key = (rg, st, ddate.isoformat(), dtype)
        if key in seen:
            return
        seen.add(key)
        out.append(
            DeadlineSummary(
                id=id_, region=rg or "US", state=st, deadline_type=dtype, deadline_date=ddate,
                description=desc, who_affected=who, bill_id=bill_id, bill_number=bill_number,
                bill_title=bill_title, material_categories=materials,
            )
        )

    # 1. Explicit ComplianceDeadline rows (these win on dedup — they're the curated ones).
    q = select(ComplianceDeadline, Bill.bill_number, Bill.title, Bill.material_categories).outerjoin(
        Bill, ComplianceDeadline.bill_id == Bill.id
    )
    if regions_u:
        q = q.where(ComplianceDeadline.region.in_(regions_u))
    elif region_u:
        q = q.where(ComplianceDeadline.region == region_u)
    for row in (await db.execute(q)).all():
        cd = row.ComplianceDeadline
        push(
            id_=cd.id, rg=cd.region, st=cd.state, dtype=cd.deadline_type, ddate=cd.deadline_date,
            desc=cd.description, who=cd.who_affected, bill_id=cd.bill_id,
            bill_number=row.bill_number, bill_title=row.title, materials=row.material_categories,
        )

    # 2. Dates embedded in each EPR bill's compliance_details.
    bq = select(Bill).where(Bill.ce_relevant == True).where(Bill.compliance_details.isnot(None))  # noqa: E712
    if regions_u:
        bq = bq.where(Bill.region.in_(regions_u))
    elif region_u:
        bq = bq.where(Bill.region == region_u)
    for bill in (await db.execute(bq)).scalars().all():
        details = bill.compliance_details or {}
        for cd in details.get("deadlines") or []:
            if not isinstance(cd, dict):
                continue
            push(
                id_=-1, rg=bill.region, st=bill.state, dtype=cd.get("type") or "compliance",
                ddate=_parse_iso_date(cd.get("date")), desc=cd.get("description"), who=None,
                bill_id=bill.id, bill_number=bill.bill_number, bill_title=bill.title,
                materials=bill.material_categories,
            )
        push(
            id_=-1, rg=bill.region, st=bill.state, dtype="effective", ddate=_parse_iso_date(details.get("effective_date")),
            desc=f"{bill.bill_number or 'Bill'} takes effect", who=None, bill_id=bill.id,
            bill_number=bill.bill_number, bill_title=bill.title, materials=bill.material_categories,
        )
        push(
            id_=-1, rg=bill.region, st=bill.state, dtype="compliance", ddate=_parse_iso_date(details.get("compliance_date")),
            desc=f"{bill.bill_number or 'Bill'} compliance date", who=None, bill_id=bill.id,
            bill_number=bill.bill_number, bill_title=bill.title, materials=bill.material_categories,
        )

    out.sort(key=lambda d: d.deadline_date)
    return out


def _scope_filter(
    rows: list[DeadlineSummary], *, materials: list[str], states: list[str]
) -> list[DeadlineSummary]:
    """Mirror the frontend deadlineInScope: empty dimensions match all; a deadline with no known
    materials is never excluded on the material axis (better to surface than silently hide)."""
    out = rows
    if states:
        want = {s.upper() for s in states}
        out = [d for d in out if (d.state or "").upper() in want]
    if materials:
        want_m = set(materials)
        out = [
            d for d in out
            if not (d.material_categories or []) or any(c in want_m for c in d.material_categories)
        ]
    return out


def _csv(val: str | None) -> list[str]:
    return [v for v in (val or "").split(",") if v]


@router.get("/deadlines/upcoming", response_model=list[DeadlineSummary])
async def list_upcoming_deadlines(
    days_ahead: int = 90,
    state: str | None = None,
    region: str | None = None,  # US (default), EU, or "all"
    regions: str | None = None,  # csv of region codes (multi-select); takes precedence over `region`
    materials: str | None = None,  # csv; scopes the FREE teaser so the taste is relevant (Pro ignores)
    states: str | None = None,  # csv; ditto
    is_pro: bool = Depends(get_optional_pro),
    db: AsyncSession = Depends(get_db),
):
    """Pro seats get the full merged deadline list (incl. up to 5 years of past dates so the page's
    "include past" toggle works client-side). Everyone else gets the soonest few upcoming rows as a
    teaser — the full calendar is the paid product. Counts for the metric cards come from
    /deadlines/summary, which stays public."""
    merged = await _merge_deadlines(db, days_ahead=days_ahead, state=state, include_past=is_pro,
                                    region=region, regions=_csv(regions))
    if is_pro:
        return merged
    today = date.today()
    upcoming = [d for d in merged if d.deadline_date >= today]
    scoped = _scope_filter(upcoming, materials=_csv(materials), states=_csv(states))
    return scoped[:DEADLINE_TEASER_LIMIT]


@router.get("/deadlines/summary", response_model=DeadlineStats)
async def deadlines_summary(
    days_ahead: int = 1095,
    state: str | None = None,
    region: str | None = None,  # US (default), EU, or "all"
    regions: str | None = None,  # csv of region codes (multi-select); takes precedence over `region`
    materials: str | None = None,
    states: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Ungated aggregate counts (total/within-30/within-90/nearest + which states), optionally scoped
    to the reader's materials/states. Powers the metric cards and the scoped deadline banner for free
    visitors without handing over the deadline rows themselves."""
    merged = await _merge_deadlines(db, days_ahead=days_ahead, state=state, include_past=False,
                                    region=region, regions=_csv(regions))
    scoped = _scope_filter(merged, materials=_csv(materials), states=_csv(states))  # already upcoming-only
    today = date.today()
    within_30 = sum(1 for d in scoped if (d.deadline_date - today).days <= 30)
    within_90 = sum(1 for d in scoped if (d.deadline_date - today).days <= 90)
    near_states = sorted({d.state for d in scoped if d.state and (d.deadline_date - today).days <= 90})
    return DeadlineStats(
        total_upcoming=len(scoped),
        within_30=within_30,
        within_90=within_90,
        next_date=scoped[0].deadline_date if scoped else None,  # merged is sorted ascending
        states=near_states,
    )
