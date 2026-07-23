/**
 * Packaging Studio engine — a client-side port of the hackathon Swap Studio
 * quote server (hackathon/swap-studio/server.mjs). Two grounded layers,
 * honestly separated:
 *
 *   1. WHAT APPLIES (live)  — GET /compliance/pathways?state=XX, public/free.
 *      The real enacted-law obligations, PROs to join, and deadlines per market,
 *      matched to the materials in your spec.
 *   2. WHAT A SWAP COSTS (published) — the California SB 54 (2027) producer fee
 *      schedule from Circular Action Alliance, Ch.9 Table 5. Per-material
 *      eco-modulation rates in ¢/lb → $/tonne. Fetched from
 *      GET /compliance/fee-schedule when available, with the published table
 *      bundled as a fallback so the studio always prices.
 *
 * The dashboard is a static export — everything here runs in the browser.
 */
import type { GuardPathway } from './guard';
import {
  resolveRate,
  toRatePerTonne,
  CURRENCY_META,
  type CurrencyCode,
  type Schedule,
  type MaterialFormat,
  type ModulationRule,
  type PackageAttributes,
} from './feeSchedule';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export const LB_PER_TONNE = 2204.62;

/** ¢/lb — PPMF (17) + Reuse Investment (4). Applies to plastic CMCs only. */
export const FALLBACK_PLASTIC_ADDER = 21.0;

export const SCHEDULE_CITATION =
  'Circular Action Alliance — California SB 54 EPR Program Plan, Ch. 9 Table 5, ' +
  '2027 EPR Base Fee Schedule (draft; final October 2026).';
export const SCHEDULE_SOURCE_URL = 'https://circularactionalliance.org/';
/** Short provenance line shown in the UI whether rates are live or bundled. */
export const SCHEDULE_PROVENANCE = 'CA SB-54 draft 2027 rates — final Oct 2026';

/**
 * A canonical coarse material category. Historically the CA studio's fixed five;
 * now a widened string so non-CA schedules can carry their own categories (Japan's
 * `pet_bottle_packaging`, UK's `wood_packaging`/`other_packaging`). The known five
 * keep friendly labels below; anything else is humanized by `categoryLabel`.
 */
export type MaterialCategory = string;

/** Friendly labels for the flagship (CA) categories. */
export const CATEGORY_LABEL: Record<string, string> = {
  plastic_packaging: 'Rigid plastic',
  plastic_film: 'Plastic film',
  paper_packaging: 'Paper / fiber',
  glass_packaging: 'Glass',
  aluminum_packaging: 'Metal',
  pet_bottle_packaging: 'PET bottle',
  wood_packaging: 'Wood',
  other_packaging: 'Other',
};

/** Label for any category — the curated map, else a humanized fallback. */
export function categoryLabel(cat: string): string {
  return (
    CATEGORY_LABEL[cat] ??
    cat.replace(/_packaging$/, '').replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase())
  );
}

const CATEGORIES = Object.keys(CATEGORY_LABEL) as MaterialCategory[];

/** Which fee-schedule role a palette format plays inside its category. */
type PaletteRole = 'best' | 'representative' | 'worst' | 'other';

export interface PaletteOption {
  id: string;
  label: string;
  category: MaterialCategory;
  /** Published base rate, ¢/lb (before the plastic adder). */
  cents: number;
  default_g: number;
  recyclable: boolean;
  tag: string;
  /** Ties the format to the fee-schedule's best/representative/worst fields. */
  role: PaletteRole;
}

/**
 * The designer's palette. Each option is a real published named format from
 * CAA Table 5, so its ¢/lb is grounded, not interpolated. Bundled fallback —
 * when GET /compliance/fee-schedule responds, the per-role rates are refreshed
 * from the live table.
 */
export const FALLBACK_PALETTE: PaletteOption[] = [
  // plastics
  { id: 'pet_clear',   label: 'PET / HDPE bottle — clear or natural',  category: 'plastic_packaging',  cents: 29, default_g: 22,  recyclable: true,  tag: 'best-in-class plastic',        role: 'best' },
  { id: 'plastic_rep', label: 'Rigid plastic — mixed / pigmented',     category: 'plastic_packaging',  cents: 33, default_g: 22,  recyclable: true,  tag: 'representative',               role: 'representative' },
  { id: 'pp_ps',       label: 'PP bottle / PS foam — hard to recycle', category: 'plastic_packaging',  cents: 98, default_g: 22,  recyclable: false, tag: 'worst-in-class plastic',       role: 'worst' },
  // film
  { id: 'pe_pouch',    label: 'Mono-material PE pouch',                category: 'plastic_film',       cents: 13, default_g: 6,   recyclable: true,  tag: 'best-in-class film',           role: 'best' },
  { id: 'laminate',    label: 'Multi-material laminate pouch',         category: 'plastic_film',       cents: 49, default_g: 6,   recyclable: false, tag: 'worst-in-class film',          role: 'worst' },
  // fiber / paper
  { id: 'corrugated',  label: 'Corrugated cardboard — uncoated',       category: 'paper_packaging',    cents: 2,  default_g: 30,  recyclable: true,  tag: 'best-in-class fiber',          role: 'best' },
  { id: 'paperboard',  label: 'Paperboard sleeve / carton',            category: 'paper_packaging',    cents: 5,  default_g: 12,  recyclable: true,  tag: 'representative',               role: 'representative' },
  { id: 'poly_carton', label: 'Plastic-coated / laminate carton',      category: 'paper_packaging',    cents: 27, default_g: 30,  recyclable: false, tag: 'worst-in-class fiber',         role: 'worst' },
  // glass
  { id: 'glass',       label: 'Glass bottle / jar',                    category: 'glass_packaging',    cents: 1,  default_g: 180, recyclable: true,  tag: 'lowest-fee covered material',  role: 'best' },
  { id: 'glass_small', label: 'Glass — small / non-standard form',     category: 'glass_packaging',    cents: 23, default_g: 60,  recyclable: false, tag: 'worst-in-class glass',         role: 'worst' },
  // metal
  { id: 'steel',       label: 'Steel / tin container',                 category: 'aluminum_packaging', cents: 5,  default_g: 25,  recyclable: true,  tag: 'best-in-class metal',          role: 'best' },
  { id: 'aluminum',    label: 'Aluminum can / container',              category: 'aluminum_packaging', cents: 11, default_g: 14,  recyclable: true,  tag: 'representative',               role: 'representative' },
  { id: 'foil',        label: 'Aluminum foil / aerosol',               category: 'aluminum_packaging', cents: 14, default_g: 8,   recyclable: false, tag: 'worst-in-class metal',         role: 'worst' },
];

