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
    ai_summary: str | None
    epr_relevant: bool

    model_config = {"from_attributes": True}


class SubscriptionCreate(BaseModel):
    email: str | None = None
    slack_webhook: str | None = None
    states: list[str] = ["ALL"]
    material_categories: list[str] = ["ALL"]
    min_confidence: float = 0.7
    alert_on: list[str] = ["status_change", "new_bill", "deadline"]


class SubscriptionResponse(SubscriptionCreate):
    id: int
    active: bool
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
