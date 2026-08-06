/**
 * "What you must do" — the step derivation behind the deadline modal and the bill page.
 *
 * Two inputs, both already in the corpus, no new extraction:
 *   1. the law's CompliancePathway (action_type + administering PRO/agency + registration URL),
 *      built by scripts/build_compliance_pathways.py — the LAW-level action;
 *   2. the deadline's own `deadline_type` (registration | reporting | fee_payment | compliance |
 *      effective | other) plus the bill's extracted `producer_obligations` — what THIS DATE requires.
 *
 * The deadline type wins where it's specific (a registration date means "register", whatever the
 * law-level action says); the pathway fills in the concrete counterparty and link. Pure and
 * dependency-free so the statically-exported bill page and the client modal share it.
 */
import type { ComplianceDetails, CompliancePathway, DeadlineSummary } from '@/lib/types';

/** Imperative phrasing per deadline type. `null` = the type says nothing specific about the act
 *  (a bare "compliance"/"effective"/"other" date), so the law-level pathway action leads instead. */
const STEP_BY_DEADLINE_TYPE: Record<string, { bare: string; withEntity: (e: string) => string } | null> = {
  registration: {
    bare: 'Register as a covered producer',
    withEntity: e => `Register as a covered producer with ${e}`,
  },
  reporting: {
    bare: 'File your producer report',
    withEntity: e => `File your producer report with ${e}`,
  },
  fee_payment: {
    bare: 'Pay the producer fee due on this date',
    withEntity: e => `Pay the producer fee due to ${e}`,
  },
  compliance: null,
  effective: null,
  other: null,
};

/** Imperative phrasing per law-level pathway action. `monitor`/`none` are the generic template rows
 *  (~80% of the corpus) — phrased honestly rather than dressed up as a concrete task. */
const STEP_BY_ACTION: Record<string, { bare: string; withEntity: (e: string) => string }> = {
  join_pro: {
    bare: 'Join the producer responsibility organisation for this program',
    withEntity: e => `Join ${e}`,
  },
  file_individual_plan: {
    bare: 'File an individual stewardship plan',
    withEntity: e => `File an individual stewardship plan with ${e}`,
  },
  register_with_state: {
    bare: 'Register with the program regulator',
    withEntity: e => `Register with ${e}`,
  },
  pay_into_program: {
    bare: 'Pay into the stewardship program',
    withEntity: e => `Pay into the program run by ${e}`,
  },
  arrange_collection: {
    bare: 'Arrange take-back / collection for your products',
    withEntity: e => `Arrange take-back / collection through ${e}`,
  },
  report_to_program: {
    bare: 'Report your placed-on-market volumes to the program',
    withEntity: e => `Report your placed-on-market volumes to ${e}`,
  },
  monitor: {
    bare: 'Confirm your obligations under this measure and track its implementing rules',
    withEntity: e => `Confirm your obligations with ${e} and track its implementing rules`,
  },
  none: {
    bare: 'No producer action is triggered yet — track this measure',
    withEntity: e => `No producer action is triggered yet — track this measure via ${e}`,
  },
};

/** Where a bare date is all we have. */
const FALLBACK_BY_DEADLINE_TYPE: Record<string, string> = {
  effective: 'The measure takes effect on this date — obligations begin',
  compliance: 'Be in compliance with the measure by this date',
};
const FALLBACK = 'Review this measure’s obligations and confirm whether they reach your products';

/** Which extracted producer_obligations speak to a given deadline type. `null` = no narrowing. */
const OBLIGATION_PATTERNS: Record<string, RegExp | null> = {
  registration: /\bregist(er|ers|ered|ration|ering)\b|\benrol/i,
  reporting: /\breport(s|ing|ed)?\b|\bsubmit\b|\bdisclos|\bdata\b|\brecordkeep|\bcertif/i,
  fee_payment: /\bfee(s)?\b|\bpay(s|ment|ments)?\b|\bremit\b|\bassessment\b|\bcharge(s)?\b|\bfund\b/i,
  compliance: null,
  effective: null,
  other: null,
};

/** How many obligation lines a step shows before it stops being a next step and starts being a wall. */
const MAX_OBLIGATIONS = 3;
const MAX_WHO_CHARS = 220;
const MAX_REQUIREMENT_CHARS = 400;

/** Descriptions the deadline MERGE synthesizes when a bill has no extracted per-date text (see
 *  _merge_deadlines in app/api/bills.py: "HB22-1355 takes effect" / "… compliance date"). They restate
 *  the date rather than say what's due, so they must not be presented as this date's requirement. */