/** Per-category low/high published formats bounding the eco-modulation spread (¢/lb base),
 *  plus the adder (PPMF + Reuse Investment) that plastic CMCs pay on top. */
export interface CategorySpread {
  best: number;
  worst: number;
  /** ¢/lb added to every format in the category (non-zero only for plastics). */
  adderCents: number;
}

const FALLBACK_SPREAD: Record<MaterialCategory, CategorySpread> = {
  plastic_packaging:  { best: 29, worst: 98, adderCents: FALLBACK_PLASTIC_ADDER },
  plastic_film:       { best: 13, worst: 49, adderCents: FALLBACK_PLASTIC_ADDER },
  paper_packaging:    { best: 2,  worst: 27, adderCents: 0 },
  glass_packaging:    { best: 1,  worst: 23, adderCents: 0 },
  aluminum_packaging: { best: 5,  worst: 14, adderCents: 0 },
};

// ---------------------------------------------------------------------------
// Fee schedule — live endpoint with bundled fallback
// ---------------------------------------------------------------------------

/**
 * GET /compliance/fee-schedule response (app/api/compliance.py, built from
 * app/scoring/ca_sb54_fees.py). One entry per coarse material category with
 * best / representative / worst rate tiers in published ¢/lb; the plastic
 * adder is exposed per rate (base + adder = total) rather than baked in.
 */
export interface FeeScheduleRate {
  tier: 'best' | 'representative' | 'worst';
  format_name: string | null;
  base_cents_per_lb: number;
  plastic_adder_cents_per_lb: number;
  total_cents_per_lb: number;
  usd_per_tonne: number;
  usd_per_tonne_high: number | null;
}
export interface FeeScheduleCategory {
  material_category: string;
  aliases: string[];
  includes_plastic_adder: boolean;
  note?: string | null;
  rates: FeeScheduleRate[];
}
export interface FeeScheduleResponse {
  program?: string;
  basis?: string;
  source_url?: string;
  rates_final_expected?: string;
  lb_per_tonne?: number;
  high_scenario_multiplier?: number;
  categories: FeeScheduleCategory[];
}

/** Normalized schedule the quote engine prices against. */
export interface FeeSchedule {
  /** 'live' = endpoint responded; 'fallback' = bundled draft table in use. */
  source: 'live' | 'fallback';
  palette: PaletteOption[];
  spread: Record<MaterialCategory, CategorySpread>;
  citation: string;
  sourceUrl: string;
  /**
   * The generalized pricing schedule (feeSchedule.ts) this table maps onto — the
   * single source of rate truth. The plastic adder that used to live in
   * spread.adderCents is expressed here as a modulation rule, so unmodulated CA
   * pricing is unchanged while per-component `attrs` flow through the same engine.
   * Rebuilt whenever palette/spread change (live fetch or bundled fallback).
   */
  engine: Schedule;
}

export const FALLBACK_SCHEDULE: FeeSchedule = {
  source: 'fallback',
  palette: FALLBACK_PALETTE,
  spread: FALLBACK_SPREAD,
  citation: SCHEDULE_CITATION,
  sourceUrl: SCHEDULE_SOURCE_URL,
  engine: buildEngineSchedule(FALLBACK_PALETTE, FALLBACK_SPREAD, SCHEDULE_CITATION, SCHEDULE_SOURCE_URL),
};

/**
 * Map the studio's palette/spread onto a generalized feeSchedule.ts `Schedule`.
 * Every palette format becomes a base-rate `MaterialFormat` (¢/lb native); each
 * category's `adderCents` (the CA plastic PPMF+reuse adder) becomes an
 * `add_per_tonne` modulation rule. Composition is 'stack' — for CA the only rule
 * is the adder, so resolveRate(base) reproduces the old base+adder exactly.
 */
function buildEngineSchedule(
  palette: PaletteOption[],
  spread: Record<MaterialCategory, CategorySpread>,
  citation: string,
  sourceUrl: string,
): Schedule {
  const formats: MaterialFormat[] = palette.map((p) => ({
    id: p.id,
    label: p.label,
    category: p.category,
    baseRateNative: p.cents,
    tier: p.role === 'other' ? 'representative' : p.role,
    recyclable: p.recyclable,
    tag: p.tag,
  }));

  const rules: ModulationRule[] = [];
  for (const cat of CATEGORIES) {
    const adderCents = spread[cat]?.adderCents ?? 0;
    if (adderCents > 0) {
      rules.push({
        id: `adder-${cat}`,
        label: 'PPMF + Reuse Investment adder',
        role: 'malus',
        op: { kind: 'add_per_tonne', value: toRatePerTonne(adderCents, 'cents_per_lb') },
        applies: (_a, ctx) => ctx.category === cat,
      });
    }
  }

  return {
    id: 'ca-sb54-live',
    jurisdiction: 'US-CA',
    materialScope: 'all',
    program: 'CA SB-54',
    currency: 'USD',
    rateUnit: 'cents_per_lb',
    citation,
    sourceUrl,
    provenance: SCHEDULE_PROVENANCE,
    formats,
    modulation: { rules, policy: { compose: 'stack' } },
  };
}

