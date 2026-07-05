/**
 * Tiny typed client for the public SignalScout API.
 * Every method maps to one read endpoint documented at /docs (FastAPI OpenAPI).
 * No auth is required for the endpoints used here — they are the public/free tier.
 */

const DEFAULT_BASE = "https://signalscout-api-36712717703.us-central1.run.app";

export const API_BASE = process.env.SIGNALSCOUT_API_BASE_URL?.replace(/\/$/, "") || DEFAULT_BASE;

/** Optional Firebase bearer token — a Pro seat unlocks the full deadline calendar. */
const API_TOKEN = process.env.SIGNALSCOUT_API_TOKEN;

type Params = Record<string, string | number | boolean | undefined | null>;

function buildUrl(path: string, params?: Params): string {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function get<T>(path: string, params?: Params): Promise<T> {
  const res = await fetch(buildUrl(path, params), {
    headers: API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : undefined,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`SignalScout API ${res.status} on ${path}${body ? `: ${body.slice(0, 300)}` : ""}`);
  }
  return res.json() as Promise<T>;
}

// --- Response shapes (only the fields we surface; the API returns more) ---

export interface ComplianceEntity {
  slug: string;
  name: string;
  entity_type: string; // "pro" | "agency" | ...
  url?: string | null;
  registration_url?: string | null;
  jurisdiction_scope?: string | null;
}

export interface Pathway {
  bill_id: number;
  bill_number: string;
  bill_title: string;
  material_categories: string[] | null;
  management_model: string | null;
  action_type: string; // join_pro | file_individual_plan | register_with_state | monitor | ...
  action_summary: string;
  registration_url: string | null;
  next_deadline_date: string | null;
  has_fee: boolean;
  entity: ComplianceEntity | null;
}

export interface Bill {
  id: number;
  bill_number: string;
  title: string;
  state: string | null;
  region: string;
  status: string | null;
  instrument_type: string | null;
  material_categories: string[] | null;
  policy_stance: string | null;
  confidence_score: number | null;
  last_action_date: string | null;
  source_url: string | null;
  summary?: string | null;
}

export interface DeadlineSummary {
  deadline_date: string;
  bill_number?: string;
  bill_title?: string;
  label?: string;
  state?: string | null;
  region?: string | null;
}

export interface DeadlineStats {
  total_upcoming: number;
  within_30: number;
  within_90: number;
  next_date: string | null;
  states?: string[];
}

export interface MatrixCell {
  instrument_type: string;
  material_category: string;
  region?: string;
  count: number;
}

export interface SubscribePayload {
  email: string;
  organization?: string;
  region_scope?: Record<string, string[]>;
  instrument_types: string[];
  material_categories?: string[];
}

export const client = {
  pathways: (p: { state?: string; region?: string }) =>
    get<Pathway[]>("/compliance/pathways", p),

  bills: (p: {
    regions?: string;
    region?: string;
    state?: string;
    status?: string;
    material_category?: string;
    instrument_type?: string;
    ce_relevant?: boolean;
    min_confidence?: number;
    limit?: number;
  }) => get<Bill[]>("/bills", p),

  bill: (id: number) => get<Bill>(`/bills/${id}`),

  deadlinesUpcoming: (p: { days_ahead?: number; region?: string; materials?: string; states?: string }) =>
    get<DeadlineSummary[]>("/bills/deadlines/upcoming", p),

  deadlinesSummary: (p: { days_ahead?: number; region?: string; materials?: string; states?: string }) =>
    get<DeadlineStats>("/bills/deadlines/summary", p),

  matrix: (p: { regions?: string; min_confidence?: number }) =>
    get<MatrixCell[]>("/bills/instrument-material-matrix", p),

  async subscribe(payload: SubscribePayload): Promise<void> {
    const res = await fetch(buildUrl("/subscriptions"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`Subscribe failed (${res.status})${body ? `: ${body.slice(0, 300)}` : ""}`);
    }
  },
};
