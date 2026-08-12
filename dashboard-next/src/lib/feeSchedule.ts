/**
 * Generalized packaging-EPR fee-schedule engine — the multi-jurisdiction
 * successor to the CA-SB-54-only cost layer in studio.ts.
 *
 * WHY THIS EXISTS
 * ---------------
 * studio.ts prices every swap against ONE hardcoded schedule (California SB 54,
 * ¢/lb → USD/tonne, with a flat plastic PPMF+reuse adder) and prices every
 * selected market against it. Research into FR/DE/ES/IT/UK/JP/KR/CA showed that
 * comparable per-material tables exist in most markets, but they differ on three
 * axes the old model can't express:
 *
 *   1. UNIT + CURRENCY   — ¢/lb, ¢/kg, €/tonne, €/kg, £/tonne, ¥/kg, ₩/kg.
 *   2. MODULATION SHAPE  — CA's flat adder is one of four shapes actually in use:
 *        · flat adder       (CA PPMF+reuse; France PCR primes)      → add_per_tonne
 *        · percent bonus/malus (France −4%/+100%, Spain, Québec)    → percent
 *        · multiplier tiers (UK RAM red/amber/green; Korea +20%)    → multiplier
 *        · discrete bands   (Italy fasce)  → modeled as base-rate selection, not modulation
 *   3. COMPOSITION       — how active rules combine differs by scheme:
 *        · stack            (France, Québec: bonuses/maluses accumulate)
 *        · exclusive_malus  (Spain: any malus = a single +10% that VOIDS all bonuses)
 *        · selector_plus_stack (UK: one RAM grade sets a base multiplier, then stack)
 *
 * This module encodes rates in their NATIVE unit, normalizes to a canonical
 * "major currency units per tonne" (carrying the currency — no FX baked in), and
 * runs a small rule engine that covers all four shapes and all three compositions.
 *
 * MIGRATION
 * ---------
 * studio.ts is left untouched. To adopt: replace its `FeeSchedule`/`ratePerTonne`
 * with a `Schedule` + `resolveRate()` from here (CA's flat adder becomes the one
 * modulation rule in `caSb54Schedule()`), and let the quote engine carry a
 * per-market schedule instead of a single global one. Germany/EU/China register
 * as "no published rate table" (see NOTE at the registry) rather than blank.
 */

// ---------------------------------------------------------------------------
// Currency + unit normalization
// ---------------------------------------------------------------------------

export type CurrencyCode = 'USD' | 'CAD' | 'EUR' | 'GBP' | 'JPY' | 'KRW';

/** Per-currency display facts: symbol, minor-unit divisor, and minor-unit suffix.
 *  JPY/KRW have no everyday minor unit (minorPerMajor 1), so per-package fees show
 *  in whole-currency with decimals rather than a cents-style suffix. */
export const CURRENCY_META: Record<CurrencyCode, { symbol: string; minorPerMajor: number; minorSuffix: string }> = {
  USD: { symbol: '$', minorPerMajor: 100, minorSuffix: '¢' },
  CAD: { symbol: 'C$', minorPerMajor: 100, minorSuffix: '¢' },
  EUR: { symbol: '€', minorPerMajor: 100, minorSuffix: 'c' },
  GBP: { symbol: '£', minorPerMajor: 100, minorSuffix: 'p' },
  JPY: { symbol: '¥', minorPerMajor: 1, minorSuffix: '' },
  KRW: { symbol: '₩', minorPerMajor: 1, minorSuffix: '' },
};

/** The native way a scheme quotes its rates. Everything normalizes to $/tonne-equivalent. */
export type RateUnit =
  | 'cents_per_lb'  // CA SB 54 (US cents)
  | 'cents_per_kg'  // Canadian provinces (CAD cents)
  | 'per_kg'        // France, Spain, Japan, Korea (major units/kg)
  | 'per_tonne';    // UK, Italy, Germany (major units/tonne)

const LB_PER_TONNE = 2204.62;
const KG_PER_TONNE = 1000;

/** Convert a native rate into canonical MAJOR currency units per tonne (currency preserved by caller). */
export function toRatePerTonne(value: number, unit: RateUnit): number {
  switch (unit) {
    case 'cents_per_lb':
      return (value / 100) * LB_PER_TONNE;
    case 'cents_per_kg':
      return (value / 100) * KG_PER_TONNE;
    case 'per_kg':
      return value * KG_PER_TONNE;
    case 'per_tonne':
      return value;
  }
}

const round2 = (n: number) => Math.round(n * 100) / 100;

// ---------------------------------------------------------------------------
// Package attributes — the inputs a modulation rule reads
// ---------------------------------------------------------------------------

/**
 * The design attributes of a single packaging component that eco-modulation keys
 * off. All optional: a scheme only reads the ones it modulates on. `flags` is the
 * escape hatch for scheme-specific signals (e.g. Spain's EVOH≥5%, France's MOAH).
 */
export interface PackageAttributes {
  /** Recyclability grade in the scheme's own vocabulary: 'A'|'B'|'C'|'D' (PPWR),
   *  'green'|'amber'|'red' (UK RAM), 'best'|'difficult' (Korea), etc. */
  recyclabilityGrade?: string | null;
  /** Post-consumer recycled content, %. Drives PCR bonuses (thresholds are scheme-specific). */
  pcrPercent?: number | null;
  /** 'clear' | 'natural' earn optical-sorting bonuses; 'colored' | 'opaque' are penalized. */
  color?: 'clear' | 'natural' | 'colored' | 'opaque' | null;
  /** Reusable/refillable system — often a full exemption (−100%). */
  reusable?: boolean;
  /** Any recycling-disruptor present (dark plastic, PVC sleeve, mineral filler, etc.). */
  hasRecyclingDisruptor?: boolean;
  /** Falls under the EU Single-Use-Plastics Directive litter surcharge (Spain, others). */
  singleUsePlastic?: boolean;
  flags?: Record<string, boolean | number | string>;
}

/** Context passed to a rule's predicate — lets category-scoped rules (CA's plastic adder) fire. */
export interface RuleContext {
  category?: string;
  format?: MaterialFormat;
}

/** A settable package attribute (excludes the free-form `flags` bag). */
export type AttrKey =
  | 'recyclabilityGrade'
  | 'pcrPercent'
  | 'color'
  | 'reusable'
  | 'hasRecyclingDisruptor'
  | 'singleUsePlastic';

/**
 * A design-attribute control a schedule wants surfaced in the UI — declared per
 * schedule so the studio only shows levers that scheme actually modulates on
 * (an input that changes no fee would be dishonest). Rules read the same attrs.
 */
export interface AttributeInput {
  attr: AttrKey;
  label: string;
  kind: 'select' | 'toggle' | 'number';
  /** For 'select' — the choices; the first is treated as the un-modulated base. */
  options?: { value: string; label: string }[];
  help?: string;
  /** For 'number' (e.g. pcrPercent) — unit suffix shown after the field. */
  suffix?: string;
}

// ---------------------------------------------------------------------------
// Modulation rules
// ---------------------------------------------------------------------------

/** The three arithmetic shapes every scheme's modulation reduces to. */
export type ModulationOp =
  /** Add a fixed amount, in canonical $/tonne-equivalent (CA adder, France PCR prime). */
  | { kind: 'add_per_tonne'; value: number }
  /** Signed percent of the base rate: −4 = a 4% bonus, +100 = a 100% malus. */
  | { kind: 'percent'; value: number }
  /** Multiply the running rate: 1.2 = UK red, 0.85 = UK green discount, 1.2 = Korea difficult. */
  | { kind: 'multiplier'; value: number };

