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

/** Every v2+ extracted dimension is an "envelope": an explicit status (so "measure doesn't address
 * this" is distinct from "not yet extracted") plus a verbatim source_excerpt for citation. */
export type DimensionStatus = 'present' | 'absent' | 'not_applicable';
export interface DimensionEnvelope {
  status: DimensionStatus;
  source_excerpt?: string;
}
export interface EcoModulation extends DimensionEnvelope { criteria?: string[]; }
export interface RecycledContent extends DimensionEnvelope {
  minimums?: { material: string; percent: number | null; by_year: string | null }[];
}
export interface Penalties extends DimensionEnvelope {
  max_amount?: number | null; currency?: string; per?: string | null;
}
export interface CollectionTargets extends DimensionEnvelope {
  targets?: { material: string; percent: number | null; by_year: string | null;
    basis: 'weight' | 'units' | 'value_recovered' | 'material_specific' | 'unspecified' }[];
}
export interface ProStructure extends DimensionEnvelope {
  model?: 'single_pro' | 'competitive_pros' | 'government_run' | 'individual' | 'unspecified';
  needs_assessment?: boolean; named_pros?: string[];
}
export interface BansRestrictions extends DimensionEnvelope {
  items?: { target: string; type: 'sales_ban' | 'material_restriction' | 'design_ban';
    effective_date: string | null }[];
}
export interface FeeAmounts extends DimensionEnvelope {
  rates?: { basis: string; amount: number | null; currency?: string; material?: string | null }[];
}
export interface Labeling extends DimensionEnvelope {
  requirements?: { type: string; on_pack?: boolean; detail?: string }[];
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
  extraction_version?: number;
  // v2+ structured dimensions (see scripts/extract_dimensions.py / sonnet_extractor.py).
  eco_modulation?: EcoModulation;
  recycled_content?: RecycledContent;
  penalties?: Penalties;
  collection_targets?: CollectionTargets;
  pro_structure?: ProStructure;
  bans_restrictions?: BansRestrictions;
  fee_amounts?: FeeAmounts;
  labeling?: Labeling;
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

/** One bill's persisted full statute text (GET /bills/{id}/text). `text` is null when we haven't
 *  ingested this bill's text yet — the modal then falls back to the source link. */
export interface BillFullText {
  bill_id: number;
  text: string | null;
  char_len: number | null;
  source: string | null;
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
  /** Jurisdiction family (US, EU, FR, …). Present when the Insights region filter groups by region. */
  region?: string;
}

/** One (year, stance) bucket from /bills/stance-momentum — advances | weakens | neutral. */
export interface BillStancePoint {
  year: number;
  stance: string;
  count: number;
  region?: string;
}

// "Ask the Bills" (POST /research/ask) — a cited answer, an optional SQL-backed chart, and a
// coverage note so an answer never implies whole-corpus completeness it doesn't have.
export interface ResearchChartBar { label: string; value: number; }
export interface ResearchChart { title: string; bars: ResearchChartBar[]; }
export interface ResearchCitation {
  bill_id: number;
  region?: string | null;
  state?: string | null;
  bill_number?: string | null;
  year?: number | null;
  snippet?: string | null;
  // Full summary so an in-sentence [STATE BILL_NUMBER] marker or the cited-bills list can open the
  // same bill modal the relevant-bills table opens — even for a cited bill not on table page 1.
  bill?: BillSummary | null;
}
// One page of the full relevant-bill set backing an answer (GET /research/bills for pages 2+).
// `total` is the complete count across all pages, so the table can page through every relevant bill.
export interface ResearchBillPage {
  total: number;
  page: number;
  page_size: number;
  strategy: string;   // 'text' | 'dimension:<key>' | 'text_broad'
  items: BillSummary[];
}
export interface ResearchAnswer {
  answer: string;
  citations: ResearchCitation[];
  chart?: ResearchChart | null;
  coverage_note?: string | null;
  bills?: ResearchBillPage | null;
}

// --- Bill-strength evaluation (POST /evaluate/bill) — see app/evaluation/strength.py --------------
// Strength is *conditional on the material*: a lead-acid battery bill can be lean and strong; a
// textiles bill that lean is weak. So we position the material into a regime, then score the bill's
// extracted mechanisms against the baseline that regime demands (a fit score, not a flat count).
export interface RegimeAxes {
  value_density: number;      // 0..1 — concentrated worth
  dispersion: number;         // 0..1 — spread thin across many holders
  channel_maturity: number;   // 0..1 — an established reverse channel exists
}
export interface BillRegime {
  key: 'incremental_viable' | 'critical_mass';
  label: string;
  material: string;
  confidence: 'high' | 'low' | 'estimated';  // seed table | fixed fallback | LLM estimate
  rationale: string;
  axes: RegimeAxes;
}
export interface RequirementResult {
  key: string;
  label: string;
  importance: 'load_bearing' | 'supporting' | 'bonus';
  status: 'met' | 'partial' | 'missing';
  weight: number;
  your_value: string;   // what this bill has
  baseline: string;     // what a strong bill for this regime carries
  note?: string | null;
}
export interface StrengthScore {
  value: number;        // 0..100
  band: 'strong' | 'moderate' | 'weak';
  summary: string;
}
// Corpus cross-check: the draft measured against ENACTED laws in the same material regime — which
// mechanisms the ones that made it onto the books carried, and which produced documented outcomes.
export interface AnalogOutcome {
  direction: 'positive' | 'negative' | 'mixed';
  summary: string;
  metric?: string | null;
  attribution?: string | null;
  source_name?: string | null;
  source_url?: string | null;
}
export interface CorpusAnalog {
  bill_id?: number | null;
  region?: string | null;
  state?: string | null;
  bill_number?: string | null;
  title?: string | null;
  year?: number | null;
  material: string;
  same_material: boolean;
  reviewed: boolean;
  mechanisms: Record<string, 'met' | 'partial' | 'missing'>;
  outcomes: AnalogOutcome[];
}
export interface CorpusBaselinePoint {
  key: string;
  label: string;
  analog_share: number;   // 0..1 of same-regime enacted analogs carrying this mechanism
  your_status: 'met' | 'partial' | 'missing';
}
export interface CorpusCrossCheck {
  regime: string;
  analog_count: number;
  same_material_count: number;
  value_basis_share?: number | null;
  baseline: CorpusBaselinePoint[];
  analogs: CorpusAnalog[];
  note: string;
}

export interface EvaluateResponse {
  regime: BillRegime;
  score: StrengthScore;
  requirements: RequirementResult[];
  flags: string[];
  compliance_details: ComplianceDetails;  // extracted envelopes, rendered with dimensions.ts
  baseline_details: ComplianceDetails;     // the strong model bill for this regime (diff target)
  corpus?: CorpusCrossCheck | null;
  title?: string | null;
  jurisdiction?: string | null;
}

// The value×dispersion×channel map of known materials + regime — GET /evaluate/material-map.
export interface MaterialMapPoint {
  material: string;
  value_density: number;      // log-normalized recoverable $/tonne, 0..1
  dispersion: number;
  channel_maturity: number;
  regime: 'incremental_viable' | 'critical_mass';
  value_usd_per_tonne?: number | null;  // raw anchor behind value_density
}

/** One (basis, region) bucket from /bills/collection-target-basis — how collection/recovery targets
 * are measured (weight | units | value_recovered | material_specific | unspecified). */
export interface CollectionTargetBasisPoint {
  basis: string;
  count: number;
  region?: string | null;
}

/** One (year, region) bucket from /bills/laws-in-force — CE laws that came into force that year. */
export interface LawsInForcePoint {
  year: number;
  region: string;
  count: number;
}

/** One (instrument × material) cell from /bills/instrument-material-matrix. */
export interface InstrumentMaterialCell {
  instrument_type: string;
  material_category: string;
  count: number;
  region?: string;
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
  /** Multi-region CSV (US,EU,FR…); from the global region filter. Takes precedence over `region`. */
  regions?: string;
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
  /** CSV of compliance-dimension keys (eco_modulation,collection_targets…) — a bill matches only if
   * each is `present`. Filtered server-side since compliance_details isn't in the list payload. */
  dimensions?: string;
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
