// Personalized "scope" — the states + materials a reader told us matter to them, captured once and
// persisted in localStorage (we have no auth). Every front-door surface defaults to this scope so the
// firehose becomes "what's hitting me." Opt-out default to relevance: the scope is on once set; the
// full feed is the deliberate "Show everything" toggle, not the default.
//
// Match semantics mirror the backend digest's _matches_list (app/alerts/digest.py): an empty dimension
// means "match all", a populated dimension is an OR-match against the candidate.
import type { BillSummary, DeadlineSummary } from './types';

export interface Scope {
  /** Two-letter state codes the reader follows. Empty ⇒ all jurisdictions. */
  states: string[];
  /** material_category slugs (see MATERIAL_CATEGORIES in BillFilters). Empty ⇒ all materials. */
  materials: string[];
}

export const EMPTY_SCOPE: Scope = { states: [], materials: [] };

const KEY = 'scope:v1';

export function isEmptyScope(scope: Scope): boolean {
  return scope.states.length === 0 && scope.materials.length === 0;
}

/** Load the saved scope, or null if the reader has never been through onboarding. */
export function loadScope(): Scope | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Scope>;
    if (!parsed || !Array.isArray(parsed.states) || !Array.isArray(parsed.materials)) return null;
    return { states: parsed.states, materials: parsed.materials };
  } catch {
    return null;
  }
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

/** True when a bill falls inside the reader's scope. Empty dimensions match everything. */
export function inScope(bill: BillSummary, scope: Scope): boolean {
  if (scope.states.length && !scope.states.includes(bill.state)) return false;
  if (scope.materials.length) {
    const cats = bill.material_categories ?? [];
    if (!cats.some(c => scope.materials.includes(c))) return false;
  }
  return true;
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
  if (scope.states.length && !scope.states.includes(deadline.state)) return false;
  if (scope.materials.length) {
    const cats = resolveMaterials?.(deadline);
    if (cats && cats.length && !cats.some(c => scope.materials.includes(c))) return false;
  }
  return true;
}
