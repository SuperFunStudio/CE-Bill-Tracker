// TypeScript interfaces mirroring app/schemas.py

export interface ComplianceDeadline {
  date: string;
  type: string;
  description: string;
}

export interface ComplianceFees {
  structure: string;
  details: string;
}

export interface ComplianceDetails {
  producer_definition?: string;
  covered_products?: string[];
  exemptions?: string[];
  deadlines?: ComplianceDeadline[];
  fees?: ComplianceFees;
  producer_obligations?: string[];
  pro_requirements?: string;
  enforcement?: { agency: string; penalties: string };
  preemption_risk?: string;
  preemption_notes?: string;
  effective_date?: string;
  compliance_date?: string;
  reporting_requirements?: string;
}

export interface BillSummary {
  id: number;
  /** "US" (default) or "EU". `state` is the sub-jurisdiction within the region. */
  region: string;
  state: string;
  bill_number: string | null;
  title: string | null;
  status: string | null;
  last_action_date: string | null;
  ce_relevant: boolean;
  confidence_score: number | null;
  material_categories: string[] | null;
  /** Resin codes detected in the full bill text (HDPE, EVA, EPS…); null until the polymer scan runs. */
  polymers?: string[] | null;
  instrument_type: string | null;
  /** Full instrument set (a law is often several at once); instrument_type is the primary. */
  instrument_types?: string[] | null;
  urgency: string | null;
  ai_summary: string | null;
  /** "advances" | "weakens" | "neutral" — direction relative to the instrument. */
  policy_stance: string | null;
  /** "ai" | "heuristic" — how policy_stance was derived. */
  stance_source: string | null;
  /** Classification transparency: false = auto-classified only, true = human spot-checked. */
  reviewed?: boolean;
  source_url: string | null;
  /** Source-link health from the auditor: "alive" | "redirected" | "dead" | "blocked"; null = unchecked. */
  source_url_status?: string | null;
  /** Resolved URL when source_url_status is "redirected" — where the page actually moved. */
  source_url_final?: string | null;
  litigation_case_count: number;
  max_preemption_risk: number | null;
}

/** A full-text search result from GET /bills/search — a bill plus the highlighted snippet(s)
 *  where the query matched in the bill text. `snippets` carry <mark>…</mark> around the match. */
export interface BillSearchHit extends BillSummary {
  snippets: string[];
  text_indexed: boolean;
}

/** Full-text index coverage — how many bills the deep search actually covers. indexed_bills === 0
 *  means the index isn't populated on this environment yet (deep-search UI stays hidden). */
export interface TextCoverageStats {
  indexed_bills: number;
  total_bills: number;
}

export interface BillDetail extends BillSummary {
  description: string | null;
  /** The paid Sonnet extraction — present only on the per-bill detail, never on the bulk list. */
  compliance_details: ComplianceDetails | null;
  created_at: string;
  updated_at: string;
}

export interface StateMapSummary {
  state: string;
  enacted_count: number;
  pending_count: number;
  total_relevant: number;
  material_categories: string[];
}

/** One (year, status) bucket from /bills/timeline — count of EPR bills that last reached `status` in `year`. */
export interface BillTimelinePoint {
  year: number;
  status: string;
  count: number;
}

/** One (year, stance) bucket from /bills/stance-momentum — advances | weakens | neutral. */
export interface BillStancePoint {
  year: number;
  stance: string;
  count: number;
}

/** One (instrument × material) cell from /bills/instrument-material-matrix. */
export interface InstrumentMaterialCell {
  instrument_type: string;
  material_category: string;
  count: number;
}

/** One state's CE-vs-baseline passage gap from /insights/state-gap. */
export interface StateGapRow {
  state: string;
  ce_rate: number;
  ce_enacted: number;
  ce_total: number;
  baseline_rate: number | null;
  gap: number | null;
}

/** One legislative biennium for a state from /insights/state-cycles — the gap as a trend over cycles. */
export interface StateCycleRow {
  biennium: string;
  start_year: number;
  ce_total: number;
  ce_enacted: number;
  ce_rate: number | null;
  baseline_introduced: number;
  baseline_enacted: number;
  baseline_rate: number | null;
  gap: number | null;
  in_flight: boolean;
}

/** One bill a champion sponsored (from /insights/champions/{id}/bills) — carries its source. */
export interface ChampionBill {
  bill_id: number | null;
  state: string | null;
  bill_number: string | null;
  instrument: string | null;
  enacted: boolean;
  source_url: string | null;
}

