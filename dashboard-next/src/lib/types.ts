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
  state: string;
  bill_number: string | null;
  title: string | null;
  status: string | null;
  last_action_date: string | null;
  epr_relevant: boolean;
  confidence_score: number | null;
  material_categories: string[] | null;
  instrument_type: string | null;
  urgency: string | null;
  ai_summary: string | null;
  /** "advances" | "weakens" | "neutral" — direction relative to the instrument. */
  policy_stance: string | null;
  /** "ai" | "heuristic" — how policy_stance was derived. */
  stance_source: string | null;
  /** Classification transparency: false = auto-classified only, true = human spot-checked. */
  reviewed?: boolean;
  source_url: string | null;
  compliance_details: ComplianceDetails | null;
  litigation_case_count: number;
  max_preemption_risk: number | null;
}

export interface BillDetail extends BillSummary {
  description: string | null;
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
  ai_summary: string | null;
  epr_relevant: boolean;
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
}

export interface CompanyObligationsResponse {
  company_id: string;
  company_name: string;
  affected_bill_count: number;
  affected_states: string[];
  upcoming_deadline_count: number;
  next_deadline_date: string | null;
  obligations: CompanyObligation[];
}

// Query param types
export interface BillParams {
  limit?: number;
  offset?: number;
  state?: string;
  status?: string;
  epr_relevant?: boolean;
  urgency?: string;
  material_category?: string;
  search?: string;
}

export interface DeadlineParams {
  days_ahead?: number;
  state?: string;
}

export interface FederalActionParams {
  days_back?: number;
  limit?: number;
  action_type?: string;
}
