import type {
  BillSummary,
  BillDetail,
  BillParams,
  StateMapSummary,
  BillTimelinePoint,
  DeadlineSummary,
  DeadlineParams,
  FederalActionSummary,
  FederalActionParams,
  LitigationCaseSummary,
  LitigationCaseDetail,
  CompanySummary,
  CompanyDetail,
  CompanyObligationsResponse,
  ExposureRanking,
  ExposureBriefResponse,
  CompliancePathway,
} from './types';

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

function buildUrl(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const url = new URL(`${API}${path}`);
  if (params) {
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null && val !== '') {
        url.searchParams.set(key, String(val));
      }
    }
  }
  return url.toString();
}

async function apiFetch<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error ${res.status}: ${url}`);
  return res.json();
}

export interface SubscribePayload {
  email: string;
  /** Optional — the subscriber's organization. */
  organization?: string;
  /** Two-letter state codes, or ["ALL"] for every jurisdiction. */
  states: string[];
  /** Policy instrument slugs (epr, right_to_repair, …), or ["ALL"] for every topic. */
  instrument_types: string[];
  /** Optional material_category slugs to narrow alerts; omit/["ALL"] for every material. */
  material_categories?: string[];
}

/** Public "get free updates" sign-up — creates an alert subscription. */
export async function subscribe(payload: SubscribePayload): Promise<void> {
  const res = await fetch(buildUrl('/subscriptions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Subscribe failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
}

/** Which paid tier a visitor expressed interest in — the willingness-to-pay experiment. */
export type PlanInterest = 'pro' | 'team' | 'enterprise' | 'api' | 'company_impact' | 'bespoke';

export interface AccessRequestPayload {
  email: string;
  name?: string;
  organization?: string;
  plan_interest: PlanInterest;
  message?: string;
  /** Funnel attribution: "pricing" | "company_gate". */
  source?: string;
}

/** Capture a "request access / pricing" click. No billing — just records interest + segment. */
export async function requestAccess(payload: AccessRequestPayload): Promise<void> {
  const res = await fetch(buildUrl('/access-requests'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Request failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
}

export async function fetchBills(params?: BillParams): Promise<BillSummary[]> {
  return apiFetch<BillSummary[]>(buildUrl('/bills', params as Record<string, string | number | boolean | undefined>));
}

export async function fetchBill(id: number): Promise<BillDetail> {
  return apiFetch<BillDetail>(buildUrl(`/bills/${id}`));
}

export async function fetchMapSummary(): Promise<StateMapSummary[]> {
  return apiFetch<StateMapSummary[]>(buildUrl('/bills/map-summary'));
}

export async function fetchBillTimeline(params?: {
  instrument_type?: string;
  material_category?: string;
}): Promise<BillTimelinePoint[]> {
  return apiFetch<BillTimelinePoint[]>(
    buildUrl('/bills/timeline', params as Record<string, string | number | boolean | undefined>),
  );
}

export async function fetchDeadlines(params?: DeadlineParams): Promise<DeadlineSummary[]> {
  return apiFetch<DeadlineSummary[]>(buildUrl('/bills/deadlines/upcoming', params as Record<string, string | number | boolean | undefined>));
}

export async function fetchFederalActions(params?: FederalActionParams): Promise<FederalActionSummary[]> {
  return apiFetch<FederalActionSummary[]>(buildUrl('/federal-actions', params as Record<string, string | number | boolean | undefined>));
}

export async function fetchPreemptionRisk(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(buildUrl('/federal-actions/preemption-risk'));
}

export async function fetchLitigationCases(): Promise<LitigationCaseSummary[]> {
  return apiFetch<LitigationCaseSummary[]>(buildUrl('/litigation-cases'));
}

export async function fetchLitigationCase(id: number): Promise<LitigationCaseDetail> {
  return apiFetch<LitigationCaseDetail>(buildUrl(`/litigation-cases/${id}`));
}

export async function fetchBillLitigationCases(billId: number): Promise<LitigationCaseSummary[]> {
  return apiFetch<LitigationCaseSummary[]>(buildUrl(`/bills/${billId}/litigation-cases`));
}

export async function fetchCompanies(params?: { limit?: number; search?: string }): Promise<CompanySummary[]> {
  return apiFetch<CompanySummary[]>(buildUrl('/companies', params as Record<string, string | number | boolean | undefined>));
}

export async function fetchCompany(id: string): Promise<CompanyDetail> {
  return apiFetch<CompanyDetail>(buildUrl(`/companies/${id}`));
}

export async function fetchExposureRanking(billId?: number, limit = 50): Promise<ExposureRanking[]> {
  const params: Record<string, string | number | boolean | undefined> = { limit };
  if (billId !== undefined) params.bill_id = billId;
  return apiFetch<ExposureRanking[]>(buildUrl('/companies/exposure-ranking', params));
}

export async function fetchExposureBrief(companyId: string, billId: number): Promise<ExposureBriefResponse> {
  return apiFetch<ExposureBriefResponse>(buildUrl(`/companies/${companyId}/exposure-brief`, { bill_id: billId }));
}

export async function fetchCompanyObligations(companyId: string): Promise<CompanyObligationsResponse> {
  return apiFetch<CompanyObligationsResponse>(buildUrl(`/companies/${companyId}/obligations`));
}

/** Per-state compliance pathways — one "how do I comply" record per enacted EPR law. */
export async function fetchCompliancePathways(state: string): Promise<CompliancePathway[]> {
  return apiFetch<CompliancePathway[]>(buildUrl('/compliance/pathways', { state }));
}