const SYNTHESIZED_DESCRIPTION = /^\S+\s+(takes effect|compliance date)$/i;

export interface NextStep {
  /** The imperative headline — the sentence the page subtitle promises. */
  action: string;
  /** What THIS date specifically calls for, from the deadline's own extracted description. The only
   *  field that separates a law's several dates from one another, so it leads the block when present.
   *  Null for a law-level step, or when the description was synthesized from the date itself. */
  requirement: string | null;
  /** Who the obligation lands on, when the corpus says. */
  who: string | null;
  /** Where to do it (PRO/agency registration page). */
  link: { label: string; url: string } | null;
  /** Obligation lines from the extraction, narrowed to this date's type where possible. */
  obligations: string[];
  /** True when `obligations` were matched to this deadline type; false when they're the law's
   *  general obligations, shown for want of anything date-specific (the UI labels them differently). */
  obligationsMatched: boolean;
  /** True when the step rests on the generic monitor/none pathway template rather than a concrete
   *  action. Surfaced as a caveat so we never imply a precision the corpus doesn't have. */
  generic: boolean;
  /** Set when the law charges a producer fee. */
  feeNote: string | null;
}

function clip(s: string, max: number): string {
  const t = s.replace(/\s+/g, ' ').trim();
  if (t.length <= max) return t;
  return t.slice(0, t.lastIndexOf(' ', max - 1)).trimEnd() + '…';
}

/** Obligation lines relevant to this deadline. Falls back to the law's first few obligations (flagged
 *  via `matched: false`) so a bare "compliance" date still shows what the law actually requires. */
export function pickObligations(
  deadlineType: string | null | undefined,
  obligations: string[] | null | undefined,
): { items: string[]; matched: boolean } {
  const all = (obligations ?? []).map(o => o.trim()).filter(Boolean);
  if (all.length === 0) return { items: [], matched: false };
  const pattern = deadlineType ? OBLIGATION_PATTERNS[deadlineType] : null;
  if (pattern) {
    const hits = all.filter(o => pattern.test(o));
    if (hits.length > 0) return { items: hits.slice(0, MAX_OBLIGATIONS), matched: true };
  }
  return { items: all.slice(0, MAX_OBLIGATIONS), matched: false };
}

/**
 * Build the step for a deadline (pass `deadline`) or for a law as a whole (omit it).
 *
 * Returns null only when there is genuinely nothing to say — no pathway and no extracted
 * obligations — so a caller can hide the block rather than render an empty promise.
 */
export function buildNextStep({
  pathway,
  deadline,
  details,
}: {
  pathway?: CompliancePathway | null;
  deadline?: Pick<DeadlineSummary, 'deadline_type' | 'who_affected' | 'description'> | null;
  details?: ComplianceDetails | null;
}): NextStep | null {
  const entity = pathway?.entity?.name ? clip(pathway.entity.name, 90) : null;
  const actionType = pathway?.action_type ?? null;
  const deadlineType = deadline?.deadline_type ?? null;
  const generic = !actionType || actionType === 'monitor' || actionType === 'none';

  // The date's own type leads where it's specific; otherwise the law-level action does.
  const byDate = deadlineType ? STEP_BY_DEADLINE_TYPE[deadlineType] : null;
  const byAction = actionType ? STEP_BY_ACTION[actionType] : null;
  const spec = byDate ?? byAction ?? null;
  const action = spec
    ? (entity ? spec.withEntity(entity) : spec.bare)
    : (deadlineType && FALLBACK_BY_DEADLINE_TYPE[deadlineType]) || FALLBACK;

  const { items, matched } = pickObligations(deadlineType, details?.producer_obligations);

  const rawRequirement = deadline?.description?.trim() || '';
  const requirement =
    rawRequirement && !SYNTHESIZED_DESCRIPTION.test(rawRequirement)
      ? clip(rawRequirement, MAX_REQUIREMENT_CHARS)
      : null;

  const whoRaw = deadline?.who_affected || details?.producer_definition || null;
  const who = whoRaw ? clip(whoRaw, MAX_WHO_CHARS) : null;

  const url = pathway?.registration_url ?? pathway?.entity?.registration_url ?? pathway?.entity?.url ?? null;
  const link = url ? { label: entity ?? 'Program page', url } : null;

  // Nothing sourced at all — no pathway, no obligations, no date-specific text. Better to render
  // nothing than a platitude.
  if (!pathway && items.length === 0 && !requirement) return null;

  return {
    action,
    requirement,
    who,
    link,
    obligations: items,
    obligationsMatched: matched,
    generic,
    feeNote: pathway?.has_fee ? 'A producer fee applies under this law.' : null,
  };
}
