/**
 * Pure evaluation core for the Packaging Studio's Guard — a browser port of
 * spec-sheet-guard/src/guard.ts (the hackathon CI tool).
 *
 * Given a packaging spec and the compliance pathways for each market it sells into,
 * decide which obligations apply, which are already acknowledged, and what should
 * block a build. No I/O here, so the rules match the CLI's unit-tested behavior
 * exactly — the studio previews the very verdict `npx spec-sheet-guard` will
 * produce on the exported packaging.yaml.
 */

/** One compliance obligation attached to an enacted law in a jurisdiction, as
 *  returned by GET /compliance/pathways. Fields are nullable to match the live API. */
export interface GuardPathway {
  bill_id: number;
  bill_number: string | null;
  bill_title: string | null;
  material_categories: string[] | null;
  management_model?: string | null;
  /** join_pro | file_individual_plan | register_with_state | monitor | none | ... */
  action_type: string | null;
  action_summary: string | null;
  registration_url: string | null;
  next_deadline_date: string | null; // ISO date
  has_fee: boolean;
  entity: {
    slug?: string | null;
    name?: string | null;
    entity_type?: string | null;
    url?: string | null;
    registration_url?: string | null;
    jurisdiction_scope?: string | null;
  } | null;
}

export interface PackagingSpec {
  product?: string;
  /** Jurisdiction codes the product is sold into: US state codes, or EU / FR / JP. */
  markets: string[];
  /** SignalScout material categories the product uses (e.g. plastic_packaging, metals). */
  materials: string[];
  /**
   * Obligations already handled. Each entry matches a finding by (case-insensitive):
   * an entity slug/name, a bill number, or a market-scoped bill number "CA:SB-54".
   */
  acknowledged?: string[];
}

export type Severity = 'error' | 'warning' | 'note';

export interface Finding {
  market: string;
  severity: Severity;
  acknowledged: boolean;
  /** Numeric bill id from the pathways feed — for bill-detail links + the watchlist star. */
  billId: number;
  billNumber: string;
  billTitle: string;
  actionType: string;
  actionSummary: string;
  matchedMaterials: string[];
  entityName: string | null;
  registrationUrl: string | null;
  hasFee: boolean;
  deadline: string | null;
  /** Whole days from `today` to the deadline; negative = overdue; null = no date. */
  daysToDeadline: number | null;
}

export interface GuardReport {
  spec: PackagingSpec;
  findings: Finding[];
  counts: { error: number; warning: number; note: number; acknowledged: number };
  /** True when nothing blocks the build. */
  ok: boolean;
}

/** Action types that impose a real producer obligation (vs. "just watch this"). */
const NON_ACTIONABLE = new Set(['monitor', 'none', '', 'no_action']);

function isActionable(actionType: string): boolean {
  return !NON_ACTIONABLE.has((actionType || '').toLowerCase());
}

/**
 * Loose material match: exact, or either side contains the other as a token.
 * Lets a spec say "packaging" and match "plastic_packaging"/"paper_packaging",
 * or say "plastic" and match "plastic_packaging" — without missing an obligation.
 */
function materialsMatch(specMaterials: string[], pathwayMaterials: string[] | null): string[] {
  if (!pathwayMaterials || pathwayMaterials.length === 0) return [];
  const spec = specMaterials.map((m) => m.trim().toLowerCase()).filter(Boolean);
  const matched: string[] = [];
  for (const pm of pathwayMaterials) {
    const p = pm.toLowerCase();
    if (spec.some((s) => s === p || p.includes(s) || s.includes(p))) matched.push(pm);
  }
  return matched;
}

function daysBetween(fromISO: string, toISO: string): number {
  const MS = 24 * 60 * 60 * 1000;
  const from = Date.parse(fromISO);
  const to = Date.parse(toISO);
  return Math.round((to - from) / MS);
}

function isAcknowledged(spec: PackagingSpec, market: string, p: GuardPathway): boolean {
  const acks = (spec.acknowledged ?? []).map((a) => a.trim().toLowerCase()).filter(Boolean);
  if (acks.length === 0) return false;
  const candidates = [
    p.bill_number ?? '',
    `${market}:${p.bill_number ?? ''}`,
    p.entity?.slug ?? '',
    p.entity?.name ?? '',
  ]
    .map((c) => c.toLowerCase())
    .filter(Boolean);
  return acks.some((a) => candidates.includes(a));
}

export interface EvaluateOptions {
  /** ISO date treated as "now" (defaults to real today). */
  today?: string;
  /**
   * Unacknowledged obligations with a deadline within this many days are errors;
   * those further out (or dateless) are warnings. Set to Infinity to fail on ALL
   * unmet obligations regardless of deadline. Default: Infinity (any unmet = error).
   */
  failWindowDays?: number;
}

export function evaluate(
  spec: PackagingSpec,
  pathwaysByMarket: Record<string, GuardPathway[]>,
  opts: EvaluateOptions = {},
): GuardReport {
  const today = opts.today ?? new Date().toISOString().slice(0, 10);
  const failWindow = opts.failWindowDays ?? Infinity;
  const findings: Finding[] = [];

  for (const market of spec.markets) {
    const pathways = pathwaysByMarket[market] ?? [];
    for (const p of pathways) {
      const matched = materialsMatch(spec.materials, p.material_categories);
      const materialUnknown = !p.material_categories || p.material_categories.length === 0;
      // Skip laws that clearly don't touch our materials.
      if (matched.length === 0 && !materialUnknown) continue;

      const daysToDeadline = p.next_deadline_date ? daysBetween(today, p.next_deadline_date) : null;
      const acknowledged = isAcknowledged(spec, market, p);
      const actionable = isActionable(p.action_type ?? '');

      let severity: Severity;
      if (acknowledged || !actionable) {
        severity = 'note';
      } else if (materialUnknown) {
        // Applies to this market but SignalScout hasn't pinned the materials yet — review.
        severity = 'warning';
      } else if (daysToDeadline === null || daysToDeadline <= failWindow) {
        severity = 'error';
      } else {
        severity = 'warning';
      }

      findings.push({
        market,
        severity,
        acknowledged,
        billId: p.bill_id,
        billNumber: p.bill_number ?? '',
        billTitle: p.bill_title ?? '',
        actionType: p.action_type ?? '',
        actionSummary: p.action_summary ?? '',
        matchedMaterials: matched,
        entityName: p.entity?.name ?? null,
        registrationUrl: p.registration_url ?? p.entity?.registration_url ?? null,
        hasFee: p.has_fee,
        deadline: p.next_deadline_date,
        daysToDeadline,
      });
    }
  }

  // Sort: errors first, then by soonest deadline (dateless last), then market.
  const sevRank: Record<Severity, number> = { error: 0, warning: 1, note: 2 };
  findings.sort((a, b) => {
    if (sevRank[a.severity] !== sevRank[b.severity]) return sevRank[a.severity] - sevRank[b.severity];
    const ad = a.daysToDeadline ?? Number.POSITIVE_INFINITY;
    const bd = b.daysToDeadline ?? Number.POSITIVE_INFINITY;
    if (ad !== bd) return ad - bd;
    return a.market.localeCompare(b.market);
  });

  const counts = {
    error: findings.filter((f) => f.severity === 'error').length,
    warning: findings.filter((f) => f.severity === 'warning').length,
    note: findings.filter((f) => f.severity === 'note').length,
    acknowledged: findings.filter((f) => f.acknowledged).length,
  };

  return { spec, findings, counts, ok: counts.error === 0 };
}
