import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Computed,
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
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legiscan_bill_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    openstates_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    # EU document identifier (CELEX number, e.g. "32023R1542"). Set only for region="EU" rows
    # ingested from EUR-Lex/CELLAR; mirrors the per-source unique ids above. See app/ingestion/eurlex.py.
    celex_id: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    # Generic foreign-source identifier for non-US/EU national law, namespaced by region+source to stay
    # collision-free across countries (e.g. "JP:egov:424AC0000000057"). One column serves every new
    # country adapter (JP/GB/KR/…) so adding a jurisdiction needs no per-source migration.
    # See app/ingestion/foreign.py.
    foreign_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)

    # Top-level jurisdiction family. "US" (default) or "EU" today; the `state` column below carries the
    # sub-jurisdiction code within the region. This is the lean multi-region seam — the full
    # region+jurisdiction normalization is deferred (see plan serene-munching-brook).
    region: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
    # Within-region jurisdiction code. US: "CA"/"OR" for states, "US" for federal. EU: "EU" for
    # EU-wide acts (and "DE"/"FR"/… for member states once those are added).
    state: Mapped[str] = mapped_column(String(2), nullable=False)  # "CA", "OR", "US" federal; "EU" EU-wide
    # Atlas Circular jurisdiction node (migration 036). The normalized tree replacing the flat
    # region/state pair (which stay as denormalized mirrors during transition). Backfilled from
    # (region, state) via app/geo/jurisdictions.jurisdiction_code — e.g. (US,CA)->US-CA, (CA,CA)->CA.
    jurisdiction_id: Mapped[int | None] = mapped_column(ForeignKey("jurisdictions.id"), nullable=True)
    bill_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_action_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Health of source_url, set by scripts/audit_bill_source_links.py (see app/links/health.py).
    # status: alive | redirected | dead | blocked; NULL = never checked (treat link as fine).
    # final: resolved URL when redirected, so the UI can link to where the page actually moved.
    source_url_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_url_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Change detection
    change_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Classification (populated by pipeline)
    ce_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    material_categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Representative ("primary") instrument — kept for single-value views (insights group-by, the
    # instrument dropdown). instrument_types carries the full set (a law is often several at once).
    instrument_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    instrument_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Direction of the bill relative to its instrument: "advances" (establishes/strengthens),
    # "weakens" (exempts/narrows/repeals/preempts), or "neutral" (admin/study/ambiguous).
    # stance_source is "ai" (Haiku) or "heuristic" (text backfill) — see migration 006.
    policy_stance: Mapped[str | None] = mapped_column(String(20), nullable=True)
    stance_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Classification transparency: every relevance call is auto-classified by default; `reviewed`
    # flips true once a human has spot-checked it. Surfaced as the "auto-classified · reviewed"
    # marker on each bill (see /methodology).
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Auto-rescue flag: set True when the classifier itself would have dropped the bill
    # (is_ce_relevant=false / low confidence — usually because it was starved of bill text) but a
    # near-certain keyword signal in the title/description kept it in scope. Distinct from `reviewed`
    # (a human spot-check): needs_review marks rows the rescue layer wants a human to confirm. Cleared
    # whenever a later classification clears the rescue. See app/classification/pipeline.py.
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Event-triggered "new bill" alert idempotency — set once a newly-tracked relevant bill has been
    # emailed to matching subscribers (see app/alerts/new_bill_alerts.py).
    new_bill_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Full compliance extraction (Sonnet output)
    compliance_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    @property
    def polymers(self) -> list[str] | None:
        """Resin codes (HDPE, EVA, EPS…) detected in the full bill text by
        scripts/scan_bill_polymers.py and stored under compliance_details['polymers'].
        Surfaced as a lightweight list on BillSummary so the Bill Explorer can filter by
        resin — the rest of compliance_details (the paid Sonnet extraction) stays detail-only.
        Reads the already-loaded JSONB, so it adds no query to the list endpoint."""
        codes = (self.compliance_details or {}).get("polymers")
        return codes or None

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
        Index("idx_bills_region", "region"),
        Index("idx_bills_last_action", "last_action_date"),
        Index("idx_bills_relevant", "ce_relevant"),
        Index("idx_bills_policy_stance", "policy_stance"),
        Index("idx_bills_material_categories", "material_categories", postgresql_using="gin"),
        Index("idx_bills_instrument_types", "instrument_types", postgresql_using="gin"),
        Index("idx_bills_jurisdiction", "jurisdiction_id"),
    )


