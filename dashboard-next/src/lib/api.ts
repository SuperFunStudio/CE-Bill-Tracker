import type {
  BillSummary,
  BillSearchHit,
  TextCoverageStats,
  BillDetail,
  BillFullText,
  BillParams,
  StateMapSummary,
  BillTimelinePoint,
  BillStancePoint,
  CollectionTargetBasisPoint,
  FeeAmountsSummary,
  ResearchAnswer,
  ResearchBillPage,
  EvaluateResponse,
  MaterialMapPoint,
  InstrumentMaterialCell,
  LawsInForcePoint,
  StateGapRow,
  StateCycleRow,
  ChampionSummary,
  ChampionBill,
  DeadlineSummary,
  DeadlineParams,
  FederalActionSummary,
  FederalActionStats,
  FederalActionParams,
  LitigationCaseSummary,
  LitigationCaseDetail,
  CompanySummary,
  CompanyDetail,
  CompanyObligationsResponse,
  ExposureRanking,
  ExposureBriefResponse,
  CompliancePathway,
  BillOutcome,
  DeadlineStats,
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

async function apiFetch<T>(url: string, token?: string | null): Promise<T> {
  const res = await fetch(url, token ? { headers: { Authorization: `Bearer ${token}` } } : undefined);
  if (!res.ok) throw new Error(`API error ${res.status}: ${url}`);
  return res.json();
}

export interface SubscribePayload {
  email: string;
  /** Optional — the subscriber's organization. */
  organization?: string;
  /** LEGACY flat jurisdiction list (US-only). Prefer region_scope; back-compat maps it to US. */
  states?: string[];
  /** Region-keyed jurisdiction scope: { US: ["CA","OR"], EU: ["*"] }. "*" = whole region. Empty = all. */
  region_scope?: Record<string, string[]>;
  /** Policy instrument slugs (epr, right_to_repair, …), or ["ALL"] for every topic. */
  instrument_types: string[];
  /** Optional material_category slugs to narrow alerts; omit/["ALL"] for every material. */
  material_categories?: string[];
}

export interface SubscribeResult {
  /** True when a confirmation email was sent and the subscription is NOT yet live. */
  pending_confirmation: boolean;
}

/** Public "get free updates" sign-up — creates an alert subscription.
 *
 * Double opt-in: an emailed sign-up comes back inactive with pending_confirmation=true, and nothing
 * is sent to the address until the emailed link is clicked. Callers must reflect that — telling
 * someone they're subscribed when they aren't is how a confirmation email gets ignored. Older API
 * builds don't return the field; treat its absence as "pending" rather than assuming the optimistic
 * case, so the copy can never overstate what happened. */
export async function subscribe(payload: SubscribePayload): Promise<SubscribeResult> {
  const res = await fetch(buildUrl('/subscriptions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Subscribe failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  const body = await res.json().catch(() => null);
  return { pending_confirmation: body?.pending_confirmation !== false };
}

/** Which paid tier a visitor expressed interest in — the willingness-to-pay experiment. */
export type PlanInterest = 'pro' | 'team' | 'enterprise' | 'api' | 'company_impact' | 'bespoke' | 'research';

export interface AccessRequestPayload {
  email: string;
  name?: string;
  organization?: string;
  plan_interest: PlanInterest;
  message?: string;
  /** Funnel attribution: "pricing" | "company_gate". */
  source?: string;
  /** Marketing attribution (utm_* + referrer) captured on landing — surfaced in the lead email. */
  attribution?: Record<string, string>;
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

/** "Ask the Bills" (Pro) — POST a natural-language question, get a cited answer + optional chart. */
/** Ask a question. Pass `sessionId` to continue an existing thread — the server treats the question as
 *  a follow-up (condensed against the thread) and appends it as the next turn. Omit it to start fresh. */
/** An API error that preserves the HTTP status + server `detail` so callers can branch on it — Ask the
 *  Atlas uses this to tell the anonymous free-limit wall ("ask_free_limit") from the free-account
 *  upgrade wall ("ask_upgrade_required"). */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail || `API error ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export async function askResearch(
  question: string, token?: string | null, sessionId?: string | null,
): Promise<ResearchAnswer> {
  const res = await fetch(buildUrl('/research/ask'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ question, ...(sessionId ? { session_id: sessionId } : {}) }),
  });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json())?.detail ?? ''; } catch { /* non-JSON body */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export interface ResearchSessionListItem {
  session_id: string;
  title: string;
  preview: string;
  turns: number;
  shared: boolean;
  updated_at: string | null;
}

/** The signed-in member's own Ask-the-Atlas history (My Library). Private to the caller. */
export async function fetchMyResearchSessions(token?: string | null): Promise<ResearchSessionListItem[]> {
  return apiFetch<ResearchSessionListItem[]>(buildUrl('/research/my-sessions'), token);
}

/** One persisted turn of an owned thread — the question and the stored answer markdown. Rich
 *  citations/charts aren't persisted per turn, so a restored turn shows the answer text (inline
 *  [STATE BILL_NUMBER] markers render as plain text); asking a follow-up produces a fresh, cited turn. */
export interface ResearchTurnOut {
  seq: number;
  question: string;
  retrieval_query: string | null;
  answer: string | null;
  bill_total: number;
}
export interface ResearchSessionOut {
  session_id: string;
  title: string | null;
  turns: ResearchTurnOut[];
}

/** Load one owned research thread with its turns in order, so the Ask page can reopen and continue a
 *  saved conversation. 404 if the session isn't owned by the caller. */
export async function fetchResearchSession(
  sessionId: string, token?: string | null,
): Promise<ResearchSessionOut> {
  return apiFetch<ResearchSessionOut>(buildUrl(`/research/session/${sessionId}`), token);
}

/** Pages 2+ of the full relevant-bill set for an asked question (SQL-only, no LLM). Prev/Next on the
 *  Ask page call this; the cascade is deterministic so pages align with the answer's page 1. */
export async function fetchResearchBills(
  question: string, page: number, pageSize: number, token?: string | null,
): Promise<ResearchBillPage> {
  const res = await fetch(buildUrl('/research/bills', { question, page, page_size: pageSize }), {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

/** "Evaluate a Bill" (Pro) — POST pasted measure text, get its material regime + a fit score against
 *  the baseline that regime demands, per-mechanism, plus the extracted compliance envelopes. */
export async function evaluateBill(
  input: { text: string; title?: string; jurisdiction?: string; region?: string },
  token?: string | null,
): Promise<EvaluateResponse> {
  const res = await fetch(buildUrl('/evaluate/bill'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `API error ${res.status}`);
  }
  return res.json();
}

/** The material-position map (value×dispersion×channel + regime) — reference data for the viz. */
export async function fetchMaterialMap(): Promise<MaterialMapPoint[]> {
  return apiFetch<MaterialMapPoint[]>(buildUrl('/evaluate/material-map'));
}

export async function fetchBill(id: number): Promise<BillDetail> {
  return apiFetch<BillDetail>(buildUrl(`/bills/${id}`));
}

/** One bill's persisted full statute text (side table). `text` is null when not yet ingested. */
export async function fetchBillText(id: number): Promise<BillFullText> {
  return apiFetch<BillFullText>(buildUrl(`/bills/${id}/text`));
}

/** Full-text search over persisted bill text — returns bills whose statute text matches `q`
 *  (even when the title/summary don't), each with highlighted ts_headline snippets. `regions` is the
 *  same CSV the bill list takes ("all" / undefined = every region) and is applied server-side before
 *  the rank cutoff, so a region-scoped explorer never gets out-of-region hits. */
export async function fetchBillSearch(q: string, limit = 50, regions?: string): Promise<BillSearchHit[]> {
  return apiFetch<BillSearchHit[]>(buildUrl('/bills/search', { q, limit, regions }));
}

/** Founding-seat counter for the pricing page — { total, claimed, remaining }, counted from stamped
 *  founding entitlements server-side. Public/unauthenticated; see app/api/billing.py. */
export async function fetchFoundingSeats(): Promise<{ total: number; claimed: number; remaining: number }> {
  return apiFetch<{ total: number; claimed: number; remaining: number }>(buildUrl('/billing/founding-seats'));
}

/** How many bills the full-text search actually covers — for the deep-search coverage note. */
export async function fetchBillTextCoverage(): Promise<TextCoverageStats> {
  return apiFetch<TextCoverageStats>(buildUrl('/bills/text-coverage'));
}

export async function fetchMapSummary(): Promise<StateMapSummary[]> {
  return apiFetch<StateMapSummary[]>(buildUrl('/bills/map-summary'));
}

export async function fetchBillTimeline(params?: {
  instrument_type?: string;
  material_category?: string;
  /** CSV of region codes (US,EU,FR…) to scope the timeline; omit / "all" for every region. */
  regions?: string;
}): Promise<BillTimelinePoint[]> {
  return apiFetch<BillTimelinePoint[]>(
    buildUrl('/bills/timeline', params as Record<string, string | number | boolean | undefined>),
  );
}

/** Per-year bill counts by policy stance (advances/weakens/neutral) — the Insights "policy momentum" view. */
export async function fetchStanceMomentum(params?: {
  instrument_type?: string;
  material_category?: string;
  min_confidence?: number;
  regions?: string;
}): Promise<BillStancePoint[]> {
  return apiFetch<BillStancePoint[]>(
    buildUrl('/bills/stance-momentum', params as Record<string, string | number | boolean | undefined>),
  );
}

/** Bill counts per (instrument × material) — the Insights coverage heatmap. */
export async function fetchInstrumentMaterialMatrix(params?: {
  min_confidence?: number;
  regions?: string;
  status?: string;
}): Promise<InstrumentMaterialCell[]> {
  return apiFetch<InstrumentMaterialCell[]>(
    buildUrl('/bills/instrument-material-matrix', params as Record<string, string | number | boolean | undefined>),
  );
}

/** Distribution of how collection/recovery targets are measured (weight vs value_recovered vs …),
 * per region — the Insights "how targets are measured" chart. */
export async function fetchCollectionTargetBasis(params?: { regions?: string }): Promise<CollectionTargetBasisPoint[]> {
  return apiFetch<CollectionTargetBasisPoint[]>(
    buildUrl('/bills/collection-target-basis', params as Record<string, string | number | boolean | undefined>),
  );
}

/** Bill-sourced fee coverage aggregate — open, full (spans every jurisdiction, ignores the region
 * filter). Feeds the Insights "fees across jurisdictions" chart. See /compliance/fee-amounts/summary. */
export async function fetchFeeSummary(): Promise<FeeAmountsSummary> {
  return apiFetch<FeeAmountsSummary>(buildUrl('/compliance/fee-amounts/summary'));
}

/** Per-year, per-region CE laws that came into force — cumulated client-side into the "laws on the
 * books over time" momentum line (works for foreign regs, which have no introduced→enacted pipeline). */
export async function fetchLawsInForce(params?: { regions?: string }): Promise<LawsInForcePoint[]> {
  return apiFetch<LawsInForcePoint[]>(
    buildUrl('/bills/laws-in-force', params as Record<string, string | number | boolean | undefined>),
  );
}

// The whole /insights router is behind CAP_INSIGHTS_IMPACT (a router-level dependency — see
// app/api/insights.py), so these four are token-REQUIRED, not token-optional: called without one they
// 401 for everyone, admins included. That is exactly what the Geography tab was doing. There is no
// teaser to fall back to here, so the token is a required argument rather than an optional tail
// parameter — a caller that forgets it should fail to compile, not at runtime in front of a member.
/** Per-state CE-vs-baseline passage gap — the Insights "Atlas Circular" table. */
export async function fetchStateGap(token: string | null): Promise<StateGapRow[]> {
  return apiFetch<StateGapRow[]>(buildUrl('/insights/state-gap'), token);
}

/** CE champion roster (slim). Active-only by default; filter by state. */
export async function fetchChampions(
  token: string | null,
  params?: {
    state?: string;
    active_only?: boolean;
    limit?: number;
  },
): Promise<ChampionSummary[]> {
  return apiFetch<ChampionSummary[]>(
    buildUrl('/insights/champions', params as Record<string, string | number | boolean | undefined>),
    token,
  );
}

/** One state's per-biennium CE-vs-baseline gap — the Insights per-cycle view. */
export async function fetchStateCycles(state: string, token: string | null): Promise<StateCycleRow[]> {
  return apiFetch<StateCycleRow[]>(buildUrl('/insights/state-cycles', { state }), token);
}

/** A champion's sponsored bills, each with its source_url. person_id contains a slash — pass it raw. */
export async function fetchChampionBills(personId: string, token: string | null): Promise<ChampionBill[]> {
  return apiFetch<ChampionBill[]>(buildUrl(`/insights/champions/${personId}/bills`), token);
}

/** Documented real-world outcomes of enacted laws — powers the Insights "Real-World Impact" spotlight. */
export async function fetchBillOutcomes(params?: {
  direction?: string;
  state?: string;
  /** US when omitted (the server's default), a region code, or "all" — 11 regions carry outcomes,
   *  so the global surfaces must pass "all" or they silently show only the US ones. */
  region?: string;
  reviewed_only?: boolean;
},
  /** CAP_INSIGHTS_IMPACT token for the FULL documented set. Without one the API returns the newest
   *  few — which is all the free homepage ticker rotates through anyway. */
  token?: string | null,
): Promise<BillOutcome[]> {
  return apiFetch<BillOutcome[]>(
    buildUrl('/bills/outcomes', params as Record<string, string | number | boolean | undefined>),
    token,
  );
}

/** Reviewed outcomes keyed by bill id — ONE request for the whole static build, read by every bill
 *  page's impact block. Ungated (one law's effect on that law's page is depth, not the cross-bill
 *  table); keys are strings because that's what JSON object keys are. */
export async function fetchBillOutcomeIndex(): Promise<Record<string, BillOutcome[]>> {
  return apiFetch<Record<string, BillOutcome[]>>(buildUrl('/bills/outcomes/by-bill'));
}

/** The Upcoming Deadlines list. Pro seats (pass a Firebase token) get the full merged calendar; an
 *  anonymous/free call gets only the soonest few rows as a teaser — the gate is enforced server-side. */
export async function fetchDeadlines(params?: DeadlineParams, token?: string | null): Promise<DeadlineSummary[]> {
  return apiFetch<DeadlineSummary[]>(
    buildUrl('/bills/deadlines/upcoming', params as Record<string, string | number | boolean | undefined>),
    token,
  );
}

/** Ungated aggregate deadline counts — powers the metric cards + scoped banner even for free visitors. */
export async function fetchDeadlineStats(params?: DeadlineParams): Promise<DeadlineStats> {
  return apiFetch<DeadlineStats>(
    buildUrl('/bills/deadlines/summary', params as Record<string, string | number | boolean | undefined>),
  );
}

/** Federal action rows. CAP_FEDERAL server-side: pass a token for the full list, otherwise the API
 *  returns a short teaser. Counts for free surfaces come from fetchFederalSummary instead. */
export async function fetchFederalActions(
  params?: FederalActionParams,
  token?: string | null,
): Promise<FederalActionSummary[]> {
  return apiFetch<FederalActionSummary[]>(
    buildUrl('/federal-actions', params as Record<string, string | number | boolean | undefined>),
    token,
  );
}

/** Ungated federal counts — total and how many carry High preemption risk. */
export async function fetchFederalSummary(): Promise<FederalActionStats> {
  return apiFetch<FederalActionStats>(buildUrl('/federal-actions/summary'));
}

export async function fetchPreemptionRisk(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(buildUrl('/federal-actions/preemption-risk'));
}

/** The bulk litigation feed — CAP_FEDERAL, 403 without a qualifying token. */
export async function fetchLitigationCases(token?: string | null): Promise<LitigationCaseSummary[]> {
  return apiFetch<LitigationCaseSummary[]>(buildUrl('/litigation-cases'), token);
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

/** Admin-gated (the brief generation calls Claude Sonnet) — pass the caller's Firebase token. */
export async function fetchExposureBrief(companyId: string, billId: number, token?: string | null): Promise<ExposureBriefResponse> {
  return apiFetch<ExposureBriefResponse>(buildUrl(`/companies/${companyId}/exposure-brief`, { bill_id: billId }), token);
}

export async function fetchCompanyObligations(companyId: string): Promise<CompanyObligationsResponse> {
  return apiFetch<CompanyObligationsResponse>(buildUrl(`/companies/${companyId}/obligations`));
}

/** Compliance pathways — one "how do I comply" record per enacted law. Scope by `state` (a US state
 *  profile) and/or `region` (US default, EU, or "all" for the self-serve checker across a region), or
 *  by `bill_ids` (CSV) for the per-bill "what you must do" block — that form bypasses the US default,
 *  so a foreign law's pathway resolves too. */
export async function fetchCompliancePathways(
  params: { state?: string; region?: string; regions?: string; bill_ids?: string },
): Promise<CompliancePathway[]> {
  return apiFetch<CompliancePathway[]>(buildUrl('/compliance/pathways', params));
}