export interface ModulationRule {
  id: string;
  label: string;
  op: ModulationOp;
  /**
   * 'bonus' lowers the fee, 'malus' raises it, 'selector' is a mutually-exclusive
   * base setter (UK RAM grade) — the composition policy treats the three differently.
   */
  role: 'bonus' | 'malus' | 'selector';
  /** True when this rule's condition is met for the package. Pure — no I/O. */
  applies: (attrs: PackageAttributes, ctx: RuleContext) => boolean;
}

/**
 * How active rules combine — the schemes genuinely need all three:
 *  - 'stack'                every active rule applies (France, Québec).
 *  - 'exclusive_malus'      if ANY malus is active, apply only the first malus and
 *                           drop all bonuses (Spain's non-cumulative +10% override).
 *  - 'selector_plus_stack'  exactly one 'selector' sets the base (UK grade multiplier),
 *                           then maluses/bonuses stack on top.
 */
export interface ModulationPolicy {
  compose: 'stack' | 'exclusive_malus' | 'selector_plus_stack';
  /** Percent ops computed against the pre-modulation base (default true) vs. the running rate. */
  percentOnBase?: boolean;
  /** Floor as a fraction of base — e.g. reuse '−100%' floors at 0 (minFractionOfBase: 0). */
  minFractionOfBase?: number;
  /** Cap as a fraction of base — e.g. Québec's ecodesign bonus capped at −50% (maxFractionOfBase stays 1). */
  maxFractionOfBase?: number;
}

export interface AppliedModulation {
  ruleId: string;
  label: string;
  /** Signed effect on the rate, canonical $/tonne-equivalent. */
  deltaPerTonne: number;
}

export interface ModulationResult {
  baseRatePerTonne: number;
  finalRatePerTonne: number;
  applied: AppliedModulation[];
}

/** One op's signed contribution. `refBase` is what percents multiply (base or running). */
function opDelta(op: ModulationOp, refBase: number, running: number): number {
  switch (op.kind) {
    case 'add_per_tonne':
      return op.value;
    case 'percent':
      return (refBase * op.value) / 100;
    case 'multiplier':
      return running * (op.value - 1);
  }
}

/**
 * Apply a scheme's modulation rules to a base rate for one package. Returns the
 * final rate plus a per-rule audit trail (so the UI can show "why this number").
 */
export function applyModulation(
  base: number,
  rules: ModulationRule[],
  attrs: PackageAttributes,
  policy: ModulationPolicy,
  ctx: RuleContext = {},
): ModulationResult {
  const active = rules.filter((r) => r.applies(attrs, ctx));
  const applied: AppliedModulation[] = [];
  const percentOnBase = policy.percentOnBase ?? true;
  let running = base;

  const fire = (rule: ModulationRule, refBase: number) => {
    const before = running;
    running += opDelta(rule.op, percentOnBase ? refBase : running, running);
    applied.push({ ruleId: rule.id, label: rule.label, deltaPerTonne: round2(running - before) });
  };

  const selectors = active.filter((r) => r.role === 'selector');
  const maluses = active.filter((r) => r.role === 'malus');
  const bonuses = active.filter((r) => r.role === 'bonus');

  if (policy.compose === 'selector_plus_stack') {
    if (selectors[0]) fire(selectors[0], base); // one grade sets the base
    const selectedBase = running; // subsequent percents key off the graded base
    for (const r of [...maluses, ...bonuses]) fire(r, selectedBase);
  } else if (policy.compose === 'exclusive_malus') {
    if (maluses.length) fire(maluses[0], base); // a malus voids every bonus
    else for (const r of bonuses) fire(r, base);
  } else {
    // 'stack' — selectors first (rare here), then maluses, then bonuses
    for (const r of [...selectors, ...maluses, ...bonuses]) fire(r, base);
  }

  if (policy.minFractionOfBase != null) running = Math.max(running, base * policy.minFractionOfBase);
  if (policy.maxFractionOfBase != null) running = Math.min(running, base * policy.maxFractionOfBase);

  return { baseRatePerTonne: round2(base), finalRatePerTonne: round2(running), applied };
}

// ---------------------------------------------------------------------------
// Schedule + material formats
// ---------------------------------------------------------------------------

/** A canonical coarse category — shared across schemes so a spec maps to any of them. */
export type MaterialCategory = string;

/**
 * One priced packaging format in a scheme's table. `tier` records what role the
 * format plays in its category so the studio's best/representative/worst UI still
 * works: 'best'|'worst' bound the eco-modulation spread; 'band' is one rung of a
 * discrete ladder (Italy); 'single' is a scheme with one rate per material (Japan/UK).
 */
export interface MaterialFormat {
  id: string;
  label: string;
  category: MaterialCategory;
  /** Base rate in the schedule's native `rateUnit` (before modulation). */
  baseRateNative: number;
  tier: 'best' | 'representative' | 'worst' | 'band' | 'single';
  recyclable?: boolean;
  tag?: string;
  /** Starting weight (g) when this format is picked for a new component. Optional —
   *  the studio falls back to a per-category default when absent. */
  default_g?: number;
}

/**
 * One jurisdiction's (or operator's) published producer-fee table. The registry
 * key is (jurisdiction, materialScope): Spain needs two entries — Ecoembes for
 * non-glass and Ecovidrio for glass, different operators and unit bases.
 */
export interface Schedule {
  id: string;
  /** ISO-ish jurisdiction code: 'US-CA', 'UK', 'CA-QC', 'FR', 'JP', 'ES'. */
  jurisdiction: string;
  /** 'all' or a material family this schedule is limited to (Spain glass → Ecovidrio). */
  materialScope: 'all' | string;
  program: string;
  currency: CurrencyCode;
  rateUnit: RateUnit;
  /** Rates are versioned by effective date, NOT year — Italy revises quarterly, UK escalates annually. */
  effectiveFrom?: string;
  effectiveTo?: string | null;
  citation: string;
  sourceUrl: string;
  /** Short UI provenance line, e.g. "CA SB-54 draft 2027 rates — final Oct 2026". */
  provenance: string;
  formats: MaterialFormat[];
  modulation: { rules: ModulationRule[]; policy: ModulationPolicy };
  /** Design-attribute controls the studio should surface for this schedule. Absent/
   *  empty = no per-component levers (fees vary only by material choice, as with CA). */
  inputs?: AttributeInput[];
}

export interface ResolvedRate {
  /** Final rate after modulation, canonical major-units/tonne, in `currency`. */
  ratePerTonne: number;
  currency: CurrencyCode;
  baseRatePerTonne: number;
  applied: AppliedModulation[];
}

/** Price one format under one schedule for a given package design. The single entry point. */
export function resolveRate(
  schedule: Schedule,
  format: MaterialFormat,
  attrs: PackageAttributes = {},
): ResolvedRate {
  const base = toRatePerTonne(format.baseRateNative, schedule.rateUnit);
  const mod = applyModulation(base, schedule.modulation.rules, attrs, schedule.modulation.policy, {
    category: format.category,
    format,
  });
  return {
    ratePerTonne: mod.finalRatePerTonne,
    currency: schedule.currency,
    baseRatePerTonne: mod.baseRatePerTonne,
    applied: mod.applied,
  };
}

