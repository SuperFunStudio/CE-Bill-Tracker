import type {
  BillSummary,
  BillDetail,
  BillParams,
  StateMapSummary,
  DeadlineSummary,
  DeadlineParams,
  FederalActionSummary,
  FederalActionParams,
  LitigationCaseSummary,
  LitigationCaseDetail,
  CompanySummary,
  CompanyDetail,
  ExposureRanking,
  ExposureBriefResponse,
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

export async function fetchBills(params?: BillParams): Promise<BillSummary[]> {
  return apiFetch<BillSummary[]>(buildUrl('/bills', params as Record<string, string | number | boolean | undefined>));
}

export async function fetchBill(id: number): Promise<BillDetail> {
  return apiFetch<BillDetail>(buildUrl(`/bills/${id}`));
}

export async function fetchMapSummary(): Promise<StateMapSummary[]> {
  return apiFetch<StateMapSummary[]>(buildUrl('/bills/map-summary'));
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
