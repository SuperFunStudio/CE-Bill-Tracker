import uuid
from datetime import date, datetime

from pydantic import BaseModel


class BillSummary(BaseModel):
    id: int
    # "US" (default) or "EU". The `state` field below is the sub-jurisdiction within the region
    # ("CA"/"US" federal for US, "EU" for EU-wide). See migration 031.
    region: str = "US"
    state: str
    bill_number: str | None
    title: str | None
    status: str | None
    last_action_date: date | None
    ce_relevant: bool
    confidence_score: float | None
    material_categories: list | None
    # Resin codes detected in the full bill text (compliance_details['polymers']), surfaced here so
    # the Bill Explorer can filter to a specific resin (HDPE, EVA…). Null until the polymer scan runs.
    polymers: list[str] | None = None
    instrument_type: str | None
    # Full instrument set (a law is often several at once); instrument_type is the primary. See migration 034.
    instrument_types: list | None = None
    urgency: str | None
    ai_summary: str | None
    policy_stance: str | None = None
    stance_source: str | None = None
    reviewed: bool = False
    source_url: str | None
    # Source-link health (set by scripts/audit_bill_source_links.py): lets the UI offer a fallback
    # instead of dropping the user on a dead/moved link. status is alive|redirected|dead|blocked,
    # NULL = unchecked (treat as fine); final is the resolved URL when redirected.
    source_url_status: str | None = None
    source_url_final: str | None = None
    litigation_case_count: int = 0
    max_preemption_risk: int | None = None

    model_config = {"from_attributes": True}


class BillDetail(BillSummary):
    description: str | None
    # compliance_details (the paid Sonnet extraction) is intentionally absent from BillSummary so the
    # bulk list endpoint can't be harvested for the whole compliance dataset in one call — it lives
    # here, on the per-bill detail, only.
    compliance_details: dict | None
    created_at: datetime
    updated_at: datetime


class BillSearchHit(BillSummary):
    """A full-text search result (GET /bills/search): the bill summary plus the highlighted
    snippet(s) where the query matched in the bill's full text. `snippets` come from Postgres
    `ts_headline` — the matched term wrapped in <mark>…</mark>, on text that was already HTML-stripped
    at ingest, so the only markup is the highlight. `text_indexed` is always True here (only indexed
    bills can match) but is carried so the UI can mark a result as a deep-text hit vs. a summary hit."""
    snippets: list[str] = []
    text_indexed: bool = True


class RegionCoverage(BaseModel):
    """Per-region slice of text + dimension coverage, so an 'across all bills' claim can be qualified
    honestly (e.g. 'US 98% analyzed, JP 40%') instead of implying completeness."""
    region: str
    total_bills: int      # ce_relevant in this region
    indexed_bills: int    # of those, with full text stored
    analyzed_bills: int   # of those, extracted at the current dimension schema version


class TextCoverageStats(BaseModel):
    """How many ce_relevant bills have indexed full text (GET /bills/text-coverage). Lets the UI be
    honest that full-text search isn't exhaustive — a thin/empty deep-search result means 'not in the
    text we've indexed', not 'nowhere in any bill'. indexed_bills == 0 means the index isn't populated
    on this environment yet (so the deep-search UI stays hidden). by_region is populated only when the
    caller passes ?by_region=true."""
    indexed_bills: int
    total_bills: int
    by_region: list[RegionCoverage] | None = None


class BillFullText(BaseModel):
    """One bill's persisted full statute text (GET /bills/{id}/text). Deliberately its own endpoint,
    not a field on BillDetail — the text is large and lives in the `bill_texts` side table, kept off
    the wide bill row and the snapshot list. `text` is None when we haven't ingested this bill's text
    yet, so the modal can fall back to the source link instead of showing an empty panel."""
    bill_id: int
    text: str | None = None
    char_len: int | None = None
    # Which rung of the fetch ladder produced the text (nysenate | legiscan | openstates | source_url).
    source: str | None = None


class StateMapSummary(BaseModel):
    state: str
    enacted_count: int
    pending_count: int
    total_relevant: int
    material_categories: list[str]


class BillTimelinePoint(BaseModel):
    """One (year, status) bucket: how many EPR-relevant bills last reached `status` in `year`.

    `year` is derived from status_date (the date of the most recent status transition), so
    enacted buckets read as "laws enacted that year" — cumulating them gives laws on the books.
    """

    year: int
    status: str
    count: int
    # Jurisdiction family (US, EU, FR, …). Set when the Insights region filter groups by region so
    # the chart can render one series per region (compare mode); the frontend sums across regions for
    # the aggregate "All" view. Omitted/None on legacy unscoped calls.
    region: str | None = None


