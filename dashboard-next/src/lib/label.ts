// "Regulation Facts" label builder — client-side port of the hackathon EPR-nutrition-label
// server (hackathon/epr-nutrition-label/server.js) plus the Cliff Score blend from
// hackathon/compliance-cliff. The dashboard is a static export, so all aggregation runs in the
// browser: one GET /compliance/pathways call per jurisdiction, fanned out with
// Promise.allSettled, then folded into a single shareable label.

import type {
  CompliancePathway,
  CompanySummary,
  CompanyObligation,
  CompanyObligationsResponse,
} from './types';

// Same API-base pattern as src/lib/api.ts (which is WIP and must not be modified).
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

function buildUrl(path: string, params?: Record<string, string | number | undefined>): string {
  const url = new URL(`${API}${path}`);
  if (params) {
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null && val !== '') url.searchParams.set(key, String(val));
    }
  }
  return url.toString();
}

async function apiFetch<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error ${res.status}: ${url}`);
  return res.json();
}

// ------------------------------------------------------------------ small utils

/** Days until an ISO date (UTC-anchored, ceil — matches the hackathon math). Negative = past. */
export function daysUntil(iso: string): number {
  const d = new Date(`${iso}T00:00:00Z`);
  return Math.ceil((d.getTime() - Date.now()) / 86400000);
}

export function formatLabelDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatMoney(n: number | null | undefined): string | null {
  if (n == null) return null;
  const a = Math.abs(n);
  if (a >= 1e9) return `$${(n / 1e9).toFixed(a >= 1e10 ? 0 : 1)}B`;
  if (a >= 1e6) return `$${(n / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`;
  if (a >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${Math.round(n)}`;
}

// --------------------------------------------------------------- region probe

/**
 * Prod (pre multi-region promotion) ignores the `region` query param and returns every pathway —
 * which would silently attribute US obligations to EU/FR/JP. Probe once per session: a
 * region-aware API returns [] for an impossible region; a legacy one returns everything.
 * Cached in module state so the probe fires at most once.
 */
let regionAwareProbe: Promise<boolean> | null = null;
export function apiIsRegionAware(): Promise<boolean> {
  regionAwareProbe ??= apiFetch<CompliancePathway[]>(
    buildUrl('/compliance/pathways', { region: 'ZZ' }),
  )
    .then(rows => rows.length === 0)
    .catch(() => false);
  return regionAwareProbe;
}

// -------------------------------------------------------------------- shapes

export interface LabelAction {
  actionType: string | null;
  summary: string | null;
  bill: string | null;
  entity: string | null;
  registrationUrl: string | null;
  deadline: string | null;
  hasFee: boolean;
}

export interface LabelJurisdiction {
  code: string;
  kind: 'state' | 'region';
  obligations: number;
  fees: number;
  /** Region requested but the API isn't region-aware yet — render "coverage pending†". */
  unsupported?: boolean;
  /** The per-jurisdiction fetch failed. */
  error?: boolean;
  nextDeadline: string | null;
  actions: LabelAction[];
}

export interface LabelTotals {
  obligations: number;
  jurisdictions: number;
  jurisdictionsWithObligations: number;
  fees: number;
  deadlinesWithin30: number;
  deadlinesWithin90: number;
  soonestDeadline: { date: string; code: string; bill: string | null; daysAway: number } | null;
}

/** Dollar figures only company mode carries (from /companies/{id}/obligations stakes). */
export interface LabelFinance {
  maxPenaltyPerDayUsd: number | null;
  feeLowUsd: number | null;
  feeHighUsd: number | null;
  ecoModulationSwingUsd: number | null;
  anyFeeGrounded: boolean;
}

export interface CliffVerdict {
  key: 'sheer' | 'steep' | 'exposed' | 'foothills' | 'solid';
  title: string;
  color: string;
  description: string;
}

export interface RegulationLabel {
  mode: 'product' | 'company';
  /** Product name or company name — the "serving" line. */
  subjectName: string;
  generatedAt: string;
  materials: string[];
  totals: LabelTotals;
  /** The "CONTAINS:" allergen line — derived from action_type + has_fee (and stakes in company mode). */
  contains: string[];
  /** Administering PROs / agencies. */
  entities: string[];
  jurisdictions: LabelJurisdiction[];
  cliff: { score: number; verdict: CliffVerdict } | null;
  finance: LabelFinance | null;
}

export interface ProductSelection {
  productName: string;
  materials: string[];
  states: string[];
  regions: string[];
}

// ---------------------------------------------------------------- cliff score

/** Verdict tiers ported from compliance-cliff (public/index.html verdict()). */
export function cliffVerdict(s: number): CliffVerdict {
  if (s >= 80)
    return { key: 'sheer', title: 'Sheer drop', color: '#ff5a5f', description: 'Broad, imminent, and expensive exposure. This is a board-level risk.' };
  if (s >= 62)
    return { key: 'steep', title: 'Steep face', color: '#ff884d', description: 'Multiple active obligations with real money and near-term deadlines.' };
  if (s >= 42)
    return { key: 'exposed', title: 'Exposed edge', color: '#e8a010', description: 'On the map in several markets — deadlines are coming into view.' };
  if (s >= 22)
    return { key: 'foothills', title: 'Foothills', color: '#a3ad2f', description: 'Early exposure. A good time to get ahead of it.' };
  return { key: 'solid', title: 'Solid ground', color: '#1a7f5a', description: 'No enacted obligations matched yet — worth monitoring.' };
}

function urgencyTerm(nextDeadlineDate: string | null): number {
  if (!nextDeadlineDate) return 0;
  const dd = daysUntil(nextDeadlineDate);
  return dd <= 90 ? 1 : dd <= 365 ? 0.7 : dd <= 730 ? 0.45 : 0.25;
}

/**
 * Company-mode Cliff Score — the exact 0-100 blend from compliance-cliff: breadth (laws x states),
 * deadline urgency, statutory penalty size, and annual-fee magnitude.
 */
export function cliffScoreFromObligations(o: CompanyObligationsResponse): number {
  const laws = Math.min(1, (o.affected_bill_count || 0) / 12);
  const states = Math.min(1, (o.affected_states?.length || 0) / 6);
  const urgency = o.next_deadline_date ? urgencyTerm(o.next_deadline_date) : 0;
  const pen = Math.min(1, (o.max_penalty_per_day_usd || 0) / 50000);
  const fee = Math.min(1, (o.portfolio_annual_fee_high_usd || 0) / 1e8);
  const score = 100 * (0.26 * laws + 0.16 * states + 0.24 * urgency + 0.18 * pen + 0.16 * fee);
  return Math.max(o.affected_bill_count > 0 ? 18 : 0, Math.round(score));
}

/**
 * Product-mode Cliff Score. Pathways data has no penalty and no fee dollar amounts, so those blend
 * terms are honestly unavailable: the penalty term is dropped entirely (weights renormalized, not
 * faked as zero exposure) and the fee-magnitude term becomes fee *presence* — the share of matched
 * laws that carry a producer fee. Breadth + urgency map 1:1 from the original blend.
 */
export function cliffScoreFromLabel(t: LabelTotals): number {
  const laws = Math.min(1, t.obligations / 12);
  const markets = Math.min(1, t.jurisdictionsWithObligations / 6);
  const urgency = t.soonestDeadline ? urgencyTerm(t.soonestDeadline.date) : 0;
  const feePresence = t.obligations > 0 ? Math.min(1, t.fees / t.obligations) : 0;
  // Original weights minus the omitted penalty term (0.18), renormalized to sum to 1.
  const w = 0.26 + 0.16 + 0.24 + 0.16; // 0.82
  const score = (100 / w) * (0.26 * laws + 0.16 * markets + 0.24 * urgency + 0.16 * feePresence);
  return Math.max(t.obligations > 0 ? 18 : 0, Math.min(100, Math.round(score)));
}

// ------------------------------------------------------------- product mode

/** Same material-overlap rule as the compliance-copilot MCP, plus the "ALL" wildcard. */
function overlaps(billMats: string[] | null | undefined, wanted: string[]): boolean {
  if (!wanted.length) return true;
  if (!billMats || !billMats.length) return false;
  const set = new Set(billMats.map(s => s.toLowerCase()));
  if (set.has('all')) return true;
  return wanted.some(m => set.has(m.toLowerCase()));
}

const ACTION_PHRASES: Record<string, string> = {
  join_pro: 'PRO registration',
  file_individual_plan: 'individual compliance plan',
  register_with_state: 'state registration',
  monitor: 'regulatory monitoring',
};

export const MAX_MARKETS = 30;

/** Build the label for a material/market selection: one pathways call per jurisdiction. */
export async function buildProductLabel(sel: ProductSelection): Promise<RegulationLabel> {
  const materials = sel.materials.map(m => m.toLowerCase());
  const states = sel.states.map(s => s.toUpperCase());
  const regions = sel.regions.map(r => r.toUpperCase());

  const jurisdictions: { code: string; kind: 'state' | 'region'; params: { state?: string; region?: string } }[] = [
    ...states.map(s => ({ code: s, kind: 'state' as const, params: { state: s } })),
    ...regions.map(r => ({ code: r, kind: 'region' as const, params: { region: r } })),
  ];
  if (!jurisdictions.length) throw new Error('Pick at least one market.');
  if (jurisdictions.length > MAX_MARKETS) throw new Error(`${MAX_MARKETS} markets max.`);

  const regionAware = regions.length ? await apiIsRegionAware() : true;

  const settled = await Promise.allSettled(
    jurisdictions.map(j =>
      j.kind === 'region' && !regionAware
        ? Promise.resolve(null) // legacy API: don't attribute the unfiltered firehose to this region
        : apiFetch<CompliancePathway[]>(buildUrl('/compliance/pathways', j.params)),
    ),
  );

  const perJurisdiction: LabelJurisdiction[] = [];
  const allDeadlines: { date: string; code: string; bill: string | null }[] = [];
  const contains = new Set<string>();
  const entities = new Set<string>();
  let totalObligations = 0;
  let feeCount = 0;

  jurisdictions.forEach((j, i) => {
    const s = settled[i];
    if (s.status === 'fulfilled' && s.value === null) {
      perJurisdiction.push({ code: j.code, kind: j.kind, unsupported: true, obligations: 0, fees: 0, nextDeadline: null, actions: [] });
      return;
    }
    if (s.status !== 'fulfilled') {
      perJurisdiction.push({ code: j.code, kind: j.kind, error: true, obligations: 0, fees: 0, nextDeadline: null, actions: [] });
      return;
    }
    const pathways = (s.value as CompliancePathway[])
      .filter(p => overlaps(p.material_categories, materials))
      .sort((a, b) => {
        if (a.next_deadline_date === b.next_deadline_date) return 0;
        if (!a.next_deadline_date) return 1;
        if (!b.next_deadline_date) return -1;
        return a.next_deadline_date < b.next_deadline_date ? -1 : 1;
      });

    let jFees = 0;
    for (const p of pathways) {
      totalObligations += 1;
      if (p.has_fee) {
        jFees += 1;
        feeCount += 1;
        contains.add('producer fees');
      }
      if (p.action_type && ACTION_PHRASES[p.action_type]) contains.add(ACTION_PHRASES[p.action_type]);
      if (p.entity?.name) entities.add(p.entity.name);
      if (p.next_deadline_date && daysUntil(p.next_deadline_date) >= 0) {
        allDeadlines.push({ date: p.next_deadline_date, code: j.code, bill: p.bill_number });
      }
    }

    perJurisdiction.push({
      code: j.code,
      kind: j.kind,
      obligations: pathways.length,
      fees: jFees,
      nextDeadline: pathways.find(p => p.next_deadline_date)?.next_deadline_date ?? null,
      actions: pathways.slice(0, 3).map(p => ({
        actionType: p.action_type,
        summary: p.action_summary,
        bill: p.bill_number,
        entity: p.entity?.name ?? null,
        registrationUrl: p.registration_url ?? p.entity?.registration_url ?? null,
        deadline: p.next_deadline_date,
        hasFee: p.has_fee,
      })),
    });
  });

  allDeadlines.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const soonest = allDeadlines[0] ?? null;

  const totals: LabelTotals = {
    obligations: totalObligations,
    jurisdictions: jurisdictions.length,
    jurisdictionsWithObligations: perJurisdiction.filter(j => j.obligations > 0).length,
    fees: feeCount,
    deadlinesWithin30: allDeadlines.filter(d => daysUntil(d.date) <= 30).length,
    deadlinesWithin90: allDeadlines.filter(d => daysUntil(d.date) <= 90).length,
    soonestDeadline: soonest ? { ...soonest, daysAway: daysUntil(soonest.date) } : null,
  };

  const score = cliffScoreFromLabel(totals);

  return {
    mode: 'product',
    subjectName: sel.productName.trim() || 'Unnamed product',
    generatedAt: new Date().toISOString(),
    materials,
    totals,
    contains: [...contains].sort(),
    entities: [...entities].sort(),
    jurisdictions: perJurisdiction,
    cliff: { score, verdict: cliffVerdict(score) },
    finance: null,
  };
}

// ------------------------------------------------------------- company mode

export async function searchCompanies(term: string, limit = 8): Promise<CompanySummary[]> {
  return apiFetch<CompanySummary[]>(buildUrl('/companies', { search: term, limit }));
}

export async function fetchObligations(companyId: string): Promise<CompanyObligationsResponse> {
  return apiFetch<CompanyObligationsResponse>(buildUrl(`/companies/${companyId}/obligations`));
}

/** Fold a company's obligations response into the same Regulation Facts shape (rows per state). */
export function buildCompanyLabel(o: CompanyObligationsResponse): RegulationLabel {
  const byState = new Map<string, CompanyObligation[]>();
  for (const ob of o.obligations ?? []) {
    const key = (ob.state || '??').toUpperCase();
    const list = byState.get(key) ?? [];
    list.push(ob);
    byState.set(key, list);
  }

  const contains = new Set<string>();
  const materials = new Set<string>();
  const allDeadlines: { date: string; code: string; bill: string | null }[] = [];
  let feeCount = 0;

  const perJurisdiction: LabelJurisdiction[] = [...byState.entries()]
    .map(([code, obs]) => {
      const sorted = [...obs].sort((a, b) => {
        const ad = a.next_deadline?.deadline_date ?? null;
        const bd = b.next_deadline?.deadline_date ?? null;
        if (ad === bd) return 0;
        if (!ad) return 1;
        if (!bd) return -1;
        return ad < bd ? -1 : 1;
      });
      let jFees = 0;
      for (const ob of sorted) {
        for (const m of ob.matched_materials ?? []) materials.add(m.toLowerCase());
        if (ob.stakes?.fee) {
          jFees += 1;
          feeCount += 1;
          contains.add('producer fees');
        }
        if (ob.stakes?.penalty) contains.add('statutory penalties');
        if (ob.stakes?.pro_membership_usd) contains.add('PRO membership dues');
        const nd = ob.next_deadline?.deadline_date;
        if (nd && daysUntil(nd) >= 0) allDeadlines.push({ date: nd, code, bill: ob.bill_number });
      }
      return {
        code,
        kind: 'state' as const,
        obligations: obs.length,
        fees: jFees,
        nextDeadline: sorted.find(x => x.next_deadline)?.next_deadline?.deadline_date ?? null,
        actions: sorted.slice(0, 3).map(ob => ({
          actionType: null,
          summary: ob.bill_title ?? (ob.next_deadline?.description || null),
          bill: ob.bill_number,
          entity: null,
          registrationUrl: null,
          deadline: ob.next_deadline?.deadline_date ?? null,
          hasFee: Boolean(ob.stakes?.fee),
        })),
      };
    })
    .sort((a, b) => b.obligations - a.obligations || a.code.localeCompare(b.code));

  allDeadlines.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const soonest = allDeadlines[0] ?? null;

  const totals: LabelTotals = {
    obligations: o.affected_bill_count ?? 0,
    jurisdictions: perJurisdiction.length,
    jurisdictionsWithObligations: perJurisdiction.filter(j => j.obligations > 0).length,
    fees: feeCount,
    deadlinesWithin30: allDeadlines.filter(d => daysUntil(d.date) <= 30).length,
    deadlinesWithin90: allDeadlines.filter(d => daysUntil(d.date) <= 90).length,
    soonestDeadline: soonest ? { ...soonest, daysAway: daysUntil(soonest.date) } : null,
  };

  const score = cliffScoreFromObligations(o);

  return {
    mode: 'company',
    subjectName: o.company_name,
    generatedAt: new Date().toISOString(),
    materials: [...materials].sort(),
    totals,
    contains: [...contains].sort(),
    entities: [],
    jurisdictions: perJurisdiction,
    cliff: { score, verdict: cliffVerdict(score) },
    finance: {
      maxPenaltyPerDayUsd: o.max_penalty_per_day_usd,
      feeLowUsd: o.portfolio_annual_fee_low_usd,
      feeHighUsd: o.portfolio_annual_fee_high_usd,
      ecoModulationSwingUsd: o.portfolio_eco_modulation_swing_usd,
      anyFeeGrounded: o.any_fee_grounded,
    },
  };
}