/**
 * Rate for a category + native ¢/lb base under a schedule's engine, optionally
 * modulated by a component's design attributes. Rounded to whole $/tonne to match
 * the legacy ¢/lb→$/tonne integer rounding (keeps CA figures byte-identical).
 */
function engineRateFor(
  engine: Schedule,
  category: MaterialCategory,
  baseCents: number,
  attrs?: PackageAttributes,
): number {
  const fmt: MaterialFormat = { id: '_adhoc', label: '', category, baseRateNative: baseCents, tier: 'representative' };
  return Math.round(resolveRate(engine, fmt, attrs).ratePerTonne);
}

/** Thin normalizer: live per-category rate tiers → palette rates + spread bounds. */
export function normalizeFeeSchedule(data: FeeScheduleResponse): FeeSchedule {
  if (!Array.isArray(data?.categories) || data.categories.length === 0) {
    throw new Error('fee-schedule: missing categories');
  }
  const byCategory = new Map(data.categories.map((c) => [c.material_category, c]));
  const tierRate = (cat: FeeScheduleCategory | undefined, tier: FeeScheduleRate['tier']) => {
    const r = cat?.rates?.find((x) => x.tier === tier);
    return r ? Number(r.base_cents_per_lb) : NaN;
  };

  const spread: Record<MaterialCategory, CategorySpread> = { ...FALLBACK_SPREAD };
  for (const cat of CATEGORIES) {
    const row = byCategory.get(cat);
    if (!row) continue; // keep the bundled bounds for any category the endpoint omits
    const best = tierRate(row, 'best');
    const worst = tierRate(row, 'worst');
    if (!Number.isFinite(best) || !Number.isFinite(worst)) throw new Error(`fee-schedule: bad rates for ${cat}`);
    // The adder is uniform within a category (0 for non-plastics) — read it off any tier.
    const adder = Number(row.rates.find((x) => Number.isFinite(x.plastic_adder_cents_per_lb))?.plastic_adder_cents_per_lb);
    spread[cat] = { best, worst, adderCents: Number.isFinite(adder) ? adder : spread[cat].adderCents };
  }

  // Refresh each palette format's base rate from the live table via its role.
  const palette = FALLBACK_PALETTE.map((opt) => {
    if (opt.role === 'other') return opt; // no live tier to refresh from
    const row = byCategory.get(opt.category);
    if (!row) return opt;
    const cents = tierRate(row, opt.role);
    return Number.isFinite(cents) ? { ...opt, cents } : opt;
  });

  const citation = data.basis || SCHEDULE_CITATION;
  const sourceUrl = data.source_url || SCHEDULE_SOURCE_URL;
  return {
    source: 'live',
    palette,
    spread,
    citation,
    sourceUrl,
    engine: buildEngineSchedule(palette, spread, citation, sourceUrl),
  };
}

/**
 * Fetch the live fee schedule; fall back to the bundled draft table when the
 * endpoint 404s, errors, or returns an unexpected shape. Callers surface the
 * `source: 'fallback'` flag as a "using bundled draft rates" note.
 */
export async function fetchFeeSchedule(): Promise<FeeSchedule> {
  try {
    const res = await fetch(`${API_BASE}/compliance/fee-schedule`, {
      headers: { accept: 'application/json' },
    });
    if (!res.ok) return FALLBACK_SCHEDULE;
    return normalizeFeeSchedule((await res.json()) as FeeScheduleResponse);
  } catch {
    return FALLBACK_SCHEDULE;
  }
}

/** Starting weight (g) by category when a format doesn't specify its own. */
const CATEGORY_DEFAULT_G: Record<string, number> = {
  glass_packaging: 150,
  pet_bottle_packaging: 20,
  plastic_packaging: 10,
  plastic_film: 6,
  paper_packaging: 15,
  aluminum_packaging: 16,
  wood_packaging: 50,
  other_packaging: 10,
};

const TIER_TO_ROLE: Record<MaterialFormat['tier'], PaletteRole> = {
  best: 'best',
  worst: 'worst',
  representative: 'representative',
  band: 'representative',
  single: 'representative',
};

/**
 * Reverse adapter: build the studio's UI-shaped `FeeSchedule` (palette + per-category
 * best/worst spread) from a registered engine `Schedule` (feeSchedule.ts). Lets a
 * non-CA jurisdiction (Japan, UK, …) drive the exact same studio UI + quote engine.
 * The `engine` is carried through verbatim, so pricing (incl. modulation) stays
 * authoritative; `spread` bounds are derived from the formats present in each category.
 */
export function feeScheduleFromSchedule(schedule: Schedule): FeeSchedule {
  const palette: PaletteOption[] = schedule.formats.map((f) => ({
    id: f.id,
    label: f.label,
    category: f.category,
    cents: f.baseRateNative,
    default_g: f.default_g ?? CATEGORY_DEFAULT_G[f.category] ?? 10,
    recyclable: f.recyclable ?? false,
    tag: f.tag ?? '',
    role: TIER_TO_ROLE[f.tier],
  }));

  const spread: Record<MaterialCategory, CategorySpread> = {};
  for (const f of schedule.formats) {
    const cur = spread[f.category];
    if (!cur) spread[f.category] = { best: f.baseRateNative, worst: f.baseRateNative, adderCents: 0 };
    else {
      cur.best = Math.min(cur.best, f.baseRateNative);
      cur.worst = Math.max(cur.worst, f.baseRateNative);
    }
  }

  return {
    source: 'live',
    palette,
    spread,
    citation: schedule.citation,
    sourceUrl: schedule.sourceUrl,
    engine: schedule, // pricing authority — modulation rules travel with it
  };
}

/**
 * Remap a spec's components onto a different schedule's palette when the active
 * schedule changes, so switching jurisdictions preserves the package structure. A
 * material id that still exists is kept; otherwise the component snaps to the same
 * category's representative format in the target palette (or the first, as a floor).
 * Weights are preserved.
 */