class BillStancePoint(BaseModel):
    """One (year, stance) bucket: how many EPR-relevant bills last moved in `year` carry `stance`.

    `stance` is policy_stance — "advances" (establishes/strengthens), "weakens"
    (exempts/narrows/repeals/preempts), or "neutral" (admin/study/ambiguous). Powers the Insights
    "policy momentum" diverging chart; neutral is returned but the chart leaves it off the axis.
    """

    year: int
    stance: str
    count: int
    region: str | None = None  # see BillTimelinePoint.region


class InstrumentMaterialCell(BaseModel):
    """One (instrument, material) cell of the Insights coverage heatmap: how many EPR-relevant bills
    apply `instrument_type` to `material_category`. Materials are unnested from the JSONB array, so a
    bill tagging three materials contributes to three cells. Absent cells are the white space."""

    instrument_type: str
    material_category: str
    count: int
    region: str | None = None  # see BillTimelinePoint.region


class ResearchAskRequest(BaseModel):
    """A natural-language question for the 'Ask the Bills' endpoint (POST /research/ask)."""
    question: str


class ResearchChartBar(BaseModel):
    label: str
    value: int


class ResearchChart(BaseModel):
    """A chart the answer chose to show. Bars are computed server-side from SQL aggregates (not the
    LLM), so the numbers are exact; the model only picks WHICH aggregate is relevant."""
    title: str
    bars: list[ResearchChartBar]


class ResearchCitation(BaseModel):
    """One bill the answer is grounded in — only bills from the retrieved set can be cited."""
    bill_id: int
    region: str | None = None
    state: str | None = None
    bill_number: str | None = None
    year: int | None = None
    snippet: str | None = None


class ResearchBillPage(BaseModel):
    """One page of the FULL set of bills relevant to an 'Ask the Bills' question. `total` is the
    complete count across all pages (so the UI can page through every relevant bill, not a capped
    sample). `strategy` records which retrieval tier produced the set — 'text' (precise full-text),
    'dimension:<key>' (structured fallback when the question maps to a compliance dimension but text
    match is thin), or 'text_broad' (OR-broadened last resort) — so the coverage note can be honest."""
    total: int
    page: int
    page_size: int
    strategy: str
    items: list[BillSummary]


class ResearchAnswer(BaseModel):
    """The 'Ask the Bills' response: a cited narrative, an optional SQL-backed chart, and a coverage
    note so an answer over retrieved bills never implies whole-corpus completeness."""
    answer: str
    citations: list[ResearchCitation]
    chart: ResearchChart | None = None
    coverage_note: str | None = None
    # Page 1 of the full relevant-bill set backing this answer; subsequent pages come from
    # GET /research/bills (SQL-only, no LLM). None when the question yields no relevant bills.
    bills: ResearchBillPage | None = None


# --- Bill-strength evaluation (POST /evaluate/bill) — see app/evaluation/strength.py ----------------
class EvaluateRequest(BaseModel):
    """A draft/enacted measure to evaluate. Pasted text is run through the same SonnetExtractor as the
    corpus, then scored against the baseline its target material's regime demands (fit, not a flat count)."""
    text: str
    title: str | None = None
    jurisdiction: str | None = None
    region: str | None = None  # extractor language/framing; defaults to US


class RegimeAxes(BaseModel):
    """Where the target material sits on the value×dispersion×channel map (0..1 each). Drives the regime."""
    value_density: float
    dispersion: float
    channel_maturity: float


class BillRegime(BaseModel):
    """Which intervention playbook the material demands. `key` is incremental_viable | critical_mass —
    a lead-acid battery bill can be lean and strong; a textiles bill that lean is weak."""
    key: str
    label: str
    material: str
    confidence: str  # high (matched a known material) | low (fallback positioning)
    rationale: str
    axes: RegimeAxes


class RequirementResult(BaseModel):
    """One mechanism the regime's baseline requires, scored against what the extractor found in the bill."""
    key: str
    label: str
    importance: str  # load_bearing | supporting | bonus
    status: str      # met | partial | missing
    weight: int
    your_value: str  # what this bill has
    baseline: str    # what a strong bill for this regime carries
    note: str | None = None


class StrengthScore(BaseModel):
    value: int       # 0..100, weighted fraction of non-bonus requirements met
    band: str        # strong | moderate | weak
    summary: str