// ---------------------------------------------------------------------------
// Registry — (jurisdiction, materialScope) → schedule, with honest gaps
// ---------------------------------------------------------------------------

const registry = new Map<string, Schedule>();
const keyOf = (jurisdiction: string, scope = 'all') => `${jurisdiction}|${scope}`;

export function registerSchedule(s: Schedule): void {
  registry.set(keyOf(s.jurisdiction, s.materialScope), s);
}

/** Resolve the schedule for a jurisdiction (optionally material-scoped, e.g. Spain glass). */
export function getSchedule(jurisdiction: string, scope = 'all'): Schedule | undefined {
  return registry.get(keyOf(jurisdiction, scope)) ?? registry.get(keyOf(jurisdiction, 'all'));
}

/**
 * NOTE — jurisdictions with NO encodable rate table. Register these so the UI
 * renders "no published producer fee schedule" honestly instead of a blank:
 *   · 'DE'  Germany — fees set by ~10 competing private dual systems, commercial/undisclosed.
 *           Only the ZSVR 22-category recyclability METHODOLOGY is public. Use representative
 *           ranges (plastics ~€800–1,170/t, PPK ~€200/t, glass ~€50/t) if a number is required.
 *   · 'EU'  PPWR sets modulation CRITERIA only — no rates until delegated acts (~2028),
 *           mandatory modulation ~2029. Never collapses to one table; would need ~27 PROs.
 *   · 'CN'  China — packaging EPR nascent; no per-material fee schedule (WEEE/battery/vehicle only).
 */
export type UnpricedReason = 'competitive_private' | 'criteria_only' | 'nascent';
export interface UnpricedJurisdiction {
  jurisdiction: string;
  reason: UnpricedReason;
  note: string;
}
export const UNPRICED_JURISDICTIONS: Record<string, UnpricedJurisdiction> = {
  DE: { jurisdiction: 'DE', reason: 'competitive_private', note: 'Fees set by competing private dual systems (undisclosed); ZSVR publishes recyclability methodology only.' },
  EU: { jurisdiction: 'EU', reason: 'criteria_only', note: 'PPWR harmonizes modulation criteria, not rates. Delegated acts ~2028; mandatory modulation ~2029.' },
  CN: { jurisdiction: 'CN', reason: 'nascent', note: 'Packaging EPR nascent — no per-material fee schedule. WEEE/battery/vehicle only.' },
};

// ---------------------------------------------------------------------------
// Worked adapters — CA (backward-compat) and UK (first new jurisdiction)
// ---------------------------------------------------------------------------

/**
 * California SB 54 — the existing studio.ts schedule expressed in the new model.
 * The plastic PPMF+reuse adder (21¢/lb) becomes the sole modulation rule, scoped
 * to plastic categories; the best/worst palette formats become base-rate tiers.
 *
 * ⚠️ STATUS: ILLUSTRATIVE, AND THE RATES BELOW NEED RE-VERIFICATION.
 * CAA published a "California Illustrative Fees" table on 1 May 2026 that is
 * explicitly "not final fees… good faith, non-binding"; final rates land with the
 * program plan in October 2026. Two known problems with what is encoded here:
 *
 *   1. The values predate the 1 May 2026 publication and are believed stale.
 *   2. `pp_ps` at 98¢/lb is labelled "PP bottle / PS foam — hard to recycle", but
 *      98 is reported to correspond to *Other/Mixed Plastics — Textiles* in the
 *      published table, i.e. the LABEL and the RATE may describe different rows.
 *
 * These have NOT been corrected here because the source PDF could not be retrieved
 * to verify replacements, and the governing rule (docs/PRO_TARIFF_INGESTION_PLAN.md)
 * is that a rate is never taken from a summary — a hallucinated tariff is worse than
 * no tariff because it looks authoritative. Fix by ingesting the CAA table directly.
 *
 * ⚠️ MISSING DIMENSION: California also levies a PPMF *component-based* fee of
 * ~$0.0010–0.0012 per plastic COMPONENT UNIT (20% of the $500M/yr fund, allocated
 * by piece count, not weight). This model has no piece-count input, so that charge
 * cannot be expressed at all. For a QSR shipping ~1bn lids/straws/sauce cups a year
 * it is a seven-figure line item. See docs/EXPOSURE_CALCULATOR_SPEC.md §4.
 */
export function caSb54Schedule(): Schedule {
  const plasticAdderPerTonne = toRatePerTonne(21.0, 'cents_per_lb'); // PPMF 17 + Reuse 4
  const isPlastic = (ctx: RuleContext) =>
    ctx.category === 'plastic_packaging' || ctx.category === 'plastic_film';

  return {
    id: 'ca-sb54',
    jurisdiction: 'US-CA',
    materialScope: 'all',
    program: 'CA SB-54',
    currency: 'USD',
    rateUnit: 'cents_per_lb',
    effectiveFrom: '2027-01-01',
    citation: 'Circular Action Alliance — California SB 54 EPR Program Plan, Ch. 9 Table 5 (draft; final Oct 2026).',
    sourceUrl: 'https://circularactionalliance.org/',
    provenance: 'CA SB-54 2027 ILLUSTRATIVE (non-binding) — final Oct 2026; rates predate the 1 May 2026 table',
    formats: [
      // base ¢/lb from Table 5 (low scenario); mirrors studio.ts FALLBACK_PALETTE.
      { id: 'pet_clear', label: 'PET / HDPE bottle — clear or natural', category: 'plastic_packaging', baseRateNative: 29, tier: 'best', recyclable: true, tag: 'best-in-class plastic' },
      { id: 'plastic_rep', label: 'Rigid plastic — mixed / pigmented', category: 'plastic_packaging', baseRateNative: 33, tier: 'representative', recyclable: true },
      { id: 'pp_ps', label: 'PP bottle / PS foam — hard to recycle', category: 'plastic_packaging', baseRateNative: 98, tier: 'worst', recyclable: false, tag: 'worst-in-class plastic' },
      // TODO: add an explicit 'other/mixed plastic — no recycling stream' worst-bucket
      // so niche resins (EVA foam, PC, PVC blends, multilayer) map to the ceiling rate
      // instead of having no home. See EVA-foam gap note.
      { id: 'corrugated', label: 'Corrugated cardboard — uncoated', category: 'paper_packaging', baseRateNative: 2, tier: 'best', recyclable: true },
      { id: 'poly_carton', label: 'Plastic-coated / laminate carton', category: 'paper_packaging', baseRateNative: 27, tier: 'worst', recyclable: false },
      { id: 'glass', label: 'Glass bottle / jar', category: 'glass_packaging', baseRateNative: 1, tier: 'best', recyclable: true },
      { id: 'aluminum', label: 'Aluminum can / container', category: 'aluminum_packaging', baseRateNative: 11, tier: 'representative', recyclable: true },
    ],
    modulation: {
      rules: [
        {
          id: 'plastic-ppmf-reuse',
          label: 'PPMF + Reuse Investment adder (plastic CMCs)',
          role: 'malus',
          op: { kind: 'add_per_tonne', value: plasticAdderPerTonne },
          applies: (_a, ctx) => isPlastic(ctx),
        },
      ],
      policy: { compose: 'stack' },
    },
  };
}