class Jurisdiction(Base):
    """Atlas Circular's jurisdiction tree (migration 036) — world -> bloc/country -> state ->
    municipality (municipality unseeded for now). Every bill attaches via Bill.jurisdiction_id. The
    seed data + the (region,state)->code mapping live in app/geo/jurisdictions.py so the tree and the
    backfill never drift. `aliases` (lowercased) is what lets a query resolve "France"/"French" to the
    FR node — the fix for geographic queries that the flat region/state columns can't serve."""
    __tablename__ = "jurisdictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("jurisdictions.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # world|bloc|country|state|municipality
    code: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)  # 'FR','US','US-CA'
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Lowercased search synonyms (country name, demonym, ISO code, state name/abbr). GIN-indexed.
    aliases: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, server_default=sa_text("'{}'"))
    path: Mapped[str] = mapped_column(Text, nullable=False)  # dotted, e.g. 'world.us.us_ca'
    bill_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        Index("idx_jurisdictions_path", "path"),
        Index("idx_jurisdictions_aliases", "aliases", postgresql_using="gin"),
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


class ClassificationChange(Base):
    """Audit log of classification deltas — one row per bill whose relevance/instrument changed on a
    (re)classification run. Mirrors BillChange, but for the classifier rather than bill status, and
    captures the FULL classification snapshot (old/new) so a reclassify run is diffable and a bad run
    is recoverable. Crucial because reclassify (app/reclassify.py) overwrites ce_relevant/confidence
    in place and only re-examines currently-in-scope bills — without this log a starved run silently
    sheds bills with no way to see or undo what dropped.

    old_value / new_value each hold: ce_relevant, confidence_score, instrument_type, instrument_types,
    needs_review. run_id tags the run (the Cloud Run execution name when available, else a source tag)
    so all of a run's drops can be queried together.
    """

    __tablename__ = "classification_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(Integer, ForeignKey("bills.id"), nullable=False)
    # Run/source tag: Cloud Run execution name (e.g. "signalscout-reclassify-dev-xx4vb") or a caller
    # source like "classify"/"reclassify" when not running as a job.
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_classification_changes_bill_id", "bill_id"),
        Index("idx_classification_changes_run_id", "run_id"),
    )


class BillText(Base):
    """Persisted full bill text + an FTS index — Layer B of the full-text search plan
    (docs/V2_FULLTEXT_SEARCH_PLAN.md).

    The extracted bill text was never stored; every text-based extraction re-fetched it per bill.
    This side table holds the cleaned full text ONCE, deliberately kept OUT of the wide `bills` row
    and the snapshot-baked list query (which must stay cheap and text-free). One row per bill,
    CASCADE-deleted with it. `text_tsv` is a generated `english` tsvector with a GIN index, so the
    search endpoint can run `text_tsv @@ websearch_to_tsquery('english', :q)` and return
    `ts_headline` snippets. `indexed_change_hash` mirrors the bill's `change_hash` at fetch time so
    the refresh job can skip bills whose text hasn't changed. No relationship is exposed on `Bill`
    on purpose — nothing should be able to eager-load text onto a list query; read it by bill_id.
    """
    __tablename__ = "bill_texts"

    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id", ondelete="CASCADE"), primary_key=True
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Read-only generated column (Postgres maintains it); never written via the ORM.
    text_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(text, ''))", persisted=True),
        nullable=True,
    )
    char_len: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Which rung of the fetch ladder produced the text: nysenate | legiscan | openstates | source_url.
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    indexed_change_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_bill_texts_tsv", "text_tsv", postgresql_using="gin"),
    )