/** A CE champion (legislator) from /insights/champions. */
export interface ChampionSummary {
  person_id: string | null;
  name: string | null;
  party: string | null;
  chamber: string | null;
  district: string | null;
  active: boolean;
  states: string[];
  primary_sponsorships: number;
  cosponsorships: number;
  total_ce_bills: number;
  enacted_count: number;
  success_rate: number | null;
  instruments: string[];
  materials: string[];
}

export interface DeadlineSummary {
  id: number;
  state: string;
  deadline_type: string;
  deadline_date: string;
  description: string | null;
  who_affected: string | null;
  bill_id: number | null;
  bill_number: string | null;
  bill_title: string | null;
  /** Linked bill's material categories — lets the client scope-filter without bulk-loading bills. */
  material_categories?: string[] | null;
}

/** Ungated aggregate counts for the Upcoming Deadlines surfaces (metric cards + scoped banner). */
export interface DeadlineStats {
  total_upcoming: number;
  within_30: number;
  within_90: number;
  next_date: string | null;
  states: string[];
}

export interface ComplianceEntityRef {
  id: number;
  slug: string;
  name: string;
  entity_type: 'pro' | 'agency' | string;
  url: string | null;
  registration_url: string | null;
  jurisdiction_scope: string | null;
}

export interface CompliancePathway {
  bill_id: number;
  bill_number: string | null;
  bill_title: string | null;
  material_categories: string[] | null;
  management_model: string | null;
  action_type: string | null;
  action_summary: string | null;
  registration_url: string | null;
  next_deadline_date: string | null;
  has_fee: boolean;
  entity: ComplianceEntityRef | null;
}

/** One documented real-world outcome of an enacted law — the Insights "Real-World Impact" feed. */
export interface BillOutcome {
  id: number;
  slug: string;
  bill_id: number | null;
  state: string | null;
  bill_number: string | null;
  law_title: string | null;
  instrument_type: string | null;
  material_categories: string[] | null;
  /** "positive" | "negative" | "mixed" — direction of the documented effect. */
  direction: 'positive' | 'negative' | 'mixed' | string;
  metric_label: string | null;
  metric_value: number | null;
  metric_unit: string | null;
  /** Pre-formatted figure override; prefer over value+unit when present. */
  metric_display: string | null;
  summary: string;
  /** "direct" | "program" | "associated" — how tightly the figure ties to the statute. */
  attribution: 'direct' | 'program' | 'associated' | string | null;
  as_of_date: string | null;
  source_name: string | null;
  source_url: string | null;
  confidence: number | null;
  reviewed: boolean;
  /** Remediation arc (negative/mixed only): the later law that fixed the problem. */
  remediation_note: string | null;
  remediation_bill_number: string | null;
  remediated_by_bill_id: number | null;
}

export interface FederalActionSummary {
  id: number;
  agency: string | null;
  title: string | null;
  action_type: string | null;
  published_date: string | null;
  comment_deadline: string | null;
  effective_date: string | null;
  document_url: string | null;
  preemption_risk: string | null;
  friction_type: string | null;
  instrument_type: string | null;
  material_categories: string[] | null;
  ai_summary: string | null;
  ce_relevant: boolean;
}

export interface LitigationEventSummary {
  id: number;
  event_type: string;
  date_filed: string | null;
  description: string | null;
  summary: string | null;
  significance: string | null;
  document_url: string | null;
}

export interface LitigationCaseSummary {
  id: number;
  courtlistener_id: number;
  case_name: string;
  docket_number: string | null;
  court_id: string;
  court_name: string | null;
  date_filed: string | null;
  date_terminated: string | null;
  assigned_judge: string | null;
  case_status: string | null;
  challenge_type: string | null;
  plaintiff_type: string | null;
  key_plaintiffs: string[] | null;
  related_law_id: number | null;
  related_state: string | null;
  related_statute: string | null;
  preemption_risk: number | null;
  cl_url: string | null;
  last_activity_date: string | null;
  event_count: number;
}

export interface LitigationCaseDetail extends LitigationCaseSummary {
  events: LitigationEventSummary[];
}

export interface CompanyMaterialSummary {
  id: string;
  material_category: string;
  annual_volume_tonnes: number | null;
  volume_confidence: number | null;
  source: string | null;
}

