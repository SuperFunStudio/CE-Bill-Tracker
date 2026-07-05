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
 * Proves the general engine reproduces today's numbers.
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
    provenance: 'CA SB-54 draft 2027 rates — final Oct 2026',
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
 * mutually-exclusive multiplier: red = 1.2× (escalates 1.6× in 27-28, 2.0× in
 * 28-29), green = a revenue-neutral discount (~0.9×, data-dependent — illustrative).
 * Selector composition: exactly one grade applies, no further stacking today.
 */
export function ukPeprSchedule(): Schedule {
  const RED_2026 = 1.2;
  const GREEN_ILLUSTRATIVE = 0.9; // discount funded by red surcharge; recompute from published table when live
  return {
    id: 'uk-pepr-2026',
    jurisdiction: 'UK',
    materialScope: 'all',
    program: 'UK pEPR (PackUK)',
    currency: 'GBP',
    rateUnit: 'per_tonne',
    effectiveFrom: '2026-04-01',
    citation: 'DEFRA / PackUK — Year 2 (2026-27) illustrative waste-disposal fees + RAM modulation statement.',
    sourceUrl: 'https://www.gov.uk/government/publications/year-2-illustrative-waste-disposal-fees-extended-producer-responsibility-for-packaging/year-2-illustrative-waste-disposal-fees-extended-producer-responsibility-for-packaging',
    provenance: 'UK pEPR 2026-27 illustrative (amber base) — RAM red ×1.2',
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
          label: 'RAM red — not currently recyclable (2026-27 malus)',
          role: 'selector',
          op: { kind: 'multiplier', value: RED_2026 },
          applies: (a) => a.recyclabilityGrade === 'red',
        },
        {
          id: 'ram-green',
          label: 'RAM green — widely recyclable (revenue-neutral discount)',
          role: 'selector',
          op: { kind: 'multiplier', value: GREEN_ILLUSTRATIVE },
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
        help: 'PackUK Recyclability Assessment — amber is the base fee; red pays ×1.2, green earns a discount.',
        options: [
          { value: 'amber', label: 'Amber — base fee' },
          { value: 'green', label: 'Green — widely recyclable' },
          { value: 'red', label: 'Red — not currently recyclable' },
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

/** Register the schedules that have real, encodable tables today. Idempotent. */
export function registerBuiltinSchedules(): void {
  registerSchedule(caSb54Schedule());
  registerSchedule(ukPeprSchedule());
  registerSchedule(jpJcpraSchedule());
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
 * Which jurisdiction's schedule prices a given studio market. US state codes have
 * no OWN published producer-fee table (CA SB 54 is the only detailed US schedule),
 * so they price on the flagship — the same approximation the studio already makes,
 * now explicit and per-market. Non-US markets (a country/province code) resolve to
 * their own schedule once registered; until then they, too, fall back.
 *
 *   scheduleForMarket('CA')  → US-CA flagship (California-the-state, priced on SB 54)
 *   scheduleForMarket('OR')  → US-CA flagship (Oregon has no published fee table)
 *   scheduleForMarket('UK')  → uk-pepr-2026 (once markets include the UK)
 *   scheduleForMarket('FR')  → FR schedule when registered, else flagship
 */
export function scheduleForMarket(market: string, scope = 'all'): Schedule | undefined {
  const direct = getSchedule(market, scope);
  if (direct) return direct;
  // US two-letter state codes (and anything without its own table) → flagship.
  return getSchedule(FLAGSHIP_SCHEDULE_JURISDICTION);
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