class BillDesignSignal(Base):
    """One cited design implication derived from a bill's compliance_details.

    The atom of the Design-for-EPR synthesis (app/synthesis/design_levers.py): a `lever`
    (recyclability, recycled_content, repairability_durability, …) plus an `obligation_type`
    (required / rewarded / penalized / banned / exempted / named) and the VERBATIM
    `source_excerpt` it was extracted from. Principles are aggregated over these rows, so the
    excerpt is the chain of custody — every principle traces to a real clause on a real bill.
    `reviewed` mirrors Bill.reviewed (auto-extracted until a human spot-checks it).
    """
    __tablename__ = "bill_design_signal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    lever: Mapped[str] = mapped_column(String(40), nullable=False)
    obligation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    design_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extractor_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bill: Mapped["Bill"] = relationship("Bill", foreign_keys=[bill_id])

    __table_args__ = (
        Index("idx_design_signal_bill_id", "bill_id"),
        Index("idx_design_signal_lever", "lever"),
        Index("idx_design_signal_lever_obligation", "lever", "obligation_type"),
    )


class BillProductCoverage(Base):
    """One (product, obligation) the bill scopes — the atom behind the product-coverage grid.

    Where BillDesignSignal answers "what design levers does this bill pull", this answers "which
    specific products does it cover, and how". The controlled product vocabulary lives in
    app/synthesis/product_taxonomy.py (slug, label, icon, grid group); a slug absent from a bill's
    rows means "not mentioned" — only covered / exempt / conditional products get a row.

    `relationship` disambiguates the obligation (Phase 0 found the electronics bucket is ~half EPR /
    half right-to-repair, which scope products differently): stewarded | repairable | disposal_banned
    | deposit_return. `defined_by_reference` flags products the bill covers only by pointing at an
    existing statute rather than enumerating them. `source_excerpt` is the verbatim provenance, the
    same chain-of-custody guarantee design signals use; `reviewed` mirrors Bill.reviewed.
    """
    __tablename__ = "bill_product_coverage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    # Controlled vocab — validated against app/synthesis/product_taxonomy.py, not a DB FK.
    product_slug: Mapped[str] = mapped_column(String(60), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # electronics | batteries
    relationship_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # covered | exempt | conditional
    defined_by_reference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extractor_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bill: Mapped["Bill"] = relationship("Bill", foreign_keys=[bill_id])

    __table_args__ = (
        UniqueConstraint(
            "bill_id", "product_slug", "relationship_type", name="uq_coverage_bill_product_rel"
        ),
        Index("idx_product_coverage_bill_id", "bill_id"),
        Index("idx_product_coverage_category_slug", "category", "product_slug"),
        Index("idx_product_coverage_slug", "product_slug"),
    )


class BillFeeCitation(Base):
    """One cited fee or coverage-threshold fact extracted from a bill — the chain of custody
    behind a cost/severity estimate.

    Where the cost estimator turns a `fee_per_ton` into a dollar figure, this answers "where did
    that number come from, and can it be traced". Each row pins ONE numeric fact (`fact_type`:
    fee_per_ton / fee_per_unit_usd / registration_fee_usd / producer_revenue_threshold /
    producer_tonnage_threshold / eco_modulation) to its `basis`:

      enacted_text       — the value is stated in the bill itself; `source_excerpt` is the VERBATIM
                           clause (validated as a substring of the bill's compliance_details, same
                           guarantee BillDesignSignal uses — a fabricated quote is dropped, not stored).
      published_schedule — the value is NOT in the statute but in an agency / PRO fee schedule
                           (CalRecycle, PaintCare, MRC, …); `source_url` points at that schedule.
                           This is the honest home for EPR fees, which are usually set by post-enactment
                           rulemaking rather than written into the law (see scripts/enrich_bill_fees.py).
      benchmark          — no published value anywhere; an industry/category estimate. NOT grounded.

    A fee estimate is "grounded" when its driving fact has a citation whose basis is enacted_text or
    published_schedule; the UI surfaces that distinction so a published fee never looks like a guess.
    `reviewed` mirrors Bill.reviewed (auto-extracted until a human spot-checks it). ON DELETE CASCADE.
    """
    __tablename__ = "bill_fee_citation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    fact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    basis: Mapped[str] = mapped_column(String(20), nullable=False)
    extracted_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Verbatim clause for basis="enacted_text"; null for schedule/benchmark facts.
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Agency / PRO schedule URL for basis="published_schedule"; null otherwise.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extractor_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bill: Mapped["Bill"] = relationship("Bill", foreign_keys=[bill_id])

    __table_args__ = (
        UniqueConstraint("bill_id", "fact_type", "basis", name="uq_fee_citation_bill_fact_basis"),
        Index("idx_fee_citation_bill_id", "bill_id"),
        Index("idx_fee_citation_fact_type", "fact_type"),
    )


class AlertSubscription(Base):
    """A subscription to bill movement, in one of two scopes (the `scope` column):

      - "filter":    matches bills by states + instrument_types (topics) + materials + a confidence
                     floor. The anonymous public subscribe flow (POST /subscriptions) creates these;
                     firebase_uid is NULL.
      - "watchlist": account-owned (firebase_uid set), matches the explicit set of bills the owner
                     follows in user_watchlist, ignoring the filter columns and confidence floor. The
                     Pro star toggle ensures one of these per user (app/api/user.py). `alert_on` is
                     the user's "global per-user" notification prefs (which events to email about).

    All channels (real-time dispatcher, digest, deadline + new-bill alerts) match through
    subscription_matches_bill in app/alerts/digest.py, so the scope branch lives there once.
    """
    __tablename__ = "alert_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Owner of an account subscription; NULL for anonymous public (filter) subscriptions.
    firebase_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # "filter" | "watchlist" — see class docstring.
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="filter", server_default="filter"
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slack_webhook: Mapped[str | None] = mapped_column(Text, nullable=True)
    states: Mapped[list] = mapped_column(JSONB, default=list)  # LEGACY (pre-region) — kept for back-compat
    # Region-keyed jurisdiction scope, the source of truth since migration 032:
    #   {"US": ["CA","OR"], "EU": ["*"]}  ("*"/"ALL" or empty list = every jurisdiction in that region)
    # Empty {} = match all regions + jurisdictions. See _matches_scope in app/alerts/digest.py.
    region_scope: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    material_categories: Mapped[list] = mapped_column(JSONB, default=list)  # or ["ALL"]
    instrument_types: Mapped[list] = mapped_column(
        JSONB, default=lambda: ["ALL"]
    )  # policy topics: ["epr", "right_to_repair", ...] or ["ALL"]
    min_confidence: Mapped[float] = mapped_column(Float, default=0.7)
    alert_on: Mapped[list] = mapped_column(
        JSONB, default=lambda: ["status_change", "new_bill", "deadline"]
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Idempotency stamp for the one-time watch-list onboarding email (run_watchlist_onboarding_cycle):
    # NULL until sent, then the send time. Only meaningful on the "watchlist"-scope row. See
    # app/alerts/watchlist_onboarding.py.
    onboarding_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # High-water mark for the recurring "you added bills" recap (run_watchlist_recap_cycle): the send
    # time of the last recap. New adds (WatchlistItem.created_at) past COALESCE(this, onboarding stamp)
    # are recapped once a 30-min burst settles. Only meaningful on the "watchlist"-scope row. See
    # app/alerts/watchlist_recap.py.
    watchlist_recap_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("idx_alert_sub_uid_scope", "firebase_uid", "scope"),)


class AccessRequest(Base):
    """A captured "request access / pricing" click — the willingness-to-pay field experiment.

    Each paid tier's CTA (and the Company Impact gate) records who's interested, from what org, and
    in which tier, before any billing exists. Watching these tells us the real segment and price
    ceiling. Purely a lead-capture log; no behavioural effect.
    """
    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Which tier they asked about: "pro" | "team" | "enterprise" | "api" | "company_impact".
    plan_interest: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Where the click came from: "pricing" | "company_gate" — for funnel attribution.
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_access_requests_created", "created_at"),)


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
    ce_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    preemption_risk: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # friction_type / instrument_type: the other two classifier axes. friction_type is
    # federal-specific (how the action pressures state programs); instrument_type reuses the
    # state-bill vocabulary so the federal page can share the bill explorer's instrument facet.
    friction_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    instrument_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
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
    # Jurisdiction family ("US"/"EU"/…); `state` is the sub-jurisdiction code within it. See migration 032.
    region: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
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
        Index("idx_compliance_deadlines_region", "region"),
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
    # Jurisdiction family of the company's HQ/operations ("US"/"EU"/…). See migration 032.
    region: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
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
    # Jurisdiction family of this operational presence ("US"/"EU"/…); `state` is the code within it.
    region: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    presence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default="false")

    company: Mapped["Company"] = relationship("Company", back_populates="state_presences")

    __table_args__ = (
        Index("idx_presence_company_state", "company_id", "state"),
        Index("idx_company_state_presence_region", "region"),
    )


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
    region: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
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
        Index("idx_litigation_cases_region", "region"),
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