/**
 * UK pEPR (PackUK) — the cleanest new jurisdiction. Base fees are the Year-2
 * (2026-27) illustrative AMBER column (£/tonne); RAM grade sets the base via a
 * mutually-exclusive multiplier. Selector composition: exactly one grade applies.
 *
 * THE RED ESCALATOR IS THE HEADLINE NUMBER
 * ----------------------------------------
 * PackUK's modulation statement sets red at 1.2× for 2026-27, 1.6× for 2027-28
 * and 2.0× for 2028-29 — so a red-rated portfolio roughly DOUBLES its disposal
 * fee by 28-29 with zero change in tonnage. QSR formats (PE-lined paper cups,
 * black plastic, composite clamshells, laminated wraps) skew red, which makes
 * this projection more valuable than the current-year rate. Pass `programYear`
 * to price a future year.
 *
 * WHY GREEN IS NOT A RATE
 * -----------------------
 * Green is NOT a published multiplier. The red premium forms a redistribution
 * pot that PackUK spreads as an EQUAL PERCENTAGE DISCOUNT across all green-rated
 * material — so the actual discount is arithmetically dependent on the red/amber/
 * green mix of the whole market and cannot be known before the year is assessed.
 * PackUK's own Y2 working estimate is ~9%, and it is an estimate, not a rate.
 * (An earlier revision of this file hardcoded 0.9 as if it were published. It
 * isn't — hence the explicit label, which travels into the UI via
 * AppliedModulation.label so a user never sees the discount presented as fact.)
 *
 * NOTE ON LAG: modulated fees for 2026-27 are calculated from packaging supplied
 * in 2025. A redesign made today does not move the bill for ~18 months. Callers
 * showing "switch this format, save £X" must also say WHEN it lands.
 */
/** Published RAM red multipliers by pEPR program year (PackUK modulation statement). */
export const UK_RAM_RED_MULTIPLIER: Record<number, number> = {
  2026: 1.2, // 2026-27
  2027: 1.6, // 2027-28
  2028: 2.0, // 2028-29
};

/** PackUK's own working estimate of the Y2 green discount. NOT a published rate — the
 *  real figure is a market-mix-dependent redistribution of the red premium. Used only so
 *  a green-rated component isn't priced identically to amber; always surfaced as an estimate. */
export const UK_RAM_GREEN_ESTIMATE = 0.91;

export function ukPeprSchedule(programYear = 2026): Schedule {
  const red = UK_RAM_RED_MULTIPLIER[programYear] ?? UK_RAM_RED_MULTIPLIER[2026];
  const greenEstimate = UK_RAM_GREEN_ESTIMATE;
  return {
    id: `uk-pepr-${programYear}`,
    jurisdiction: 'UK',
    materialScope: 'all',
    program: 'UK pEPR (PackUK)',
    currency: 'GBP',
    rateUnit: 'per_tonne',
    effectiveFrom: '2026-04-01',
    citation: 'DEFRA / PackUK — Year 2 (2026-27) illustrative waste-disposal fees + RAM modulation statement.',
    sourceUrl: 'https://www.gov.uk/government/publications/year-2-illustrative-waste-disposal-fees-extended-producer-responsibility-for-packaging/year-2-illustrative-waste-disposal-fees-extended-producer-responsibility-for-packaging',
    provenance: `UK pEPR ${programYear}-${String(programYear + 1).slice(2)} ILLUSTRATIVE (amber base) — RAM red ×${red}; green discount estimated, not published`,
    formats: [
      // Amber column, £/tonne (the unmodulated base). Green/red derived via the grade multiplier.
      { id: 'aluminium', label: 'Aluminium', category: 'aluminum_packaging', baseRateNative: 270, tier: 'single', recyclable: true },
      { id: 'fbc', label: 'Fibre-based composite', category: 'paper_packaging', baseRateNative: 525, tier: 'single', recyclable: false },
      { id: 'glass', label: 'Glass', category: 'glass_packaging', baseRateNative: 205, tier: 'single', recyclable: true },
      { id: 'paper', label: 'Paper and board', category: 'paper_packaging', baseRateNative: 210, tier: 'single', recyclable: true },
      { id: 'plastic', label: 'Plastic', category: 'plastic_packaging', baseRateNative: 455, tier: 'single', recyclable: true },
      { id: 'steel', label: 'Steel', category: 'aluminum_packaging', baseRateNative: 290, tier: 'single', recyclable: true },
      { id: 'wood', label: 'Wood', category: 'wood_packaging', baseRateNative: 450, tier: 'single', recyclable: true },
      { id: 'other', label: 'Other (bamboo, ceramic, cork, hemp…)', category: 'other_packaging', baseRateNative: 225, tier: 'single', recyclable: false },
    ],
    modulation: {
      rules: [
        {
          id: 'ram-red',
          label: `RAM red — not currently recyclable (×${red}, ${programYear}-${String(programYear + 1).slice(2)})`,
          role: 'selector',
          op: { kind: 'multiplier', value: red },
          applies: (a) => a.recyclabilityGrade === 'red',
        },
        {
          id: 'ram-green',
          label: 'RAM green — ESTIMATED discount (~9%); the published figure depends on the whole market’s RAG mix',
          role: 'selector',
          op: { kind: 'multiplier', value: greenEstimate },
          applies: (a) => a.recyclabilityGrade === 'green',
        },
        // amber = no rule → base fee applies unmodulated.
      ],
      policy: { compose: 'selector_plus_stack' },
    },
    inputs: [
      {
        attr: 'recyclabilityGrade',
        label: 'Recyclability (RAM)',
        kind: 'select',
        help:
          `PackUK Recyclability Assessment. Amber is the base fee; red pays ×${red} this program year ` +
          `(rising to ×1.6 in 2027-28 and ×2.0 in 2028-29). The green discount is an estimate, not a ` +
          `published rate — it is funded by the red premium and depends on the market’s RAG mix. ` +
          `Assess per COMPONENT, not per pack: a cup, its lid and its sleeve can grade differently.`,
        options: [
          { value: 'amber', label: 'Amber — base fee' },
          { value: 'green', label: 'Green — widely recyclable (discount estimated)' },
          { value: 'red', label: `Red — not currently recyclable (×${red})` },
        ],
      },
    ],
  };
}

/**
 * Japan — JCPRA Containers & Packaging Recycling Law commissioned unit prices.
 * A flat per-material tariff in ¥/kg (FY2025 execution prices), NO eco-modulation
 * (a cost pass-through set by reverse auction). Plastic additionally carries the
 * FY2024 contribution unit price (1.8 ¥/kg) — modeled as an add-rate, mirroring
 * CA's adder. Proves the currency (JPY) + unit (per_kg) + "no modulation" paths.
 */