export function remapComponentsToSchedule(
  components: SpecComponent[],
  fromPalette: PaletteOption[],
  toPalette: PaletteOption[],
): SpecComponent[] {
  if (!toPalette.length) return components;
  const fromById = new Map(fromPalette.map((p) => [p.id, p]));
  const toIds = new Set(toPalette.map((p) => p.id));
  const byCat = new Map<MaterialCategory, PaletteOption[]>();
  for (const p of toPalette) {
    const list = byCat.get(p.category);
    if (list) list.push(p);
    else byCat.set(p.category, [p]);
  }
  const pick = (cat: MaterialCategory | undefined): PaletteOption => {
    const list = cat ? byCat.get(cat) : undefined;
    if (list?.length) return list.find((o) => o.role === 'representative') ?? list[0];
    return toPalette[0];
  };
  return components.map((c) => {
    if (toIds.has(c.material)) return c; // still valid in the target schedule
    const target = pick(fromById.get(c.material)?.category);
    return { ...c, material: target.id };
  });
}

// ---------------------------------------------------------------------------
// Currency-aware display formatting — one Fmt per active schedule currency.
// ---------------------------------------------------------------------------

/** Display formatters bound to a currency. Replaces the old $-hardcoded helpers so
 *  the studio can render ¥ / £ / € prices when a non-USD schedule is active. */
export interface Fmt {
  currency: CurrencyCode;
  symbol: string;
  /** A minor-unit amount (¢ / p / whole ¥) → e.g. "$1.20" or "42.00¢" or "¥0.65". */
  money: (minorUnits: number) => string;
  /** A per-tonne major-unit rate → e.g. "$1,102/t", "¥64,800/t". */
  rate: (perTonne: number) => string;
  /** A major-unit amount (annual fee) → e.g. "$24,200", "¥1,296,000". */
  amount: (major: number) => string;
  /** Compact major-unit amount → e.g. "$24k". */
  compact: (major: number) => string;
}

export function makeFmt(currency: CurrencyCode): Fmt {
  const { symbol, minorPerMajor, minorSuffix } = CURRENCY_META[currency];
  const amount = (n: number) => `${symbol}${Math.round(n).toLocaleString()}`;
  return {
    currency,
    symbol,
    money: (m: number) =>
      minorPerMajor === 1
        ? `${symbol}${m.toFixed(2)}`
        : m >= minorPerMajor
          ? `${symbol}${(m / minorPerMajor).toFixed(2)}`
          : `${m.toFixed(2)}${minorSuffix}`,
    rate: (v: number) => `${symbol}${Math.round(v).toLocaleString()}/t`,
    amount,
    compact: (n: number) => (n >= 10000 ? `${symbol}${Math.round(n / 1000).toLocaleString()}k` : amount(n)),
  };
}

// ---------------------------------------------------------------------------
// Fee math (¢/lb → $/tonne → ¢/package)
// ---------------------------------------------------------------------------

/** $/tonne total fee for a published ¢/lb base rate in a given category, priced
 *  through the schedule's engine (plastic categories include the PPMF + Reuse
 *  Investment adder as a modulation rule — a producer pays the total). Unmodulated:
 *  the design-attribute levers are applied only where a component's actual fee is
 *  computed (materialFee), so this stays the family's representative rate. */
export function ratePerTonne(schedule: FeeSchedule, category: MaterialCategory, baseCents: number): number {
  return engineRateFor(schedule.engine, category, baseCents);
}

/** Per-package fee contribution in the schedule's MINOR currency unit (US cents by
 *  default) for `grams` of material at a per-tonne rate. `minorPerMajor` is 100 for
 *  $/€/£ and 1 for ¥/₩ — so a JPY package fee comes back in whole yen, not "sen". */
export function centsPerPackage(ratePerTonne: number, grams: number, minorPerMajor = 100): number {
  return ((ratePerTonne * grams) / 1e6) * minorPerMajor; // major/t * t * minorPerMajor
}

/** Minor-currency-unit divisor for a schedule (100 for $/€/£, 1 for ¥/₩). */
function minorPerMajorOf(schedule: FeeSchedule): number {
  return CURRENCY_META[schedule.engine.currency]?.minorPerMajor ?? 100;
}

function materialFee(schedule: FeeSchedule, mat: PaletteOption, grams: number, attrs?: PackageAttributes) {
  // The component's actual fee is modulated by its design attributes; the best/worst
  // family bounds stay unmodulated (they describe the material-selection spread).
  const rate = engineRateFor(schedule.engine, mat.category, mat.cents, attrs);
  const s = schedule.spread[mat.category];
  const minor = minorPerMajorOf(schedule);
  return {
    rate_per_tonne: rate,
    best_per_tonne: ratePerTonne(schedule, mat.category, s.best),
    worst_per_tonne: ratePerTonne(schedule, mat.category, s.worst),
    cents_per_package: Math.round(centsPerPackage(rate, grams, minor) * 100) / 100,
  };
}

// ---------------------------------------------------------------------------
// Markets + material canonicalization
// ---------------------------------------------------------------------------

/**
 * Markets we support: US states with an enacted packaging-EPR program.
 * Deliberately US-only — we price every swap in California SB 54 terms (the US
 * flagship schedule), which is the wrong basis for EU/PPWR law, and the API's
 * region=EU filter also mixes US bills into its response. (state=XX filtering
 * is clean and state-specific.)
 */
export interface Market {
  code: string;
  kind: 'state';
  label: string;
}

export const MARKETS: Market[] = [
  { code: 'CA', kind: 'state', label: 'California' },
  { code: 'OR', kind: 'state', label: 'Oregon' },
  { code: 'CO', kind: 'state', label: 'Colorado' },
  { code: 'ME', kind: 'state', label: 'Maine' },
  { code: 'MN', kind: 'state', label: 'Minnesota' },
  { code: 'MD', kind: 'state', label: 'Maryland' },
  { code: 'WA', kind: 'state', label: 'Washington' },
];
export const MARKET_BY_CODE: Record<string, Market> = Object.fromEntries(MARKETS.map((m) => [m.code, m]));