class Entitlement(Base):
    """A paid seat. One row per account, keyed by email — the stable identity that bridges Firebase
    Auth (who the user is) and Stripe (whether they paid).

    Firebase Auth proves identity (firebase_uid/email); Stripe proves payment. The billing webhook
    upserts this row on checkout + subscription changes. Premium routes treat the account as Pro when
    plan == "pro" AND status is active/trialing. Distinct from AccessRequest, which only records
    willingness-to-pay interest (no entitlement). See gating-and-monetization-plan.
    """

    __tablename__ = "entitlements"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    # "free" until a subscription activates; "pro" while a Pro subscription is live.
    plan: Mapped[str] = mapped_column(String(30), nullable=False, default="free", server_default="free")
    # Stripe subscription status: active | trialing | past_due | canceled | incomplete | unpaid.
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Complimentary ("comp") Pro granted by an admin — no Stripe subscription behind it. When True,
    # current_period_end (if set) is the grant's expiry; NULL period_end means indefinite. There is no
    # Stripe webhook to flip a comp grant off, so is_pro() enforces the expiry itself. comp_note /
    # comp_granted_by / comp_granted_at are the audit trail (why, which admin, when). See app/api/admin.py.
    comp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    comp_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    comp_granted_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    comp_granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Stamped True at checkout when the founding launch coupon was applied — i.e. this seat is a
    # founding member. Drives the "Founding Member" badge; never cleared on renewal (founding status
    # is granted at signup and kept). See app/api/billing.py.
    founding: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # This account's share-to-unlock referral code (generated lazily on first GET /referrals/me). When
    # a NEW account signs up via this code, the referrer gets a 30-day comp Pro grant. See referrals.py.
    referral_code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    # True once this account has consumed its one-time 7-day signup trial (the first rung of the value
    # ladder). Guards against re-granting on repeat calls. See app/api/billing.py signup_trial.
    signup_trial_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # The comp-grant expiry we last sent a "trial ending" reminder for. Equals current_period_end once
    # reminded, so the daily cycle sends once per trial; a re-granted/extended trial (new period_end)
    # re-qualifies. See app/alerts/trial_reminders.py.
    trial_reminder_sent_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_entitlements_email", "email"),
        Index("idx_entitlements_firebase_uid", "firebase_uid"),
        Index("idx_entitlements_stripe_customer", "stripe_customer_id"),
    )