export function jpJcpraSchedule(): Schedule {
  return {
    id: 'jp-jcpra-2025',
    jurisdiction: 'JP',
    materialScope: 'all',
    program: 'Japan JCPRA (Containers & Packaging Recycling Law)',
    currency: 'JPY',
    rateUnit: 'per_kg',
    effectiveFrom: '2025-04-01',
    citation: 'JCPRA — FY2025 再商品化実施委託単価 (recycling execution commissioned unit prices) + FY2024 contribution unit price.',
    sourceUrl: 'https://www.jcpra.or.jp/library/fee-data.html',
    provenance: 'Japan JCPRA FY2025 unit prices (¥/kg)',
    formats: [
      { id: 'glass_clear', label: 'Glass — colorless', category: 'glass_packaging', baseRateNative: 11.0, tier: 'single', recyclable: true },
      { id: 'glass_amber', label: 'Glass — amber/brown', category: 'glass_packaging', baseRateNative: 13.9, tier: 'single', recyclable: true },
      { id: 'glass_other', label: 'Glass — other colors', category: 'glass_packaging', baseRateNative: 20.2, tier: 'single', recyclable: true },
      // PET bottles are a distinct JCPRA category from plastic packaging and carry NO
      // contribution price — kept out of 'plastic_packaging' so the adder rule skips it.
      { id: 'pet', label: 'PET bottles', category: 'pet_bottle_packaging', baseRateNative: 8.8, tier: 'single', recyclable: true },
      { id: 'paper', label: 'Paper packaging', category: 'paper_packaging', baseRateNative: 22.0, tier: 'single', recyclable: true },
      { id: 'plastic', label: 'Plastic packaging', category: 'plastic_packaging', baseRateNative: 63.0, tier: 'single', recyclable: false },
    ],
    modulation: {
      rules: [
        {
          id: 'plastic-contribution',
          label: 'Rationalization contribution (plastic, FY2024)',
          role: 'malus',
          op: { kind: 'add_per_tonne', value: toRatePerTonne(1.8, 'per_kg') },
          applies: (_a, ctx) => ctx.category === 'plastic_packaging',
        },
      ],
      policy: { compose: 'stack' },
    },
  };
}

/**
 * Oregon PY2026 (CAA) — a CONFIRMED, binding, currently-invoiced US schedule.
 *
 * Transcribed from the source PDF (`OR-2026-Fee-Schedule-Public.pdf`, CAA,
 * published 29 Oct 2025), parsed with pypdf — not derived from a summary. Rates
 * are the FINAL FEE RATE column in ¢/lb. `Base + SIM = Final`; the SIM (Statewide
 * Implementation Modulation) column is 0.0 ¢/lb on every row for PY2026, so Final
 * equals Base this year. SIM is a live mechanism, so re-read it each program year
 * rather than assuming zero.
 *
 * `Type` in the source records recycling-acceptance status — USCL (statewide
 * collection list), PRO (PRO acceptance list) or N/A (on neither). N/A is what
 * drives the punitive rates, and it is the reason the SAME poly-coated paper cup
 * costs 48.0¢/lb here and 20.0¢/lb in Colorado: the driver is each state's
 * collection list, not the packaging. Recorded in `tag` so the UI can say why.
 *
 * NOTE ON ATTRIBUTION: under ORS 459A.866(3) the producer of FOOD SERVICEWARE in
 * Oregon is "the person that first sells the food serviceware in or into this
 * state" — the supplier, not the brand owner. Pricing a restaurant chain's cups
 * against this table does NOT mean the chain owes the fee. See
 * docs/EXPOSURE_CALCULATOR_SPEC.md §3.
 */
