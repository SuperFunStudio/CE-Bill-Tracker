import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legiscan_bill_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    openstates_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)

    state: Mapped[str] = mapped_column(String(2), nullable=False)  # "CA", "OR", "US" for federal
    bill_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_action_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Change detection
    change_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Classification (populated by pipeline)
    epr_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    material_categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    instrument_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Full compliance extraction (Sonnet output)
    compliance_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Judicial monitoring
    litigation_risk: Mapped[str | None] = mapped_column(Text, nullable=True, default="unknown")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    changes: Mapped[list["BillChange"]] = relationship("BillChange", back_populates="bill")
    deadlines: Mapped[list["ComplianceDeadline"]] = relationship(
        "ComplianceDeadline", back_populates="bill"
    )

    __table_args__ = (
        Index("idx_bills_state_status", "state", "status"),
        Index("idx_bills_last_action", "last_action_date"),
        Index("idx_bills_relevant", "epr_relevant"),
        Index("idx_bills_material_categories", "material_categories", postgresql_using="gin"),
    )


class BillChange(Base):
    __tablename__ = "bill_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(Integer, ForeignKey("bills.id"), nullable=False)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    bill: Mapped["Bill"] = relationship("Bill", back_populates="changes")

    __table_args__ = (Index("idx_bill_changes_bill_id", "bill_id"),)


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slack_webhook: Mapped[str | None] = mapped_column(Text, nullable=True)
    states: Mapped[list] = mapped_column(JSONB, default=list)  # ["CA", "OR"] or ["ALL"]
    material_categories: Mapped[list] = mapped_column(JSONB, default=list)  # or ["ALL"]
    min_confidence: Mapped[float] = mapped_column(Float, default=0.7)
    alert_on: Mapped[list] = mapped_column(
        JSONB, default=lambda: ["status_change", "new_bill", "deadline"]
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FederalAction(Base):
    __tablename__ = "federal_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    federal_register_document_number: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    agency: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    material_categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    published_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    comment_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    epr_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    preemption_risk: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_federal_published", "published_date"),)


class ComplianceDeadline(Base):
    __tablename__ = "compliance_deadlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bills.id"), nullable=True
    )
    federal_action_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("federal_actions.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    deadline_type: Mapped[str] = mapped_column(String(50), nullable=False)
    deadline_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    who_affected: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    bill: Mapped["Bill | None"] = relationship("Bill", back_populates="deadlines")

    __table_args__ = (
        Index("idx_deadlines_date", "deadline_date"),
        Index("idx_deadlines_state", "state"),
    )


# ---------------------------------------------------------------------------
# Company Impact Scoring Models (v2.0)
# ---------------------------------------------------------------------------


class Company(Base):
    __tablename__ = "company"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    duns_number: Mapped[str | None] = mapped_column(String(9), unique=True, nullable=True)
    cik: Mapped[str | None] = mapped_column(String(10), unique=True, nullable=True)
    epa_registry_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    hq_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    naics_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    operating_states: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    total_annual_volume_tonnes: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    volume_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    aliases: Mapped[list["CompanyAlias"]] = relationship("CompanyAlias", back_populates="company")
    materials: Mapped[list["CompanyMaterial"]] = relationship(
        "CompanyMaterial", back_populates="company"
    )
    state_presences: Mapped[list["CompanyStatePresence"]] = relationship(
        "CompanyStatePresence", back_populates="company"
    )
    impact_scores: Mapped[list["ImpactScore"]] = relationship(
        "ImpactScore", back_populates="company"
    )

    __table_args__ = (
        Index("idx_company_name", "name"),
        Index("idx_company_hq_state", "hq_state"),
    )


class CompanyAlias(Base):
    __tablename__ = "company_alias"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company.id"), nullable=False
    )
    alias_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, server_default="false")
    verified_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("alias_name", "source", name="uq_alias_source"),
        Index("idx_alias_company_id", "company_id"),
        Index(
            "idx_alias_name_trgm",
            "alias_name",
            postgresql_using="gin",
            postgresql_ops={"alias_name": "gin_trgm_ops"},
        ),
    )


