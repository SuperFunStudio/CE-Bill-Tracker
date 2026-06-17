import uuid
from datetime import date, datetime

from pydantic import BaseModel


class BillSummary(BaseModel):
    id: int
    state: str
    bill_number: str | None
    title: str | None
    status: str | None
    last_action_date: date | None
    epr_relevant: bool
    confidence_score: float | None
    material_categories: list | None
    instrument_type: str | None
    urgency: str | None
    ai_summary: str | None
    policy_stance: str | None = None
    stance_source: str | None = None
    reviewed: bool = False
    source_url: str | None
    compliance_details: dict | None
    litigation_case_count: int = 0
    max_preemption_risk: int | None = None

    model_config = {"from_attributes": True}


class BillDetail(BillSummary):
    description: str | None
    compliance_details: dict | None
    created_at: datetime
    updated_at: datetime


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


class DeadlineSummary(BaseModel):
    id: int
    state: str
    deadline_type: str
    deadline_date: date
    description: str | None
    who_affected: str | None
    bill_id: int | None
    bill_number: str | None
    bill_title: str | None

    model_config = {"from_attributes": True}


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
    epr_relevant: bool

    model_config = {"from_attributes": True}


class SubscriptionCreate(BaseModel):
    email: str | None = None
    organization: str | None = None
    slack_webhook: str | None = None
    states: list[str] = ["ALL"]
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