class AnalogOutcome(BaseModel):
    """A documented real-world result of an enacted analog law (from bill_outcome) — the 'how it landed'."""
    direction: str          # positive | negative | mixed
    summary: str
    metric: str | None = None
    attribution: str | None = None
    source_name: str | None = None
    source_url: str | None = None


class CorpusAnalog(BaseModel):
    """One enacted law in the same material regime as the draft, scored on the same mechanisms — so the
    draft can be read against measures whose impact has actually landed."""
    bill_id: int | None = None
    region: str | None = None
    state: str | None = None
    bill_number: str | None = None
    title: str | None = None
    year: int | None = None
    material: str
    same_material: bool
    reviewed: bool          # human/Opus-approved classification
    mechanisms: dict[str, str]  # requirement key -> met | partial | missing
    outcomes: list[AnalogOutcome] = []


class CorpusBaselinePoint(BaseModel):
    """For one required mechanism: what share of enacted analogs in this regime carry it, vs the draft."""
    key: str
    label: str
    analog_share: float     # 0..1 of same-regime enacted analogs with this mechanism fully in place
    your_status: str        # met | partial | missing on the draft


class CorpusCrossCheck(BaseModel):
    """The draft measured against enacted laws in the same material regime: which mechanisms the ones
    that made it onto the books carried, which of those produced documented outcomes, and where the
    draft sits relative to that field."""
    regime: str
    analog_count: int             # same-regime enacted analogs considered
    same_material_count: int
    value_basis_share: float | None = None  # share of analogs using value-aligned (not weight) targets
    baseline: list[CorpusBaselinePoint]
    analogs: list[CorpusAnalog]
    note: str


class EvaluateResponse(BaseModel):
    """The bill-strength result: the material's regime, a fit score against that regime's baseline, a
    per-mechanism comparison, flags (value-vs-weight, implementation-gap), the extracted envelopes
    (compliance_details-shaped, rendered with the same dimensions.ts as bill detail), and a corpus
    cross-check against enacted laws in the same regime."""
    regime: BillRegime
    score: StrengthScore
    requirements: list[RequirementResult]
    flags: list[str]
    compliance_details: dict
    # The strong model bill for this regime, compliance_details-shaped — for a dimension-by-dimension
    # diff against the draft (rendered with the same dimensions.ts). See app/evaluation/baselines.py.
    baseline_details: dict
    corpus: CorpusCrossCheck | None = None
    title: str | None = None
    jurisdiction: str | None = None


class MaterialMapPoint(BaseModel):
    """One material's position on the value×dispersion×channel map, plus the regime it implies — the
    reference data behind the material-position viz (GET /evaluate/material-map)."""
    material: str
    value_density: float           # log-normalized recoverable $/tonne, 0..1
    dispersion: float
    channel_maturity: float
    regime: str
    value_usd_per_tonne: float | None = None  # the raw anchor behind value_density (for tooltips)


class CollectionTargetBasisPoint(BaseModel):
    """One (basis, region) bucket of collection/recovery targets: how many targets in `region` are
    measured on `basis` — weight | units | value_recovered | material_specific | unspecified. Unnested
    from compliance_details.collection_targets.targets, so a bill with several targets contributes
    several rows. Answers 'do bills measure collection targets by weight, or by value recovered?'."""

    basis: str
    count: int
    region: str | None = None  # see BillTimelinePoint.region


class LawsInForcePoint(BaseModel):
    """One (year, region) bucket: how many CE laws came INTO FORCE that year in that region.

    Uses the extracted effective_date (foreign regulations have no introduced→enacted pipeline, so
    the timeline/momentum charts are empty for them), falling back to status_date for US enacted laws.
    The frontend cumulates these into a "laws on the books over time" line per region — the momentum
    view that works cross-jurisdiction. See /bills/laws-in-force.
    """

    year: int
    region: str
    count: int


class StateGapRow(BaseModel):
    """One state's "Battle of the Bills" gap: its advancing-CE passage rate vs. its all-bills
    baseline. The gap (ce_rate - baseline_rate) is the signal — positive = CE bills pass MORE
    readily than the state's average bill; negative = contested-policy drag. baseline_rate comes
    from the OpenStates dump (all-bills); the CE figures are live from our DB."""

    state: str
    ce_rate: float
    ce_enacted: int
    ce_total: int
    baseline_rate: float | None = None
    gap: float | None = None