class Referral(Base):
    """One completed share-to-unlock referral: a NEW account (referred) signed up via a referrer's
    code, which earns the referrer a 30-day comp Pro grant. One row per referred account (a given new
    user can only be the referred party once), so the grant can't be replayed. See app/api/referrals.py.
    """

    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referrer_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    # The newly-signed-up account this referral credits. Unique → one referral per new user.
    referred_uid: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    referred_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("idx_referrals_referrer_uid", "referrer_uid"),)


class UserSettings(Base):
    """Per-account UI preferences, keyed by the immutable Firebase uid. Today this holds the saved
    scope (states + materials); prefs is JSONB so new preferences don't need a migration. localStorage
    stays the anonymous/offline cache and instant-paint source; this is the cross-device source of
    truth once a user signs in. Free — any authenticated user. See gating-and-monetization-plan.
    """

    __tablename__ = "user_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    prefs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WatchlistItem(Base):
    """A bill an account follows — the Pro 'personal watch list'. Keyed by Firebase uid + bill, with
    ON DELETE CASCADE so a removed bill drops out of every watch list. Pro-gated at the API layer
    (require_pro). See gating-and-monetization-plan.
    """

    __tablename__ = "user_watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    firebase_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("firebase_uid", "bill_id", name="uq_watchlist_uid_bill"),
        Index("idx_watchlist_uid", "firebase_uid"),
    )


