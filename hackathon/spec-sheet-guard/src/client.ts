/**
 * Tiny client for the one SignalScout endpoint this guard needs: /compliance/pathways.
 * Public/free tier — no auth required. Set SIGNALSCOUT_API_TOKEN (a Pro Firebase token)
 * only if you point at a gated deployment.
 */

const DEFAULT_BASE = "https://signalscout-api-36712717703.us-central1.run.app";

export const API_BASE =
  process.env.SIGNALSCOUT_API_BASE_URL?.replace(/\/$/, "") || DEFAULT_BASE;

const API_TOKEN = process.env.SIGNALSCOUT_API_TOKEN;

/** One compliance obligation attached to an enacted law in a jurisdiction. */
export interface Pathway {
  bill_id: number;
  bill_number: string;
  bill_title: string;
  material_categories: string[] | null;
  management_model: string | null;
  /** join_pro | file_individual_plan | register_with_state | monitor | none | ... */
  action_type: string;
  action_summary: string;
  registration_url: string | null;
  next_deadline_date: string | null; // ISO date
  has_fee: boolean;
  entity: {
    slug: string;
    name: string;
    entity_type: string; // "pro" | "agency" | ...
    url?: string | null;
    registration_url?: string | null;
    jurisdiction_scope?: string | null;
  } | null;
}

/** Non-US jurisdiction families are queried via `region`; US states via `state`. */
const REGION_FAMILIES = new Set(["EU", "FR", "JP"]);

function buildUrl(market: string): string {
  const url = new URL(`${API_BASE}/compliance/pathways`);
  const code = market.trim().toUpperCase();
  if (REGION_FAMILIES.has(code)) {
    url.searchParams.set("region", code);
  } else {
    url.searchParams.set("state", code); // region defaults to US server-side
  }
  return url.toString();
}

export async function fetchPathways(market: string): Promise<Pathway[]> {
  const res = await fetch(buildUrl(market), {
    headers: API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : undefined,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(
      `SignalScout API ${res.status} for market "${market}"${body ? `: ${body.slice(0, 200)}` : ""}`
    );
  }
  return (await res.json()) as Pathway[];
}