class StateCycleRow(BaseModel):
    """One legislative biennium for a state: its advancing-CE passage rate vs. the all-bills baseline,
    so the gap can be read as a trend across cycles. Bucketed by biennium (carryover-safe — a bill
    introduced in year 1 and enacted in year 2 stays in the same cycle). `in_flight` flags the current
    biennium, whose rate is deflated because bills are still moving."""

    biennium: str
    start_year: int
    ce_total: int
    ce_enacted: int
    ce_rate: float | None = None
    baseline_introduced: int
    baseline_enacted: int
    baseline_rate: float | None = None
    gap: float | None = None
    in_flight: bool = False


class ChampionBill(BaseModel):
    """One bill a champion sponsored — carries source_url so the roster honors the link-to-source rule."""

    bill_id: int | None = None
    state: str | None = None
    bill_number: str | None = None
    instrument: str | None = None
    enacted: bool = False
    source_url: str | None = None


class ChampionSummary(BaseModel):
    """A legislator advancing the circular economy. `active` = currently in office (per the dump's
    current_role). `success_rate` = enacted / total of their sponsored CE bills. Slim by default —
    the per-bill list (with sources) is fetched on expand via /insights/champions/{person_id}."""

    person_id: str | None = None
    name: str | None = None
    party: str | None = None
    chamber: str | None = None
    district: str | None = None
    active: bool = False
    states: list[str] = []
    primary_sponsorships: int = 0
    cosponsorships: int = 0
    total_ce_bills: int = 0
    enacted_count: int = 0
    success_rate: float | None = None
    instruments: list[str] = []
    materials: list[str] = []


class DeadlineSummary(BaseModel):
    id: int
    region: str = "US"
    state: str
    deadline_type: str
    deadline_date: date
    description: str | None
    who_affected: str | None
    bill_id: int | None
    bill_number: str | None
    bill_title: str | None
    # The linked bill's material categories, denormalized so the client can scope-filter deadlines
    # without bulk-loading every bill (the bulk bill list no longer carries compliance_details).
    material_categories: list | None = None

    model_config = {"from_attributes": True}


class DeadlineStats(BaseModel):
    """Public aggregate counts for the Upcoming Deadlines surfaces (metric cards + scoped banner).

    Counts are not the paid product — the individual deadline rows are — so these stay ungated to
    power the conversion hook ("147 deadlines, 12 within 30 days") even for anonymous visitors.
    """
    total_upcoming: int
    within_30: int
    within_90: int
    next_date: date | None = None
    states: list[str] = []


class FederalActionSummary(BaseModel):
    id: int
    agency: str | None
    title: str | None
    action_type: str | None
    published_date: date | None
    comment_deadline: date | None
    effective_date: date | None
    document_url: str | None
    preemption_risk: str | None
    friction_type: str | None
    instrument_type: str | None
    material_categories: list[str] | None
    ai_summary: str | None
    ce_relevant: bool

    model_config = {"from_attributes": True}


class SubscriptionCreate(BaseModel):
    email: str | None = None
    organization: str | None = None
    slack_webhook: str | None = None
    # LEGACY flat jurisdiction list (kept for back-compat). Prefer region_scope below.
    states: list[str] = ["ALL"]
    # Region-keyed jurisdiction scope: {"US": ["CA","OR"], "EU": ["*"]}. Empty {} = match all
    # regions. If omitted but `states` is given, the API maps it to {"US": states}. See migration 032.
    region_scope: dict[str, list[str]] = {}
    material_categories: list[str] = ["ALL"]
    instrument_types: list[str] = ["ALL"]
    min_confidence: float = 0.7
    alert_on: list[str] = ["status_change", "new_bill", "deadline"]


class SubscriptionResponse(SubscriptionCreate):
    id: int
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AccessRequestCreate(BaseModel):
    """A 'request access / pricing' capture. plan_interest is one of:
    pro | team | enterprise | api | company_impact."""
    email: str
    name: str | None = None
    organization: str | None = None
    plan_interest: str
    message: str | None = None
    source: str | None = None