# ---------------------------------------------------------------------------
# Compliance Action layer — "now what do I do" bridge from a tracked law to the
# concrete next step (join this PRO / file this plan, by this deadline).
# ---------------------------------------------------------------------------


class ComplianceEntity(Base):
    """A real-world body a producer interacts with to comply: a stewardship organization
    (PRO) or a government agency. The normalized directory behind the "connect with a PRO"
    step — e.g. Circular Action Alliance (packaging), Call2Recycle (batteries), PaintCare,
    Mattress Recycling Council, CalRecycle. Curated, not auto-extracted (these are stable
    real-world facts); a law links to one via CompliancePathway. See compliance-action-vision.
    """
    __tablename__ = "compliance_entity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stable kebab key for idempotent seeding / linking (e.g. "circular-action-alliance").
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    # "pro" (producer responsibility / stewardship org) | "agency" (government administrator).
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Jurisdiction family this body operates in ("US"/"EU"/…). See migration 032.
    region: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Where a producer actually registers / joins / files — the actionable link.
    registration_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "national" | "multistate" | "single_state".
    jurisdiction_scope: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # For single-state entities (agencies, state PRO chapters).
    home_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    materials: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_compliance_entity_type", "entity_type"),
        Index("idx_compliance_entity_materials", "materials", postgresql_using="gin"),
        Index("idx_compliance_entity_region", "region"),
    )


class CompliancePathway(Base):
    """The "how do I comply with THIS law" record — one primary next-action per enacted law.

    Bridges the management_model classification (compliance_details.management) to a concrete
    step: join_pro (→ a ComplianceEntity), file_individual_plan / register_with_state (→ a state
    agency, or null when only the statute itself is the start), pay_into_program, monitor, or none.
    `action_summary` is the human one-liner; `registration_url` is the click target; next_deadline /
    has_fee are convenience snapshots so a state page renders without re-joining. `basis` records how
    the link was derived (management_model | pro_domain | curated | manual). One row per bill (v1).
    """
    __tablename__ = "compliance_pathway"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("compliance_entity.id", ondelete="SET NULL"), nullable=True
    )
    # Jurisdiction family of the law this pathway is for ("US"/"EU"/…). See migration 032.
    region: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
    management_model: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # join_pro | file_individual_plan | register_with_state | pay_into_program | monitor | none
    action_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    has_fee: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bill: Mapped["Bill"] = relationship("Bill", foreign_keys=[bill_id])
    entity: Mapped["ComplianceEntity | None"] = relationship(
        "ComplianceEntity", foreign_keys=[entity_id]
    )

    __table_args__ = (
        UniqueConstraint("bill_id", name="uq_pathway_bill"),
        Index("idx_pathway_bill_id", "bill_id"),
        Index("idx_pathway_entity_id", "entity_id"),
        Index("idx_pathway_management_model", "management_model"),
    )


# ---------------------------------------------------------------------------
# Real-world outcomes — the "what did this law actually do in the world" layer.
# Everything else in the schema describes what a law REQUIRES; this captures what
# an enacted law has been documented to PRODUCE (positive, negative, or mixed),
# always anchored to a citation. The atom of the Insights "Real-World Impact"
# spotlight. Curated, not auto-extracted — measured outcomes are rare and uneven,
# so each row is hand-seeded and source-backed (see scripts/seed_bill_outcomes.py).
# ---------------------------------------------------------------------------