export function orCaaSchedule(): Schedule {
  return {
    id: 'us-or-caa-2026',
    jurisdiction: 'US-OR',
    materialScope: 'all',
    program: 'Oregon RMA (Circular Action Alliance)',
    currency: 'USD',
    rateUnit: 'cents_per_lb',
    effectiveFrom: '2026-01-01',
    effectiveTo: '2026-12-31',
    citation:
      'Circular Action Alliance — 2026 Oregon Producer Fee Schedule, Program Year 2026 ' +
      '(published 29 Oct 2025). Final Fee Rate column; SIM portion 0.0¢/lb throughout.',
    sourceUrl: 'https://circularactionalliance.org/',
    provenance: 'Oregon PY2026 CONFIRMED — binding, currently invoiced',
    formats: [
      // Printing and Writing Paper — five source rows share one rate (5.0¢/lb); collapsed.
      { id: 'or_printed', label: 'Printing & writing paper (newspapers, magazines, general use)', category: 'printed_paper', baseRateNative: 5, tier: 'single', recyclable: true, tag: 'USCL' },
      // Glass and Ceramics
      { id: 'or_glass', label: 'Glass bottles, jars & other containers', category: 'glass_packaging', baseRateNative: 10, tier: 'best', recyclable: true, tag: 'PRO' },
      { id: 'or_ceramic', label: 'Ceramic — all forms', category: 'glass_packaging', baseRateNative: 111, tier: 'worst', recyclable: false, tag: 'not accepted' },
      // Metal
      { id: 'or_alu_can', label: 'Aluminium containers', category: 'aluminum_packaging', baseRateNative: 6, tier: 'best', recyclable: true, tag: 'USCL' },
      { id: 'or_steel_can', label: 'Steel containers', category: 'aluminum_packaging', baseRateNative: 10, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_alu_foil', label: 'Aluminium foil & molded containers', category: 'aluminum_packaging', baseRateNative: 24, tier: 'representative', recyclable: true, tag: 'PRO' },
      { id: 'or_metal_small', label: 'Metal — small format', category: 'aluminum_packaging', baseRateNative: 26, tier: 'representative', recyclable: true, tag: 'PRO' },
      { id: 'or_alu_aerosol', label: 'Aluminium aerosol containers', category: 'aluminum_packaging', baseRateNative: 64, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_steel_aerosol', label: 'Steel aerosol containers', category: 'aluminum_packaging', baseRateNative: 64, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_steel_other', label: 'Steel — other forms', category: 'aluminum_packaging', baseRateNative: 68, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_alu_other', label: 'Aluminium — other forms', category: 'aluminum_packaging', baseRateNative: 78, tier: 'worst', recyclable: false, tag: 'not accepted' },
      // Paper / Fiber
      { id: 'or_occ_transport', label: 'Corrugated cardboard — tertiary/transport, non-consumer', category: 'paper_packaging', baseRateNative: 0, tier: 'best', recyclable: true, tag: 'USCL · zero-rated' },
      { id: 'or_occ', label: 'Corrugated cardboard', category: 'paper_packaging', baseRateNative: 8, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_paperboard', label: 'Paperboard', category: 'paper_packaging', baseRateNative: 8, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_kraft', label: 'Kraft paper (bags, wraps)', category: 'paper_packaging', baseRateNative: 8, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_paper_other', label: 'Other paper packaging', category: 'paper_packaging', baseRateNative: 8, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_carton', label: 'Aseptic & gable-top cartons', category: 'paper_packaging', baseRateNative: 17, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_paper_small', label: 'Paper — small format', category: 'paper_packaging', baseRateNative: 44, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_polycoat', label: 'Poly-coated paperboard — hot/cold paper cups', category: 'paper_packaging', baseRateNative: 48, tier: 'representative', recyclable: false, tag: 'not accepted — 2.4× Colorado' },
      { id: 'or_paper_laminate', label: 'Other paper laminates', category: 'paper_packaging', baseRateNative: 51, tier: 'worst', recyclable: false, tag: 'not accepted' },
      // Plastic — Rigid
      { id: 'or_hdpe_nat', label: 'HDPE (#2) bottles, jugs & jars — clear/natural', category: 'plastic_packaging', baseRateNative: 9, tier: 'best', recyclable: true, tag: 'USCL' },
      { id: 'or_hdpe_pails', label: 'HDPE (#2) pails & buckets', category: 'plastic_packaging', baseRateNative: 18, tier: 'representative', recyclable: true, tag: 'PRO' },
      { id: 'or_pp_tubs', label: 'PP (#5) tubs, pails & buckets', category: 'plastic_packaging', baseRateNative: 19, tier: 'representative', recyclable: true, tag: 'PRO' },
      { id: 'or_pet_nat', label: 'PET (#1) bottles, jugs & jars — clear/natural', category: 'plastic_packaging', baseRateNative: 25, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_lids_hdpe', label: 'HDPE (#2) package handles & lids', category: 'plastic_packaging', baseRateNative: 29, tier: 'representative', recyclable: true, tag: 'PRO' },
      { id: 'or_lids_ldpe', label: 'LDPE (#4) lids', category: 'plastic_packaging', baseRateNative: 29, tier: 'representative', recyclable: true, tag: 'PRO' },
      { id: 'or_lids_pp', label: 'PP (#5) lids', category: 'plastic_packaging', baseRateNative: 29, tier: 'representative', recyclable: true, tag: 'PRO · half the cup rate' },
      { id: 'or_hdpe_pig', label: 'HDPE (#2) bottles, jugs & jars — pigmented', category: 'plastic_packaging', baseRateNative: 32, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_hdpe_tubs', label: 'HDPE (#2) tubs, nursery pots & trays', category: 'plastic_packaging', baseRateNative: 35, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_pp_bottles', label: 'PP (#5) bottles, jugs & jars', category: 'plastic_packaging', baseRateNative: 38, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_pet_tubs', label: 'PET (#1) tubs', category: 'plastic_packaging', baseRateNative: 50, tier: 'representative', recyclable: true, tag: 'USCL' },
      { id: 'or_pet_thermo', label: 'PET (#1) thermoformed containers, cups, plates, trays', category: 'plastic_packaging', baseRateNative: 57, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_pet_lids', label: 'PET (#1) lids', category: 'plastic_packaging', baseRateNative: 60, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_pp_containers', label: 'PP (#5) other rigid containers, cups, plates, trays', category: 'plastic_packaging', baseRateNative: 62, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_ldpe_bottles', label: 'LDPE (#4) bottles, jugs & jars', category: 'plastic_packaging', baseRateNative: 66, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_hdpe_other', label: 'HDPE (#2) other rigid items', category: 'plastic_packaging', baseRateNative: 66, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_ldpe_other', label: 'LDPE (#4) other rigid items', category: 'plastic_packaging', baseRateNative: 66, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_pp_other', label: 'PP (#5) other rigid items', category: 'plastic_packaging', baseRateNative: 66, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_pet_pig', label: 'PET (#1) bottles, jugs & jars — pigmented', category: 'plastic_packaging', baseRateNative: 67, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_pet_other', label: 'PET (#1) other rigid items', category: 'plastic_packaging', baseRateNative: 70, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_pvc', label: 'PVC (#3) rigid items', category: 'plastic_packaging', baseRateNative: 97, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_ps_rigid', label: 'PS (#6) rigid non-expanded', category: 'plastic_packaging', baseRateNative: 97, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_pla_rigid', label: 'PLA / PHA / PHB rigid — compostable', category: 'plastic_packaging', baseRateNative: 97, tier: 'representative', recyclable: false, tag: 'not accepted — compostables are PENALISED here' },
      { id: 'or_mixed_rigid', label: 'Other / mixed rigid plastic', category: 'plastic_packaging', baseRateNative: 97, tier: 'representative', recyclable: false, tag: 'not accepted' },
      { id: 'or_ps_foam', label: 'PS (#6) expanded/foamed containers, plates, cups, trays', category: 'plastic_packaging', baseRateNative: 138, tier: 'worst', recyclable: false, tag: 'not accepted — worst in schedule' },
      // Plastic — Flexible
      { id: 'or_pallet_wrap', label: 'HDPE/LDPE pallet wrap — non-consumer', category: 'plastic_film', baseRateNative: 34, tier: 'best', recyclable: true, tag: 'PRO' },
      { id: 'or_pe_film', label: 'HDPE (#2)/LDPE (#4) flexible & film items', category: 'plastic_film', baseRateNative: 43, tier: 'representative', recyclable: true, tag: 'PRO' },
      { id: 'or_pp_film', label: 'PP (#5) flexible & film items', category: 'plastic_film', baseRateNative: 102, tier: 'worst', recyclable: false, tag: 'not accepted' },
      { id: 'or_pla_film', label: 'PLA / PHA / PHB flexible & film — compostable', category: 'plastic_film', baseRateNative: 102, tier: 'worst', recyclable: false, tag: 'not accepted' },
      { id: 'or_laminate_film', label: 'Plastic laminates & other flexible packaging', category: 'plastic_film', baseRateNative: 102, tier: 'worst', recyclable: false, tag: 'not accepted' },
      // Plastic — Other
      { id: 'or_plastic_small', label: 'Plastic — small format (straws, stirrers, sachets)', category: 'other_packaging', baseRateNative: 28, tier: 'best', recyclable: true, tag: 'PRO' },
      { id: 'or_plastic_hazard', label: 'Plastic containers for automotive/hazardous products', category: 'other_packaging', baseRateNative: 63, tier: 'worst', recyclable: false, tag: 'not accepted' },
      // Wood and Other Organic Materials
      { id: 'or_wood', label: 'Wood & other organic materials', category: 'wood_packaging', baseRateNative: 105, tier: 'single', recyclable: false, tag: 'not accepted' },
    ],
    // SIM is 0.0¢/lb on every PY2026 row, so there is no modulation rule to apply.
    // Oregon's eco-modulation lives in the acceptance-list assignment already baked
    // into each rate, not in a separate multiplier.
    modulation: { rules: [], policy: { compose: 'stack' } },
  };
}

/**
 * Colorado PY2026 (CAA) — the second CONFIRMED, binding, currently-invoiced US schedule.
 *
 * Transcribed from `CO-2026-Dues-Schedule-Public.pdf` (CAA, published 13 Oct 2025),
 * parsed with pypdf. Rates are the FINAL DUES column in ¢/lb.
 *
 * ECO-MODULATION IS ALREADY BAKED IN — this is the important structural difference
 * from every other schedule here. The source columns are
 * `Base Dues + Detriments Malus + Not-on-MRL Malus + High-Recycling-Rate Bonus = Final Dues`,
 * and state law requires those PASSIVE factors to be applied automatically to
 * producer invoices. So Final Dues is the rate a producer actually pays and we
 * encode it directly, with NO modulation rules — adding any would double-count.
 * The published passive factors are: +5% for materials that disrupt recycling;
 * an uplift ensuring AML materials sit ≥20% above comparable MRL materials and
 * Not-Collected ≥10% above comparable AML; −5% for high recycling rates.
 * Four ACTIVE incentives exist for PY2026 and are not encoded (guidance pending).
 *
 * `tag` carries the acceptance status — MRL (Minimum Recyclable List), AML
 * (Additional Materials List) or N/C (not collected) — which is what drives the spread.
 */
export function coCaaSchedule(): Schedule {
  return {
    id: 'us-co-caa-2026',
    jurisdiction: 'US-CO',
    materialScope: 'all',
    program: 'Colorado PRO (Circular Action Alliance)',
    currency: 'USD',
    rateUnit: 'cents_per_lb',
    effectiveFrom: '2026-01-01',
    effectiveTo: '2026-12-31',
    citation:
      'Circular Action Alliance — 2026 Colorado Producer Dues Schedule, Program Year 2026 ' +
      '(published 13 Oct 2025). Final Dues column; passive eco-modulation already applied.',
    sourceUrl: 'https://circularactionalliance.org/',
    provenance: 'Colorado PY2026 CONFIRMED — binding, passive eco-modulation included in the rate',
    formats: [
      { id: 'co_printed', label: 'Printing & writing paper (newspapers, magazines, general use)', category: 'printed_paper', baseRateNative: 6, tier: 'single', recyclable: true, tag: 'MRL' },
      // Glass and Ceramics
      { id: 'co_glass', label: 'Glass bottles, jars & other containers', category: 'glass_packaging', baseRateNative: 4, tier: 'best', recyclable: true, tag: 'MRL · high-recycling bonus applied' },
      { id: 'co_ceramic', label: 'Ceramic — all forms', category: 'glass_packaging', baseRateNative: 47, tier: 'worst', recyclable: false, tag: 'N/C' },
      // Metal
      { id: 'co_alu_can', label: 'Aluminium containers', category: 'aluminum_packaging', baseRateNative: 2, tier: 'best', recyclable: true, tag: 'MRL · high-recycling bonus applied' },
      { id: 'co_steel_can', label: 'Steel containers', category: 'aluminum_packaging', baseRateNative: 7, tier: 'representative', recyclable: true, tag: 'MRL · high-recycling bonus applied' },
      { id: 'co_alu_aerosol', label: 'Aluminium aerosol containers', category: 'aluminum_packaging', baseRateNative: 14, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_steel_aerosol', label: 'Steel aerosol containers', category: 'aluminum_packaging', baseRateNative: 14, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_metal_small', label: 'Metal — small format', category: 'aluminum_packaging', baseRateNative: 32, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_alu_other', label: 'Aluminium — other forms', category: 'aluminum_packaging', baseRateNative: 33, tier: 'representative', recyclable: false, tag: 'AML' },
      { id: 'co_alu_foil', label: 'Aluminium foil & molded containers', category: 'aluminum_packaging', baseRateNative: 34, tier: 'representative', recyclable: false, tag: 'AML' },
      { id: 'co_steel_other', label: 'Steel — other forms', category: 'aluminum_packaging', baseRateNative: 34, tier: 'worst', recyclable: false, tag: 'AML' },
      // Paper / Fiber
      { id: 'co_occ', label: 'Corrugated cardboard', category: 'paper_packaging', baseRateNative: 8, tier: 'best', recyclable: true, tag: 'MRL · high-recycling bonus applied' },
      { id: 'co_paperboard', label: 'Paperboard', category: 'paper_packaging', baseRateNative: 8, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_kraft', label: 'Kraft paper (bags, wraps)', category: 'paper_packaging', baseRateNative: 8, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_carton', label: 'Aseptic & gable-top cartons', category: 'paper_packaging', baseRateNative: 13, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_paper_other', label: 'Other paper packaging', category: 'paper_packaging', baseRateNative: 13, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_polycoat', label: 'Poly-coated paperboard — hot/cold paper cups', category: 'paper_packaging', baseRateNative: 20, tier: 'representative', recyclable: false, tag: 'AML · 0.4× Oregon' },
      { id: 'co_paper_small', label: 'Paper — small format', category: 'paper_packaging', baseRateNative: 22, tier: 'representative', recyclable: false, tag: 'AML' },
      { id: 'co_waxed_occ', label: 'Waxed corrugated cardboard', category: 'paper_packaging', baseRateNative: 25, tier: 'representative', recyclable: false, tag: 'N/C' },
      { id: 'co_molded_pulp', label: 'Molded pulp food serviceware', category: 'paper_packaging', baseRateNative: 26, tier: 'representative', recyclable: false, tag: 'AML' },
      { id: 'co_paper_laminate', label: 'Other paper laminates', category: 'paper_packaging', baseRateNative: 30, tier: 'worst', recyclable: false, tag: 'AML' },
      // Plastic — Rigid
      { id: 'co_hdpe_nat', label: 'HDPE (#2) bottles, jugs & jars — clear/natural', category: 'plastic_packaging', baseRateNative: 14, tier: 'best', recyclable: true, tag: 'MRL · high-recycling bonus applied' },
      { id: 'co_pet_nat', label: 'PET (#1) bottles, jugs & jars — clear/natural', category: 'plastic_packaging', baseRateNative: 15, tier: 'representative', recyclable: true, tag: 'MRL · high-recycling bonus applied' },
      { id: 'co_pet_rigid_nat', label: 'PET (#1) containers, cups, lids, plates, trays, tubs — clear/natural', category: 'plastic_packaging', baseRateNative: 17, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_pp_bottles', label: 'PP (#5) bottles, jugs & jars', category: 'plastic_packaging', baseRateNative: 20, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_pp_containers', label: 'PP (#5) containers, cups, lids, plates, trays, tubs', category: 'plastic_packaging', baseRateNative: 20, tier: 'representative', recyclable: true, tag: 'MRL · 0.3× Oregon' },
      { id: 'co_hdpe_pig', label: 'HDPE (#2) bottles, jugs & jars — pigmented', category: 'plastic_packaging', baseRateNative: 23, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_hdpe_tubs', label: 'HDPE (#2) tubs', category: 'plastic_packaging', baseRateNative: 25, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_pp_other', label: 'PP (#5) other rigid items', category: 'plastic_packaging', baseRateNative: 25, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_hdpe_pails', label: 'HDPE (#2) pails & buckets', category: 'plastic_packaging', baseRateNative: 28, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_hdpe_other', label: 'HDPE (#2) other rigid items', category: 'plastic_packaging', baseRateNative: 31, tier: 'representative', recyclable: true, tag: 'MRL' },
      { id: 'co_pet_pig', label: 'PET (#1) bottles, jugs & jars — pigmented', category: 'plastic_packaging', baseRateNative: 43, tier: 'representative', recyclable: false, tag: 'AML · detriments malus applied' },
      { id: 'co_ldpe_bottles', label: 'LDPE (#4) bottles, jugs & jars', category: 'plastic_packaging', baseRateNative: 50, tier: 'representative', recyclable: false, tag: 'AML' },
      { id: 'co_pet_rigid_pig', label: 'PET (#1) containers, cups, lids, plates, trays, tubs — pigmented', category: 'plastic_packaging', baseRateNative: 50, tier: 'representative', recyclable: false, tag: 'AML · 2.9× the clear equivalent' },
      { id: 'co_pet_other', label: 'PET (#1) other rigid items', category: 'plastic_packaging', baseRateNative: 50, tier: 'representative', recyclable: false, tag: 'AML' },
      { id: 'co_ldpe_other', label: 'LDPE (#4) other rigid items', category: 'plastic_packaging', baseRateNative: 55, tier: 'representative', recyclable: false, tag: 'AML' },
      { id: 'co_hdpe_squeeze', label: 'HDPE (#2) squeeze tubes', category: 'plastic_packaging', baseRateNative: 71, tier: 'representative', recyclable: false, tag: 'AML' },
      { id: 'co_pp_squeeze', label: 'PP (#5) squeeze tubes', category: 'plastic_packaging', baseRateNative: 73, tier: 'representative', recyclable: false, tag: 'AML' },
      { id: 'co_ps_rigid', label: 'PS (#6) rigid non-expanded', category: 'plastic_packaging', baseRateNative: 78, tier: 'representative', recyclable: false, tag: 'N/C' },
      { id: 'co_mixed_rigid', label: 'Other / mixed rigid plastic', category: 'plastic_packaging', baseRateNative: 78, tier: 'representative', recyclable: false, tag: 'N/C' },
      { id: 'co_pvc', label: 'PVC (#3) rigid items', category: 'plastic_packaging', baseRateNative: 81, tier: 'representative', recyclable: false, tag: 'N/C · detriments malus applied' },
      { id: 'co_ps_foam', label: 'PS (#6) expanded/foamed containers, plates, cups, trays', category: 'plastic_packaging', baseRateNative: 172, tier: 'worst', recyclable: false, tag: 'N/C · worst in schedule, 8.6× the clear-PET cup' },
      // Plastic — Flexible
      { id: 'co_pe_film', label: 'HDPE (#2)/LDPE (#4) flexible & film items', category: 'plastic_film', baseRateNative: 48, tier: 'best', recyclable: false, tag: 'AML' },
      { id: 'co_pp_film', label: 'PP (#5) flexible & film items', category: 'plastic_film', baseRateNative: 64, tier: 'representative', recyclable: false, tag: 'N/C' },
      { id: 'co_laminate_film', label: 'Plastic laminates & other flexible packaging', category: 'plastic_film', baseRateNative: 74, tier: 'worst', recyclable: false, tag: 'N/C · detriments malus applied' },
      // Certified compostable — Colorado prices these as their own class, unlike Oregon.
      { id: 'co_comp_plastic_coated', label: 'Compostable plastic / polymer-coated substrate (ASTM D6868-21)', category: 'compostable_packaging', baseRateNative: 26, tier: 'best', recyclable: false, tag: 'N/C · certified compostable' },
      { id: 'co_comp_rigid', label: 'Compostable rigid plastic (ASTM D6400-23)', category: 'compostable_packaging', baseRateNative: 27, tier: 'representative', recyclable: false, tag: 'N/C · certified compostable' },
      { id: 'co_comp_flex', label: 'Compostable flexible plastic (ASTM D6400-23)', category: 'compostable_packaging', baseRateNative: 31, tier: 'representative', recyclable: false, tag: 'N/C · certified compostable' },
      { id: 'co_comp_paper', label: 'Compostable paper (ASTM D8410-22)', category: 'compostable_packaging', baseRateNative: 32, tier: 'worst', recyclable: false, tag: 'N/C · certified compostable' },
      // Plastic — Other
      { id: 'co_plastic_small', label: 'Plastic — small format (straws, stirrers, sachets, cutlery)', category: 'other_packaging', baseRateNative: 52, tier: 'best', recyclable: false, tag: 'N/C · detriments malus applied' },
      { id: 'co_plastic_hazard', label: 'Plastic packaging — hazardous or special products', category: 'other_packaging', baseRateNative: 52, tier: 'worst', recyclable: false, tag: 'N/C · detriments malus applied' },
      // Wood and Other Organics
      { id: 'co_wood', label: 'Wood & other organic materials', category: 'wood_packaging', baseRateNative: 84, tier: 'single', recyclable: false, tag: 'N/C · detriments malus applied' },
    ],
    // Passive eco-modulation is ALREADY in the Final Dues figures above — adding rules
    // here would double-count. The four active PY2026 incentives are not yet published
    // in enough detail to encode.
    modulation: { rules: [], policy: { compose: 'stack' } },
  };
}

/** Register the schedules that have real, encodable tables today. Idempotent. */
export function registerBuiltinSchedules(): void {
  registerSchedule(caSb54Schedule());
  registerSchedule(ukPeprSchedule());
  registerSchedule(jpJcpraSchedule());
  registerSchedule(orCaaSchedule());
  registerSchedule(coCaaSchedule());
  // Next: Canada (CA-BC / CA-AB / CA-QC — ¢/kg, QC has stacking bonus/malus),
  // France (FR — €/kg + phased %), Spain (ES all + ES glass/Ecovidrio — exclusive_malus),
  // Italy (IT — band tiers).
}

// Populate the registry on module load so getSchedule() / scheduleForMarket() work
// for any importer without an explicit init step. Re-running is harmless (same keys).
registerBuiltinSchedules();

// ---------------------------------------------------------------------------
// Market + region → schedule resolution — "price each market against its own
// schedule, sync to the highlighted region, fall back to the flagship".
// ---------------------------------------------------------------------------

/** The flagship schedule every market falls back to when it has no own table. */
export const FLAGSHIP_SCHEDULE_JURISDICTION = 'US-CA';

/**
 * Which jurisdiction's schedule prices a given studio market.
 *
 * CORRECTED 2026-08-11. This function used to route EVERY US state to the CA
 * flagship on the stated grounds that "CA SB 54 is the only detailed US schedule".
 * That is no longer true, and the direction of the error mattered: Oregon PY2026
 * and Colorado PY2026 are published, binding and currently being invoiced, while
 * California's 2027 rates remain explicitly non-binding until October 2026. We
 * were proxying two CONFIRMED tables onto an ILLUSTRATIVE one.
 *
 * Resolution order: exact jurisdiction key → `US-` prefixed state key → flagship.
 *
 *   scheduleForMarket('CA')  → us-ca (California-the-state, SB 54 — still illustrative)
 *   scheduleForMarket('OR')  → us-or-caa-2026 (CONFIRMED, binding)
 *   scheduleForMarket('CO')  → us-co-caa-2026 (CONFIRMED, binding)
 *   scheduleForMarket('WA')  → US-CA flagship (no published WA table; fees start 2030)
 *   scheduleForMarket('UK')  → uk-pepr-2026
 *   scheduleForMarket('FR')  → FR schedule when registered, else flagship
 *
 * Callers must surface `schedule.provenance` — a proxied state and a confirmed one
 * look identical in the returned shape, and only one of them is a real quote.
 */
export function scheduleForMarket(market: string, scope = 'all'): Schedule | undefined {
  const direct = getSchedule(market, scope);
  if (direct) return direct;
  // Bare US state codes ('OR') resolve against their registered 'US-OR' key.
  const stateKeyed = /^[A-Z]{2}$/.test(market) ? getSchedule(`US-${market}`, scope) : undefined;
  if (stateKeyed) return stateKeyed;
  // Anything still without its own table → flagship, as an explicit approximation.
  return getSchedule(FLAGSHIP_SCHEDULE_JURISDICTION);
}

/** True when `market` is priced on another jurisdiction's table rather than its own —
 *  the signal the UI needs to label a figure "priced on CA SB 54" instead of quoting it
 *  as this market's rate. Mirrors the resolution order in `scheduleForMarket`. */
export function isProxyPriced(market: string, scope = 'all'): boolean {
  const resolved = scheduleForMarket(market, scope);
  if (!resolved) return false;
  const own = getSchedule(market, scope) ?? (/^[A-Z]{2}$/.test(market) ? getSchedule(`US-${market}`, scope) : undefined);
  return own?.id !== resolved.id;
}

/**
 * The default schedule for the globally-highlighted region (RegionContext's
 * US/EU primary). US → the SB 54 flagship. EU is criteria-only today
 * (UNPRICED_JURISDICTIONS.EU) — return undefined so callers show the honest
 * "no EU pricing basis yet" note rather than mispricing EU packaging in USD.
 */
export function scheduleForRegion(regionPrimary: string): Schedule | undefined {
  if (regionPrimary === 'US') return getSchedule(FLAGSHIP_SCHEDULE_JURISDICTION);
  return getSchedule(regionPrimary); // 'EU' etc. → undefined until a real table lands
}
