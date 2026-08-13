// Personalized "scope" — the states + materials a reader told us matter to them, captured once and
// persisted in localStorage (we have no auth). Every front-door surface defaults to this scope so the
// firehose becomes "what's hitting me." Opt-out default to relevance: the scope is on once set; the
// full feed is the deliberate "Show everything" toggle, not the default.
//
// Match semantics mirror the backend digest's _matches_list (app/alerts/digest.py): an empty dimension
// means "match all", a populated dimension is an OR-match against the candidate.
import type { BillSummary, DeadlineSummary } from './types';

export interface Scope {
  /**
   * Region codes the reader follows — 'US', 'EU', or a country ('JP', 'BR'). Empty ⇒ every region.
   * Matched against `bill.region`, NOT `bill.state`, and that separation is the point: state codes
   * and country codes share a namespace, so "DE" is Delaware in `state` and Germany in `region`.
   * Filtering both from one list would silently hand a reader watching Delaware every German law.
   */
  regions: string[];
  /** Two-letter US state codes. A sub-filter WITHIN the US — see inScope. Empty ⇒ all US states. */
  states: string[];
  /** material_category slugs (see MATERIAL_CATEGORIES in BillFilters). Empty ⇒ all materials. */
  materials: string[];
}

export const EMPTY_SCOPE: Scope = { regions: [], states: [], materials: [] };

const KEY = 'scope:v1';

export function isEmptyScope(scope: Scope): boolean {
  return scope.regions.length === 0 && scope.states.length === 0 && scope.materials.length === 0;
}

/** Load the saved scope, or null if the reader has never been through onboarding. */
export function loadScope(): Scope | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Scope>;
    if (!parsed || !Array.isArray(parsed.states) || !Array.isArray(parsed.materials)) return null;
    // `regions` post-dates the key, so a scope saved before it is read as region-less rather than
    // rejected — the storage key stays v1 precisely so those readers keep their states + materials
    // instead of being silently reset to "everything". normalizeScope supplies the US implication.
    return normalizeScope({
      regions: Array.isArray(parsed.regions) ? parsed.regions : [],
      states: parsed.states,
      materials: parsed.materials,
    });
  } catch {
    return null;
  }
}

/**
 * Fill in what a partial scope implies. Exactly one rule: **US states selected with no region chosen
 * means the US.**
 *
 * Without it, every scope saved before regions existed would silently widen the moment this shipped —
 * a reader following California would start getting Japanese and EU law, because an empty region list
 * means "every region" and their state list only ever narrowed within the US. Applied on load and on
 * save, so the stored value and the live one agree.
 */
export function normalizeScope(scope: Scope): Scope {
  if (scope.states.length && !scope.regions.length) return { ...scope, regions: ['US'] };
  return scope;
}

export function saveScope(scope: Scope): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(scope));
  } catch {
    /* private mode / quota — personalization is best-effort */
  }
}

export function clearScope(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

/**
 * True when a bill falls inside the reader's scope. Empty dimensions match everything.
 *
 * States narrow WITHIN the US rather than across the whole corpus: a reader who follows California
 * and Japan wants both, and a US-state list has nothing to say about a Japanese law. So the state
 * check only applies to US bills, and everything outside the US is admitted or excluded by `regions`
 * alone. (normalizeScope is what stops that from widening a states-only scope: it reads as US-only.)
 */
export function inScope(bill: BillSummary, scope: Scope): boolean {
  if (scope.regions.length && !scope.regions.includes(bill.region ?? '')) return false;
  if (scope.states.length && bill.region === 'US' && !scope.states.includes(bill.state)) return false;
  if (scope.materials.length) {
    const cats = bill.material_categories ?? [];
    if (!cats.some(c => scope.materials.includes(c))) return false;
  }
  return true;
}

/**
 * Every jurisdiction code a scope admits, as one flat list — regions and US states together.
 *
 * Deadlines carry a single `state` column and no `region`, so unlike a bill they can't be filtered on
 * the two dimensions separately. That column holds a US state code for a US row and a region/country
 * code for everything else (the same ambiguity `jurisdiction()` resolves for display), so the union is
 * the honest match: a reader scoped to Japan + California is watching exactly {JP, US, CA} worth of
 * codes. 'US' rides along so federal deadlines survive a US-state scope. Empty ⇒ no filtering.
 */
export function scopeJurisdictionCodes(scope: Scope): string[] {
  return Array.from(new Set([...scope.regions, ...scope.states]));
}

/**
 * True when a deadline falls inside the reader's scope. Deadlines carry `state` + `bill_id` but not
 * materials, so the caller supplies `resolveMaterials` (typically a lookup into the loaded bills) to
 * get the linked bill's categories. When materials can't be resolved (e.g. a federal deadline, or the
 * bill isn't loaded), we don't exclude on materials — better to surface than to silently hide.
 */
export function deadlineInScope(
  deadline: DeadlineSummary,
  scope: Scope,
  resolveMaterials?: (d: DeadlineSummary) => string[] | null | undefined,
): boolean {
  const codes = scopeJurisdictionCodes(scope);
  if (codes.length && !codes.includes(deadline.state)) return false;
  if (scope.materials.length) {
    const cats = resolveMaterials?.(deadline);
    if (cats && cats.length && !cats.some(c => scope.materials.includes(c))) return false;
  }
  return true;
}