class BillOutcome(Base):
    """One documented real-world outcome attributable to (or enabled by) an enacted law.

    A law can have several outcomes (e.g. a recycling gain AND a cost complaint), so this is
    one-to-many on bills, not one-per-bill. bill_id is a soft link: set when the law is in our
    bills table (→ clickable), but the denormalized state/bill_number/law_title keep the row
    self-describing for famous laws we don't track as rows yet. `attribution` records how tightly
    the number ties to the statute — "direct" (the law itself produced it), "program" (the law
    funds/incentivizes a program that produced it, e.g. TX HB3487 → Sink Your Shucks reef acreage),
    or "associated" (correlated, looser). `source_url` is the chain of custody — no outcome without it.
    """
    __tablename__ = "bill_outcome"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stable kebab key for idempotent seeding (e.g. "tx-hb3487-oyster-reef").
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    bill_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bills.id", ondelete="SET NULL"), nullable=True
    )
    # Denormalized law identity — present even when bill_id is null.
    region: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    bill_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    law_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    instrument_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    material_categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # "positive" | "negative" | "mixed" — direction of the documented effect.
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    # The headline metric, split for clean rendering: "Oyster reef restored" / 25 / "acres".
    # metric_display is an optional override for figures that don't compose as value+unit
    # (e.g. "recycling rate 18% → 64%"); the UI prefers it when present.
    metric_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metric_display: Mapped[str | None] = mapped_column(String(120), nullable=True)

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # "direct" | "program" | "associated" — how tightly the outcome ties to the statute.
    attribution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Mirrors Bill.reviewed: auto/curated-but-unvetted until a human spot-checks the figure.
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Remediation arc — only meaningful for negative/mixed outcomes (the bad-outcome flag is the
    # trigger to research a fix). remediated_by_bill_id is a soft link (clickable when tracked);
    # remediation_note/bill_number describe the fixing law even when we don't track it as a row.
    # remediation_checked_at = when this was last researched (NULL = never; drives the re-check job).
    remediation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediated_by_bill_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bills.id", ondelete="SET NULL"), nullable=True
    )
    remediation_bill_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    remediation_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bill: Mapped["Bill | None"] = relationship("Bill", foreign_keys=[bill_id])

    __table_args__ = (
        Index("idx_bill_outcome_bill_id", "bill_id"),
        Index("idx_bill_outcome_direction", "direction"),
    )


class ResearchSession(Base):
    """A persisted 'Ask the Bills' research thread — the primitive that turns ephemeral asks into a
    saveable, shareable analysis layer (migration 037; see docs/PUBLIC_AFFAIRS_RESEARCH_DESIGN.md).
    Owned by a Firebase uid (same pattern as alert_subscriptions.firebase_uid). Private by default;
    `share_token` is minted on first share for an unlisted, noindex read link. Not exposed to users
    until Phase A2 — the tables land now so /ask can start persisting."""
    __tablename__ = "research_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    owner_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, server_default="private")  # private|link|public
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    turns: Mapped[list["ResearchTurn"]] = relationship(
        "ResearchTurn", back_populates="session", cascade="all, delete-orphan", order_by="ResearchTurn.seq"
    )

    __table_args__ = (Index("idx_research_sessions_owner", "owner_uid"),)


class ResearchTurn(Base):
    """One question+answer within a ResearchSession. `bill_ids` snapshots the ranked relevant set at
    ask time (citability — a shared briefing shows what it showed); `rewritten_query`+`facets` capture
    how retrieval interpreted the (possibly follow-up) question so a page can be re-run deterministically."""
    __tablename__ = "research_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    facets: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # resolved facet interpretation
    strategy: Mapped[str | None] = mapped_column(String(40), nullable=True)
    answer: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # the ResearchAnswer payload
    bill_ids: Mapped[list | None] = mapped_column(ARRAY(Integer), nullable=True)  # ranked snapshot
    bill_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["ResearchSession"] = relationship("ResearchSession", back_populates="turns")

    __table_args__ = (Index("idx_research_turns_session", "session_id", "seq"),)


class ContentDraft(Base):
    """An editorial draft distilled from a research turn — the staging area behind the Substack content
    engine (migration 038). An admin runs a turn through the linking + editorial pass and it lands here;
    `body_markdown` already has its [STATE BILL_NUMBER] citations rewritten to /?bill=<id> deep links so
    it can be pasted straight into Substack. Nothing here auto-publishes — `status` tracks the manual
    workflow (staged → published-once-copied-out). See app/api/research.py."""
    __tablename__ = "content_drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # Provenance — nullable + SET NULL so deleting a research thread can't destroy an article draft.
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True
    )
    source_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    dek: Mapped[str | None] = mapped_column(Text, nullable=True)  # subtitle / standfirst
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)  # linked + edited article body
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="staged")  # staged|draft|published
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)  # admin email
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_content_drafts_status", "status", "created_at"),)