/**
 * Alias map from app/scoring/materials.py — normalizes the bill vocabulary that
 * /compliance/pathways returns ("glass", "metals", "plastic") to our fee categories.
 */
const CANON: Record<string, string> = {
  glass: 'glass_packaging',
  metals: 'aluminum_packaging',
  metal: 'aluminum_packaging',
  metal_packaging: 'aluminum_packaging',
  aluminum: 'aluminum_packaging',
  plastic: 'plastic_packaging',
  paper: 'paper_packaging',
  fiber: 'paper_packaging',
  paper_products: 'paper_packaging',
};

export function canon(c: string | null | undefined): string {
  if (!c) return '';
  const k = String(c).trim().toLowerCase();
  return CANON[k] || k;
}

/**
 * action_type values that mean "you must DO something" vs. just watch. `has_fee`
 * in the pathways feed is currently always false, so it's useless as a signal —
 * the real fee number comes from the SB 54 schedule. Action-required is the
 * honest obligation count.
 */
export const ACTION_REQUIRED = new Set([
  'join_pro', 'register_with_state', 'file_individual_plan',
  'report_to_program', 'arrange_collection', 'pay_fee', 'report',
]);

// ---------------------------------------------------------------------------
// Live pathways — per-state fan-out with an in-memory cache
// ---------------------------------------------------------------------------

const PATHWAYS_TTL_MS = 10 * 60 * 1000;
const pathwaysCache = new Map<string, { t: number; v: GuardPathway[] }>();