export interface CompanyStatePresenceSummary {
  id: string;
  state: string;
  presence_type: string;
  is_primary: boolean;
}

export interface CompanySummary {
  id: string;
  name: string;
  hq_state: string | null;
  naics_codes: string[] | null;
  operating_states: string[] | null;
  total_annual_volume_tonnes: number | null;
  volume_confidence: number | null;
}

export interface CompanyDetail extends CompanySummary {
  duns_number: string | null;
  cik: string | null;
  epa_registry_id: string | null;
  volume_source: string | null;
  materials: CompanyMaterialSummary[];
  state_presences: CompanyStatePresenceSummary[];
  created_at: string;
  updated_at: string;
}

export interface ImpactScoreResponse {
  id: string;
  company_id: string;
  bill_id: number;
  composite_score: number;
  material_score: number | null;
  geographic_score: number | null;
  severity_score: number | null;
  estimated_annual_cost: number | null;
  cost_confidence: number | null;
  volume_confidence: number | null;
  score_breakdown: Record<string, unknown> | null;
  calculated_at: string;
}

export interface ExposureRanking {
  company: CompanySummary;
  impact_score: ImpactScoreResponse;
}

export interface ExposureBriefResponse {
  id: string;
  company_id: string;
  bill_id: number;
  brief_json: Record<string, unknown> | null;
  generated_at: string;
  ttl_expires_at: string | null;
}

// ─── Company obligations ("are you affected + next deadline") ──────────────
export interface CompanyObligationDeadline {
  deadline_date: string;
  deadline_type: string;
  description: string | null;
  who_affected: string | null;
  source_url: string | null;
}

export interface StakesPenalty {
  amount_usd: number;
  unit: string; // "day" | "violation"
  raw: string;
}

export interface StakesFee {
  annual_fee_low_usd: number;
  annual_fee_high_usd: number;
  annual_fee_grounded: boolean;
  fee_basis: string;
  eco_modulation_swing_usd: number | null;
  eco_modulation_floor_usd: number | null;
  eco_modulation_notes: string[];
  citation: string | null;
  confidence: number;
}

export interface FinancialStakes {
  penalty: StakesPenalty | null;
  fee: StakesFee | null;
  pro_membership_usd: number | null;
  has_any: boolean;
}

export interface CompanyObligation {
  bill_id: number;
  state: string;
  bill_number: string | null;
  bill_title: string | null;
  status: string | null;
  source_url: string | null;
  matched_materials: string[];
  presence_types: string[];
  next_deadline: CompanyObligationDeadline | null;
  upcoming_deadline_count: number;
  total_deadline_count: number;
  stakes: FinancialStakes | null;
}

export interface CompanyObligationsResponse {
  company_id: string;
  company_name: string;
  affected_bill_count: number;
  affected_states: string[];
  upcoming_deadline_count: number;
  next_deadline_date: string | null;
  obligations: CompanyObligation[];
  max_penalty_per_day_usd: number | null;
  portfolio_annual_fee_low_usd: number | null;
  portfolio_annual_fee_high_usd: number | null;
  portfolio_eco_modulation_swing_usd: number | null;
  any_fee_grounded: boolean;
}

// Query param types
export interface BillParams {
  limit?: number;
  offset?: number;
  state?: string;
  /** Jurisdiction family: omitted = US only; "EU"; or "all" for every region. See migration 031. */
  region?: string;
  status?: string;
  ce_relevant?: boolean;
  urgency?: string;
  material_category?: string;
  instrument_type?: string;
  /** "advances" | "weakens" | "neutral" — drill-down from the momentum chart. */
  policy_stance?: string;
  /** Year of status_date — drill-down from a timeline/momentum bucket. */
  year?: number;
  /** Inclusive status_date year range — per-cycle (biennium) drill-down. */
  year_from?: number;
  year_to?: number;
  /** Confidence floor (momentum drill-down passes 0.7 to match the chart). */
  min_confidence?: number;
  search?: string;
}

export interface DeadlineParams {
  days_ahead?: number;
  state?: string;
  /** csv of material_category slugs — scopes the free teaser + the stats counts. */
  materials?: string;
  /** csv of two-letter state codes — ditto. */
  states?: string;
}

export interface FederalActionParams {
  days_back?: number;
  limit?: number;
  action_type?: string;
  preemption_risk?: string;
  instrument_type?: string;
  material_category?: string;
  friction_type?: string;
  ce_relevant?: boolean;
}