class AccessRequestResponse(AccessRequestCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Company Impact Scoring Schemas (v2.0)
# ---------------------------------------------------------------------------


class CompanyMaterialSummary(BaseModel):
    id: uuid.UUID
    material_category: str
    annual_volume_tonnes: float | None
    volume_confidence: float | None
    source: str | None

    model_config = {"from_attributes": True}


class CompanyStatePresenceSummary(BaseModel):
    id: uuid.UUID
    state: str
    presence_type: str
    is_primary: bool

    model_config = {"from_attributes": True}


class CompanySummary(BaseModel):
    id: uuid.UUID
    name: str
    hq_state: str | None
    naics_codes: list | None
    operating_states: list | None
    total_annual_volume_tonnes: float | None
    volume_confidence: float | None

    model_config = {"from_attributes": True}


class CompanyDetail(CompanySummary):
    duns_number: str | None
    cik: str | None
    epa_registry_id: str | None
    volume_source: str | None
    materials: list[CompanyMaterialSummary]
    state_presences: list[CompanyStatePresenceSummary]
    created_at: datetime
    updated_at: datetime


class ImpactScoreResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    bill_id: int
    composite_score: float
    material_score: float | None
    geographic_score: float | None
    severity_score: float | None
    estimated_annual_cost: float | None
    cost_confidence: float | None
    volume_confidence: float | None
    score_breakdown: dict | None
    calculated_at: datetime

    model_config = {"from_attributes": True}


class ExposureRanking(BaseModel):
    """Manually constructed — no from_attributes needed."""
    company: CompanySummary
    impact_score: ImpactScoreResponse


class CompanyObligationDeadline(BaseModel):
    """A single upcoming compliance deadline for an affected bill."""
    deadline_date: date
    deadline_type: str
    description: str | None
    who_affected: str | None
    source_url: str | None


class StakesPenalty(BaseModel):
    """Civil penalty written into the statute — the grounded 'what's at stake' anchor."""
    amount_usd: float
    unit: str  # "day" | "violation"
    raw: str   # verbatim enforcement text


class StakesFee(BaseModel):
    """Annual program-fee range for a (company, bill) pair.

    `annual_fee_grounded` is True only when backed by a published schedule (CA SB 54
    2027, Oregon CAA midpoint, PaintCare/MRC). Otherwise it's a benchmark estimate.
    """
    annual_fee_low_usd: float
    annual_fee_high_usd: float
    annual_fee_grounded: bool
    fee_basis: str
    eco_modulation_swing_usd: float | None = None
    eco_modulation_floor_usd: float | None = None
    eco_modulation_notes: list[str] = []
    citation: str | None = None
    confidence: float


class FinancialStakes(BaseModel):
    """The layered financial exposure for one affected law."""
    penalty: StakesPenalty | None = None
    fee: StakesFee | None = None
    pro_membership_usd: float | None = None
    has_any: bool = False


class CompanyObligation(BaseModel):
    """One enacted law a company is affected by, plus its next deadline.

    "Affected" is high-confidence: the company has a material in the bill's
    categories AND an operational presence in the bill's state. No proxy
    volumes or synthetic cost are involved.
    """
    bill_id: int
    state: str
    bill_number: str | None
    bill_title: str | None
    status: str | None
    source_url: str | None
    matched_materials: list[str]
    presence_types: list[str]
    next_deadline: CompanyObligationDeadline | None
    upcoming_deadline_count: int
    total_deadline_count: int
    stakes: FinancialStakes | None = None


class CompanyObligationsResponse(BaseModel):
    """'Are you affected, and what's your next deadline' for one company."""
    company_id: uuid.UUID
    company_name: str
    affected_bill_count: int
    affected_states: list[str]
    upcoming_deadline_count: int
    next_deadline_date: date | None
    obligations: list[CompanyObligation]
    # Portfolio-level financial rollup (None where no data exists). The max per-day
    # penalty across affected laws leads the page; fees aggregate into a range.
    max_penalty_per_day_usd: float | None = None
    portfolio_annual_fee_low_usd: float | None = None
    portfolio_annual_fee_high_usd: float | None = None
    portfolio_eco_modulation_swing_usd: float | None = None
    any_fee_grounded: bool = False


class ExposureBriefResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    bill_id: int
    brief_json: dict | None
    generated_at: datetime
    ttl_expires_at: datetime | None

    model_config = {"from_attributes": True}


class EntityMatchQueueItem(BaseModel):
    id: uuid.UUID
    candidate_name: str
    source: str | None
    suggested_company_id: uuid.UUID | None
    confidence: float | None
    resolved: bool
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# CourtListener Judicial Monitoring Schemas (v2.0)
# ---------------------------------------------------------------------------


class LitigationEventSummary(BaseModel):
    id: int
    event_type: str
    date_filed: date | None
    description: str | None
    summary: str | None
    significance: str | None
    document_url: str | None

    model_config = {"from_attributes": True}


class LitigationCaseSummary(BaseModel):
    id: int
    courtlistener_id: int
    case_name: str
    docket_number: str | None
    court_id: str
    court_name: str | None
    date_filed: date | None
    date_terminated: date | None
    assigned_judge: str | None
    case_status: str | None
    challenge_type: str | None
    plaintiff_type: str | None
    key_plaintiffs: list | None
    related_law_id: int | None
    related_state: str | None
    related_statute: str | None
    preemption_risk: int | None
    cl_url: str | None
    last_activity_date: date | None
    event_count: int = 0

    model_config = {"from_attributes": True}


class LitigationCaseDetail(LitigationCaseSummary):
    events: list[LitigationEventSummary] = []


# --- Compliance action layer (compliance_entity + compliance_pathway) ---


class ComplianceEntityRef(BaseModel):
    id: int
    slug: str
    name: str
    entity_type: str  # "pro" | "agency"
    url: str | None = None
    registration_url: str | None = None
    jurisdiction_scope: str | None = None

    model_config = {"from_attributes": True}


class CompliancePathwaySummary(BaseModel):
    """One enacted law's "how do I comply" record, with its administering entity inlined."""
    bill_id: int
    bill_number: str | None = None
    bill_title: str | None = None
    material_categories: list | None = None
    management_model: str | None = None
    action_type: str | None = None
    action_summary: str | None = None
    registration_url: str | None = None
    next_deadline_date: date | None = None
    has_fee: bool = False
    entity: ComplianceEntityRef | None = None

    model_config = {"from_attributes": True}


class FeeScheduleRate(BaseModel):
    """One published per-format rate from the CA SB 54 (2027 draft) fee schedule.

    `tier` is best | representative | worst within the material category — the published
    low/high formats that bound the eco-modulation spread. The plastic adder (Reuse +
    PPMF, plastic CMCs only) is exposed as its own field rather than baked into the base:
    total_cents_per_lb = base_cents_per_lb + plastic_adder_cents_per_lb, and
    usd_per_tonne is computed from the total. `format_name` is null for the
    representative tier (a category blend, not a single published format).
    """
    tier: str  # "best" | "representative" | "worst"
    format_name: str | None = None
    base_cents_per_lb: float
    plastic_adder_cents_per_lb: float
    total_cents_per_lb: float
    usd_per_tonne: int
    # Program's own published high scenario (≈2.5x low); populated on the representative tier.
    usd_per_tonne_high: int | None = None


class FeeScheduleCategory(BaseModel):
    material_category: str  # canonical form (app/scoring/materials.py vocabulary)
    aliases: list[str] = []  # raw tokens that canonicalize to this category
    includes_plastic_adder: bool
    note: str | None = None
    rates: list[FeeScheduleRate]


class FeeSchedulePlasticAdder(BaseModel):
    """The Reuse Investment + Plastic Pollution Mitigation Fund adders (plastic CMCs only)."""
    reuse_cents_per_lb: float
    ppmf_cents_per_lb: float
    total_cents_per_lb: float
    applies_to: str = "plastic material categories only"


class FeeScheduleResponse(BaseModel):
    program: str
    basis: str  # exact citation from the source-of-truth module
    source_url: str
    rates_final_expected: str
    lb_per_tonne: float
    high_scenario_multiplier: float
    plastic_adder: FeeSchedulePlasticAdder
    categories: list[FeeScheduleCategory]


# --- Real-world outcomes (bill_outcome) ---


class BillOutcomeSummary(BaseModel):
    """One documented real-world effect of an enacted law, anchored to a citation.

    `direction` is positive | negative | mixed; `attribution` (direct | program | associated)
    says how tightly the figure ties to the statute. `bill_id` is set only when the law is a
    tracked row (→ clickable); the denormalized state/bill_number/law_title always describe it.
    """
    id: int
    slug: str
    bill_id: int | None = None
    state: str | None = None
    bill_number: str | None = None
    law_title: str | None = None
    instrument_type: str | None = None
    material_categories: list | None = None
    direction: str
    metric_label: str | None = None
    metric_value: float | None = None
    metric_unit: str | None = None
    metric_display: str | None = None
    summary: str
    attribution: str | None = None
    as_of_date: date | None = None
    source_name: str | None = None
    source_url: str | None = None
    confidence: float | None = None
    reviewed: bool = False
    # Remediation arc (negative/mixed outcomes only): the later law that fixed the problem.
    # remediated_by_bill_id is set when that law is a tracked row (→ clickable).
    remediation_note: str | None = None
    remediation_bill_number: str | None = None
    remediated_by_bill_id: int | None = None

    model_config = {"from_attributes": True}