class CompanyMaterial(Base):
    __tablename__ = "company_material"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company.id"), nullable=False
    )
    material_category: Mapped[str] = mapped_column(String(100), nullable=False)
    annual_volume_tonnes: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="materials")

    __table_args__ = (Index("idx_company_material_company_id", "company_id"),)


class CompanyStatePresence(Base):
    __tablename__ = "company_state_presence"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    presence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default="false")

    company: Mapped["Company"] = relationship("Company", back_populates="state_presences")

    __table_args__ = (Index("idx_presence_company_state", "company_id", "state"),)


class ImpactScore(Base):
    __tablename__ = "impact_score"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company.id"), nullable=False
    )
    bill_id: Mapped[int] = mapped_column(Integer, ForeignKey("bills.id"), nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    material_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    geographic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_annual_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped["Company"] = relationship("Company", back_populates="impact_scores")
    bill: Mapped["Bill"] = relationship("Bill", foreign_keys=[bill_id])

    __table_args__ = (
        Index("idx_impact_company_bill", "company_id", "bill_id"),
        Index("idx_impact_composite", "composite_score"),
    )


class EntityMatchQueue(Base):
    __tablename__ = "entity_match_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    candidate_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    suggested_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company.id"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, server_default="false")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_emq_resolved", "resolved"),)


class ExposureBrief(Base):
    __tablename__ = "exposure_brief"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company.id"), nullable=False
    )
    bill_id: Mapped[int] = mapped_column(Integer, ForeignKey("bills.id"), nullable=False)
    brief_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ttl_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    bill: Mapped["Bill"] = relationship("Bill", foreign_keys=[bill_id])

    __table_args__ = (
        UniqueConstraint("company_id", "bill_id", name="uq_exposure_brief_company_bill"),
        Index("idx_exposure_brief_ttl", "ttl_expires_at"),
    )


# ---------------------------------------------------------------------------
# CourtListener Judicial Monitoring Models (v2.0)
# ---------------------------------------------------------------------------


class LitigationCase(Base):
    __tablename__ = "litigation_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    courtlistener_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    case_name: Mapped[str] = mapped_column(Text, nullable=False)
    docket_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    court_id: Mapped[str] = mapped_column(String(50), nullable=False)
    court_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_filed: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_terminated: Mapped[date | None] = mapped_column(Date, nullable=True)
    assigned_judge: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="active")
    challenge_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    plaintiff_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    key_plaintiffs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    related_law_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bills.id", ondelete="SET NULL"), nullable=True
    )
    related_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    related_statute: Mapped[str | None] = mapped_column(Text, nullable=True)
    preemption_risk: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    cl_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    related_law: Mapped["Bill | None"] = relationship("Bill", foreign_keys=[related_law_id])
    events: Mapped[list["LitigationEvent"]] = relationship(
        "LitigationEvent", back_populates="case", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_litigation_cases_status", "case_status"),
        Index("idx_litigation_cases_state", "related_state"),
        Index("idx_litigation_cases_law_id", "related_law_id"),
    )


class LitigationEvent(Base):
    __tablename__ = "litigation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(Integer, ForeignKey("litigation_cases.id", ondelete="CASCADE"), nullable=False)
    courtlistener_entry_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    date_filed: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    significance: Mapped[str | None] = mapped_column(String(20), nullable=True, default="low")
    document_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped["LitigationCase"] = relationship("LitigationCase", back_populates="events")

    __table_args__ = (
        Index("idx_litigation_events_case_id", "case_id"),
        Index("idx_litigation_events_significance", "significance"),
    )


class CLAlertSubscription(Base):
    __tablename__ = "cl_alert_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    cl_alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    query_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    docket_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_cl_subs_active", "active"),)