async function pathwaysForMarket(code: string): Promise<GuardPathway[]> {
  if (!MARKET_BY_CODE[code]) return [];
  const hit = pathwaysCache.get(code);
  if (hit && Date.now() - hit.t < PATHWAYS_TTL_MS) return hit.v;
  const res = await fetch(`${API_BASE}/compliance/pathways?state=${encodeURIComponent(code)}`, {
    headers: { accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`pathways ${code}: ${res.status}`);
  const v = (await res.json()) as GuardPathway[];
  pathwaysCache.set(code, { t: Date.now(), v });
  return v;
}

/**
 * Fetch pathways for every selected market in parallel. A failed market resolves
 * to an empty list (Promise.allSettled) so one flaky state never blanks the studio.
 */
export async function fetchPathwaysForMarkets(codes: string[]): Promise<Record<string, GuardPathway[]>> {
  const settled = await Promise.allSettled(codes.map((c) => pathwaysForMarket(c)));
  const out: Record<string, GuardPathway[]> = {};
  codes.forEach((code, i) => {
    const r = settled[i];
    out[code] = r.status === 'fulfilled' ? r.value : [];
  });
  return out;
}

// ---------------------------------------------------------------------------
// The quote engine — the real product. Given a spec (components + markets) and
// the pathways already fetched, price every component, build the eco-modulation
// cost curve, and attach the live obligations each material triggers per market.
// ---------------------------------------------------------------------------

export interface SpecComponent {
  key: string;
  name: string;
  /** Palette option id. */
  material: string;
  grams: number;
  /**
   * Design attributes eco-modulation keys off (PCR %, color, recyclability grade,
   * reuse, disruptors, SUP). Optional — absent means "price at the unmodulated base
   * rate", which is the default for every component until a lever is set. The quote
   * engine feeds these to the selected schedule's modulation rules; schemes with no
   * matching rule (e.g. CA today) simply ignore them, so numbers are unchanged.
   */
  attrs?: PackageAttributes;
  /**
   * The packaging *form* the component is drawn as (bottle, pouch, carton, …). Presentation
   * only — the fee is charged on material + weight, never on shape — so it's optional; when
   * absent the UI infers a default from the material category. See components/studio/PackageForm.
   */
  form?: string;
}

export interface StudioSpec {
  product?: string;
  components: SpecComponent[];
  markets: string[];
  unitsPerYear?: number | null;
  acknowledged?: string[];
  /** Active fee-schedule id ('ca' | 'UK' | 'JP' | …). Persisted so a shared/saved
   *  package reopens under the schedule its component materials belong to. */
  scheduleId?: string;
}

export interface ObligationSummary {
  market: string;
  /** Numeric bill id — links the row to the Bill Explorer detail + watchlist star. */
  bill_id: number;
  bill_number: string;
  bill_title: string;
  action_type: string;
  action_summary: string;
  registration_url: string | null;
  next_deadline_date: string | null;
  entity: string | null;
}

export interface CurvePoint {
  material_id: string;
  label: string;
  category: MaterialCategory;
  category_label: string;
  tag: string;
  recyclable: boolean;
  rate_per_tonne: number;
  cents_per_package: number;
  delta_per_tonne: number;
  is_current: boolean;
  same_family: boolean;
}

export interface QuoteComponent {
  key: string;
  name: string;
  grams: number;
  material_id: string;
  material_label: string;
  category: MaterialCategory;
  category_label: string;
  recyclable: boolean;
  rate_per_tonne: number;
  best_per_tonne: number;
  worst_per_tonne: number;
  cents_per_package: number;
  /** Eco-modulation headroom within the SAME material family (redesign, not re-material). */
  eco_mod_swing_per_tonne: number;
  headroom_to_best_per_tonne: number;
  obligation_count: number;
  monitor_count: number;
  monitor_ids: string[];
  obligations: ObligationSummary[];
  cost_curve: CurvePoint[];
  cheapest_same_family: CurvePoint | null;
}

export interface Quote {
  markets: Market[];
  spec_categories: string[];
  components: QuoteComponent[];
  /** Currency the fees are denominated in (from the active schedule). Drives display
   *  formatting; `cents_per_package` fields are in this currency's minor unit. */
  currency: CurrencyCode;
  totals: {
    cents_per_package: number;
    best_case_cents_per_package: number;
    redesign_headroom_cents: number;
    units_per_year: number | null;
    annual_fee_usd: number | null;
    annual_best_case_usd: number | null;
  };
  obligations: {
    action_law_count: number;
    monitor_count: number;
    pros: string[];
    nearest_deadline: string | null;
  };
}

function summarizePathway(market: string, p: GuardPathway): ObligationSummary {
  return {
    market,
    bill_id: p.bill_id,
    bill_number: p.bill_number ?? '',
    bill_title: p.bill_title ?? '',
    action_type: p.action_type ?? '',
    action_summary: p.action_summary ?? '',
    registration_url: p.registration_url ?? p.entity?.registration_url ?? null,
    next_deadline_date: p.next_deadline_date,
    entity: p.entity?.name ?? null,
  };
}

export function buildQuote(
  spec: StudioSpec,
  pathwaysByMarket: Record<string, GuardPathway[]>,
  schedule: FeeSchedule,
): Quote {
  const paletteById = new Map(schedule.palette.map((m) => [m.id, m]));
  const minor = minorPerMajorOf(schedule); // 100 for $/€/£, 1 for ¥/₩
  const markets = (spec.markets || []).filter((c) => MARKET_BY_CODE[c]);
  const components = (spec.components || [])
    .map((c) => {
      const mat = paletteById.get(c.material);
      if (!mat) return null;
      const grams = Number(c.grams) > 0 ? Number(c.grams) : mat.default_g;
      return { key: c.key, name: c.name || mat.label, grams, mat, attrs: c.attrs };
    })
    .filter(
      (c): c is { key: string; name: string; grams: number; mat: PaletteOption; attrs: PackageAttributes | undefined } =>
        c !== null,
    );

  // Live obligation layer: index the enacted laws in every selected market by
  // the canonical material category they cover.
  const lawsByMarketCategory: Record<string, GuardPathway[]> = {}; // `${code}|${category}` -> [pathway]
  for (const code of markets) {
    for (const p of pathwaysByMarket[code] ?? []) {
      const cats = new Set((p.material_categories || []).map(canon));
      // A law with no material list, or an ALL/packaging-wide law, applies to any packaging.
      const wildcard = cats.size === 0 || cats.has('all') || cats.has('packaging');
      for (const cat of CATEGORIES) {
        if (wildcard || cats.has(cat)) {
          const k = `${code}|${cat}`;
          (lawsByMarketCategory[k] ||= []).push(p);
        }
      }
    }
  }

  // Which canonical categories does this spec actually contain?
  const specCategories = new Set(components.map((c) => c.mat.category));

  // Per-component pricing + the obligations that component's material triggers.
  const componentRows: QuoteComponent[] = components.map((c) => {
    const fee = materialFee(schedule, c.mat, c.grams, c.attrs);
    // Dedupe pathways by market+bill, split action-required from monitor-only.
    const seen = new Set<string>();
    const actions: ObligationSummary[] = [];
    const monitorIds: string[] = [];
    for (const code of markets) {
      for (const p of lawsByMarketCategory[`${code}|${c.mat.category}`] || []) {
        const id = `${code}|${p.bill_number ?? p.bill_id}`;
        if (seen.has(id)) continue;
        seen.add(id);
        if (ACTION_REQUIRED.has(p.action_type ?? '')) actions.push(summarizePathway(code, p));
        else monitorIds.push(id);
      }
    }
    actions.sort((a, b) =>
      (a.next_deadline_date || '9999').localeCompare(b.next_deadline_date || '9999'));

    // The cost curve: every palette option, priced, ranked cheapest → dearest, with
    // the delta vs the current choice. Same-family options are flagged (like-for-like).
    const curve: CurvePoint[] = schedule.palette
      .map((alt) => {
        const altRate = ratePerTonne(schedule, alt.category, alt.cents);
        return {
          material_id: alt.id,
          label: alt.label,
          category: alt.category,
          category_label: categoryLabel(alt.category),
          tag: alt.tag,
          recyclable: alt.recyclable,
          rate_per_tonne: altRate,
          cents_per_package: Math.round(centsPerPackage(altRate, c.grams, minor) * 100) / 100,
          delta_per_tonne: altRate - fee.rate_per_tonne,
          is_current: alt.id === c.mat.id,
          same_family: alt.category === c.mat.category,
        };
      })
      .sort((a, b) => a.rate_per_tonne - b.rate_per_tonne);

    // Headline swap must be functionally plausible → cheapest option in the SAME family.
    const sameFamilyCheaper = curve.find(
      (x) => x.same_family && !x.is_current && x.rate_per_tonne < fee.rate_per_tonne,
    );

    return {
      key: c.key,
      name: c.name,
      grams: c.grams,
      material_id: c.mat.id,
      material_label: c.mat.label,
      category: c.mat.category,
      category_label: categoryLabel(c.mat.category),
      recyclable: c.mat.recyclable,
      ...fee,
      eco_mod_swing_per_tonne: fee.worst_per_tonne - fee.best_per_tonne,
      headroom_to_best_per_tonne: fee.rate_per_tonne - fee.best_per_tonne,
      obligation_count: actions.length,
      monitor_count: monitorIds.length,
      monitor_ids: monitorIds,
      obligations: actions,
      cost_curve: curve,
      cheapest_same_family: sameFamilyCheaper ?? null,
    };
  });

  // Package totals.
  const totalCentsPerPackage = componentRows.reduce((s, r) => s + r.cents_per_package, 0);
  const bestCaseCentsPerPackage = componentRows.reduce(
    (s, r) => s + centsPerPackage(r.best_per_tonne, r.grams, minor), 0);
  const unitsPerYear = Number(spec.unitsPerYear) > 0 ? Number(spec.unitsPerYear) : null;

  // Obligation rollup across the whole spec: distinct action-required laws, PROs, nearest deadline.
  const seenLaw = new Set<string>();
  const seenMonitor = new Set<string>();
  const pros = new Set<string>();
  let nearest: string | null = null;
  for (const row of componentRows) {
    for (const id of row.monitor_ids) seenMonitor.add(id);
    for (const o of row.obligations) {
      const id = `${o.market}|${o.bill_number}`;
      if (seenLaw.has(id)) continue;
      seenLaw.add(id);
      if (o.entity) pros.add(o.entity);
      if (o.next_deadline_date && (!nearest || o.next_deadline_date < nearest))
        nearest = o.next_deadline_date;
    }
  }

  return {
    markets: markets.map((c) => MARKET_BY_CODE[c]),
    spec_categories: [...specCategories],
    components: componentRows,
    currency: schedule.engine.currency,
    totals: {
      cents_per_package: Math.round(totalCentsPerPackage * 100) / 100,
      best_case_cents_per_package: Math.round(bestCaseCentsPerPackage * 100) / 100,
      redesign_headroom_cents: Math.round((totalCentsPerPackage - bestCaseCentsPerPackage) * 100) / 100,
      units_per_year: unitsPerYear,
      // minor units per package → major units per year (÷100 for $/€/£, ÷1 for ¥/₩).
      annual_fee_usd: unitsPerYear ? Math.round((totalCentsPerPackage / minor) * unitsPerYear) : null,
      annual_best_case_usd: unitsPerYear ? Math.round((bestCaseCentsPerPackage / minor) * unitsPerYear) : null,
    },
    obligations: {
      action_law_count: seenLaw.size,
      monitor_count: seenMonitor.size,
      pros: [...pros],
      nearest_deadline: nearest,
    },
  };
}

// ---------------------------------------------------------------------------
// Walkthrough helpers — small pure lenses over the palette/quote for the
// staged Brief → Build → Guard → Studio UI. Additive only; no signature changes.
// ---------------------------------------------------------------------------

export interface PaletteFamily {
  category: MaterialCategory;
  label: string;
  options: PaletteOption[];
}

/** Group the palette into its material families, in first-seen palette order (so a
 *  non-CA schedule's own categories group correctly, not just the flagship five). */
export function groupPaletteByFamily(palette: PaletteOption[]): PaletteFamily[] {
  const byCat = new Map<MaterialCategory, PaletteOption[]>();
  const order: MaterialCategory[] = [];
  for (const m of palette) {
    const list = byCat.get(m.category);
    if (list) list.push(m);
    else {
      byCat.set(m.category, [m]);
      order.push(m.category);
    }
  }
  return order.map((c) => ({
    category: c,
    label: categoryLabel(c),
    options: byCat.get(c)!,
  }));
}

/** The decision-consequence readout for one component: what the current pick
 *  costs vs the cheapest published format in its own family (best-in-family). */
export interface FamilyConsequence {
  /** Cheapest same-family curve point (may be the current pick itself). */
  best: CurvePoint | null;
  /** ¢/package left on the table vs best-in-family (0 when the pick IS the family best). */
  delta_cents_per_package: number;
  /** The same delta annualized at unitsPerYear; null when units are unknown. */
  delta_annual_usd: number | null;
  is_best_in_family: boolean;
}

/** Pure lens over an already-built quote — `cost_curve` is sorted cheapest →
 *  dearest, so the first same-family point is the family's best format. */
export function familyConsequence(
  c: QuoteComponent,
  unitsPerYear?: number | null,
): FamilyConsequence {
  const best = c.cost_curve.find((x) => x.same_family) ?? null;
  const rawDelta = best ? c.cents_per_package - best.cents_per_package : 0;
  const delta = Math.max(0, Math.round(rawDelta * 100) / 100);
  const units = Number(unitsPerYear) > 0 ? Number(unitsPerYear) : null;
  return {
    best,
    delta_cents_per_package: delta,
    delta_annual_usd: units ? Math.round((delta / 100) * units) : null,
    is_best_in_family: delta < 0.005,
  };
}

// ---------------------------------------------------------------------------
// Spec ⇄ URL hash — so a studio link reopens the same package
// ---------------------------------------------------------------------------

// A component is encoded as name~material~grams[~attrs] with '~' escaped inside names.
const encPart = (s: string) => encodeURIComponent(s).replace(/~/g, '%7E');

/** Compact, optional attribute token (URI-encoded, so it never contains ~ ! , that
 *  delimit the surrounding format). Omitted entirely when there are no levers set —
 *  keeps legacy 3-part chunks byte-identical, so old share links / saves still parse. */
function encodeAttrs(a?: PackageAttributes): string {
  if (!a) return '';
  const kv: string[] = [];
  if (a.recyclabilityGrade) kv.push(`g:${a.recyclabilityGrade}`);
  if (a.pcrPercent != null) kv.push(`r:${a.pcrPercent}`);
  if (a.color) kv.push(`c:${a.color}`);
  if (a.reusable) kv.push('u:1');
  if (a.hasRecyclingDisruptor) kv.push('d:1');
  if (a.singleUsePlastic) kv.push('s:1');
  return kv.length ? encodeURIComponent(kv.join(',')) : '';
}

function decodeAttrs(raw: string): PackageAttributes | undefined {
  if (!raw) return undefined;
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return undefined;
  }
  const a: PackageAttributes = {};
  for (const tok of decoded.split(',')) {
    const [k, v = ''] = tok.split(':');
    if (k === 'g' && v) a.recyclabilityGrade = v;
    else if (k === 'r') {
      const n = Number(v);
      if (Number.isFinite(n)) a.pcrPercent = n;
    } else if (k === 'c' && (v === 'clear' || v === 'natural' || v === 'colored' || v === 'opaque')) a.color = v;
    else if (k === 'u') a.reusable = true;
    else if (k === 'd') a.hasRecyclingDisruptor = true;
    else if (k === 's') a.singleUsePlastic = true;
  }
  return Object.keys(a).length ? a : undefined;
}

/** Serialize the current spec into a URL hash fragment (no leading '#'). */
export function encodeSpecToHash(spec: StudioSpec): string {
  const sp = new URLSearchParams();
  if (spec.product) sp.set('p', spec.product);
  if (spec.markets.length) sp.set('m', spec.markets.join('.'));
  if (spec.components.length) {
    sp.set(
      'c',
      spec.components
        .map((c) => {
          const parts = [encPart(c.name), c.material, String(c.grams)];
          const a = encodeAttrs(c.attrs);
          if (a) parts.push(a); // only appended when levers are set — legacy chunks stay 3-part
          // Form is a tagged token (`f=…`) so it can follow the untagged attrs slot in any
          // order without a positional collision — old 3/4-part links keep parsing unchanged.
          if (c.form) parts.push(`f=${encodeURIComponent(c.form)}`);
          return parts.join('~');
        })
        .join('!'),
    );
  }
  if (spec.unitsPerYear) sp.set('u', String(spec.unitsPerYear));
  if (spec.acknowledged?.length) sp.set('a', spec.acknowledged.map(encPart).join('!'));
  if (spec.scheduleId && spec.scheduleId !== 'ca') sp.set('s', spec.scheduleId); // 'ca' is the default
  return sp.toString();
}

/** Drop empty/false attribute keys so an unmodulated component stays `attrs: undefined`
 *  (keeps the hash minimal and pristine-detection intact). Returns undefined if nothing set. */
export function pruneAttrs(a: PackageAttributes): PackageAttributes | undefined {
  const out: PackageAttributes = {};
  if (a.recyclabilityGrade) out.recyclabilityGrade = a.recyclabilityGrade;
  if (a.pcrPercent != null && a.pcrPercent > 0) out.pcrPercent = a.pcrPercent;
  if (a.color) out.color = a.color;
  if (a.reusable) out.reusable = true;
  if (a.hasRecyclingDisruptor) out.hasRecyclingDisruptor = true;
  if (a.singleUsePlastic) out.singleUsePlastic = true;
  return Object.keys(out).length ? out : undefined;
}

/** Parse a URL hash fragment back into a spec. Returns null when there's no spec in it. */
export function decodeSpecFromHash(hash: string): StudioSpec | null {
  const raw = hash.replace(/^#/, '');
  if (!raw) return null;
  let sp: URLSearchParams;
  try {
    sp = new URLSearchParams(raw);
  } catch {
    return null;
  }
  if (!sp.has('c') && !sp.has('m')) return null;

  const components: SpecComponent[] = (sp.get('c') || '')
    .split('!')
    .filter(Boolean)
    .map((chunk, i) => {
      const [name = '', material = '', grams = '', ...rest] = chunk.split('~');
      // Optional trailing tokens, order-independent: a `f=…` token is the form; any other
      // (untagged) token is the legacy attrs blob. The encoded attrs blob never starts with
      // `f=` (its keys are g/r/c/u/d/s), so the tag can't collide.
      let attrsRaw = '';
      let formRaw = '';
      for (const part of rest) {
        if (part.startsWith('f=')) formRaw = part.slice(2);
        else if (!attrsRaw) attrsRaw = part;
      }
      return {
        key: `c${i}`,
        name: decodeURIComponent(name),
        material,
        grams: Number(grams) || 0,
        attrs: decodeAttrs(attrsRaw),
        form: formRaw ? decodeURIComponent(formRaw) : undefined,
      };
    })
    .filter((c) => c.material);

  const markets = (sp.get('m') || '').split('.').filter((c) => MARKET_BY_CODE[c]);
  const units = Number(sp.get('u'));
  const acknowledged = (sp.get('a') || '')
    .split('!')
    .filter(Boolean)
    .map((a) => decodeURIComponent(a));

  return {
    product: sp.get('p') || undefined,
    components,
    markets,
    unitsPerYear: Number.isFinite(units) && units > 0 ? units : null,
    acknowledged,
    scheduleId: sp.get('s') || undefined,
  };
}

// ---------------------------------------------------------------------------
// Export for CI — packaging.yaml + the GitHub Actions snippet
// ---------------------------------------------------------------------------

const yamlQuote = (s: string) => `"${s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;

/**
 * Render a packaging.yaml matching spec-sheet-guard's spec format exactly:
 * product / markets / materials / acknowledged. Generated with a template
 * string — no yaml dependency.
 */
export function specToYaml(spec: {
  product: string;
  markets: string[];
  materials: string[];
  acknowledged: string[];
}): string {
  const list = (items: string[], quote: boolean) =>
    items.length
      ? items.map((i) => `  - ${quote ? yamlQuote(i) : i}`).join('\n')
      : null;

  const lines: string[] = [
    '# packaging.yaml — exported from the Atlas Circular Packaging Studio.',
    '# Spec-Sheet Guard checks it against enacted EPR law in every market,',
    '# and fails CI when an obligation is unmet.',
    '',
    `product: ${yamlQuote(spec.product || 'Untitled package')}`,
    '',
    '# Jurisdictions you sell into. US state codes, or region families: EU, FR, JP.',
    'markets:',
    list(spec.markets, false) ?? '  []',
    '',
    '# Atlas Circular material categories your product uses.',
    'materials:',
    list(spec.materials, false) ?? '  []',
    '',
    '# Obligations you\'ve already handled — the guard passes once each is registered',
    '# for real or listed here. Match by entity name/slug, bill number, or "MARKET:BILL".',
  ];
  const acks = list(spec.acknowledged, true);
  lines.push(acks ? 'acknowledged:' : 'acknowledged: []');
  if (acks) lines.push(acks);
  return lines.join('\n') + '\n';
}

/** The one-step CI workflow from spec-sheet-guard's README. */
export const GITHUB_ACTIONS_SNIPPET = `name: EPR Compliance Guard

on:
  pull_request:
    paths:
      - "packaging.yaml"
      - "packaging.yml"
  workflow_dispatch:

jobs:
  epr-guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npx spec-sheet-guard --spec packaging.yaml --github
`;
