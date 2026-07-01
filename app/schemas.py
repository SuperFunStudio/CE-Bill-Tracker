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


class TextCoverageStats(BaseModel):
    """How many ce_relevant bills have indexed full text (GET /bills/text-coverage). Lets the UI be
    honest that full-text search isn't exhaustive — a thin/empty deep-search result means 'not in the
    text we've indexed', not 'nowhere in any bill'. indexed_bills == 0 means the index isn't populated
    on this environment yet (so the deep-search UI stays hidden)."""
    indexed_bills: int
    total_bills: int


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
