// Swap Studio — the material cost curve.
// Persona: Theo Marchetti, "The Material Choice" (design 45 / business 35 / dev 20).
//
// Every other entry on the board checks compliance AFTER the package exists. This one
// serves the moment BEFORE it exists — the material-choice decision — by pricing every
// swap. Two grounded layers, honestly separated:
//
//   1. WHAT APPLIES (live)  — GET /compliance/pathways?state=XX / ?region=EU, public/free.
//      The real enacted-law obligations, PROs to join, and deadlines per market, matched
//      to the materials in your spec.
//   2. WHAT A SWAP COSTS (published) — the California SB 54 (2027) producer fee schedule
//      from Circular Action Alliance, Ch.9 Table 5. Per-material eco-modulation rates in
//      ¢/lb -> $/tonne. This is the same grounded anchor the SignalScout API itself uses
//      (app/scoring/ca_sb54_fees.py); it is published-with-citation reference data, not an
//      LLM guess. CA is the only US program with per-material rates published in enough
//      detail to price a redesign, so we price the swap in CA terms and flag it as such.
//
// Zero npm dependencies — Node 18+ (built-in http + global fetch).

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 4820);
const API_BASE = (process.env.SIGNALSCOUT_API_BASE_URL ||
  'https://signalscout-api-36712717703.us-central1.run.app').replace(/\/$/, '');

// ---------------------------------------------------------------------------
// Grounded reference data (ported verbatim from app/scoring/ca_sb54_fees.py +
// app/scoring/materials.py so the demo prices swaps with the exact same numbers
// and citation the production API uses).
// ---------------------------------------------------------------------------
const LB_PER_TONNE = 2204.62;
const centsLbToPerTonne = (c) => Math.round((c / 100) * LB_PER_TONNE);

const PLASTIC_ADDER = 21.0; // ¢/lb — PPMF (17) + Reuse (4). Plastic CMCs only.

const SCHEDULE_CITATION =
  'Circular Action Alliance — California SB 54 EPR Program Plan, Ch. 9 Table 5, ' +
  '2027 EPR Base Fee Schedule (draft; final October 2026).';
const SCHEDULE_SOURCE_URL = 'https://circularactionalliance.org/';

// canonical material category -> the low/high published formats that bound its
// eco-modulation spread (the redesign headroom, quantified).
const SPREAD = {
  plastic_packaging: { best: 29, worst: 98, plastic: true },
  plastic_film:      { best: 13, worst: 49, plastic: true },
  paper_packaging:   { best: 2,  worst: 27, plastic: false },
  glass_packaging:   { best: 1,  worst: 23, plastic: false },
  aluminum_packaging:{ best: 5,  worst: 14, plastic: false },
};

// The designer's palette. Each option is a real published named format from Table 5,
// so its ¢/lb is grounded, not interpolated. `default_g` = a plausible per-unit weight.
// `recyclable` drives the eco-modulation copy (low-end formats earn passive bonuses;
// PCR content and source reduction earn further active bonuses on top).
const PALETTE = [
  // plastics
  { id: 'pet_clear',  label: 'PET / HDPE bottle — clear or natural',   category: 'plastic_packaging', cents: 29, default_g: 22, recyclable: true,  tag: 'best-in-class plastic' },
  { id: 'plastic_rep',label: 'Rigid plastic — mixed / pigmented',      category: 'plastic_packaging', cents: 33, default_g: 22, recyclable: true,  tag: 'representative' },
  { id: 'pp_ps',      label: 'PP bottle / PS foam — hard to recycle',  category: 'plastic_packaging', cents: 98, default_g: 22, recyclable: false, tag: 'worst-in-class plastic' },
  // film
  { id: 'pe_pouch',   label: 'Mono-material PE pouch',                 category: 'plastic_film',      cents: 13, default_g: 6,  recyclable: true,  tag: 'best-in-class film' },
  { id: 'laminate',   label: 'Multi-material laminate pouch',          category: 'plastic_film',      cents: 49, default_g: 6,  recyclable: false, tag: 'worst-in-class film' },
  // fiber / paper
  { id: 'corrugated', label: 'Corrugated cardboard — uncoated',        category: 'paper_packaging',   cents: 2,  default_g: 30, recyclable: true,  tag: 'best-in-class fiber' },
  { id: 'paperboard', label: 'Paperboard sleeve / carton',            category: 'paper_packaging',   cents: 5,  default_g: 12, recyclable: true,  tag: 'representative' },
  { id: 'poly_carton',label: 'Plastic-coated / laminate carton',      category: 'paper_packaging',   cents: 27, default_g: 30, recyclable: false, tag: 'worst-in-class fiber' },
  // glass
  { id: 'glass',      label: 'Glass bottle / jar',                     category: 'glass_packaging',   cents: 1,  default_g: 180, recyclable: true, tag: 'lowest-fee covered material' },
  { id: 'glass_small',label: 'Glass — small / non-standard form',      category: 'glass_packaging',   cents: 23, default_g: 60, recyclable: false, tag: 'worst-in-class glass' },
  // metal
  { id: 'steel',      label: 'Steel / tin container',                  category: 'aluminum_packaging',cents: 5,  default_g: 25, recyclable: true,  tag: 'best-in-class metal' },
  { id: 'aluminum',   label: 'Aluminum can / container',               category: 'aluminum_packaging',cents: 11, default_g: 14, recyclable: true,  tag: 'representative' },
  { id: 'foil',       label: 'Aluminum foil / aerosol',                category: 'aluminum_packaging',cents: 14, default_g: 8,  recyclable: false, tag: 'worst-in-class metal' },
];
const PALETTE_BY_ID = Object.fromEntries(PALETTE.map((m) => [m.id, m]));

const CATEGORY_LABEL = {
  plastic_packaging: 'Rigid plastic',
  plastic_film: 'Plastic film',
  paper_packaging: 'Paper / fiber',
  glass_packaging: 'Glass',
  aluminum_packaging: 'Metal',
};

// action_type values that mean "you must DO something" vs. just watch. `has_fee` in the
// pathways feed is currently always false, so it's useless as a signal — the real fee
// number comes from the SB 54 schedule above. Action-required is the honest obligation count.
const ACTION_REQUIRED = new Set([
  'join_pro', 'register_with_state', 'file_individual_plan',
  'report_to_program', 'arrange_collection', 'pay_fee', 'report',
]);

// Alias map from app/scoring/materials.py — normalizes the bill vocabulary that
// /compliance/pathways returns ("glass", "metals", "plastic") to our fee categories.
const CANON = {
  glass: 'glass_packaging', metals: 'aluminum_packaging', metal: 'aluminum_packaging',
  metal_packaging: 'aluminum_packaging', aluminum: 'aluminum_packaging',
  plastic: 'plastic_packaging', paper: 'paper_packaging', fiber: 'paper_packaging',
  paper_products: 'paper_packaging',
};
const canon = (c) => {
  if (!c) return c;
  const k = String(c).trim().toLowerCase();
  return CANON[k] || k;
};

// $/tonne total fee for a published ¢/lb base rate in a given category.
function ratePerTonne(category, baseCents) {
  const adder = SPREAD[category]?.plastic ? PLASTIC_ADDER : 0;
  return centsLbToPerTonne(baseCents + adder);
}
// Per-package fee contribution (US cents) for `grams` of a material at its rate.
function centsPerPackage(ratePerTonneUsd, grams) {
  return (ratePerTonneUsd * grams) / 1e6 * 100; // $/t * t * 100¢
}
function materialFee(mat, grams) {
  const rate = ratePerTonne(mat.category, mat.cents);
  const s = SPREAD[mat.category];
  return {
    rate_per_tonne: rate,
    best_per_tonne: ratePerTonne(mat.category, s.best),
    worst_per_tonne: ratePerTonne(mat.category, s.worst),
    cents_per_package: Math.round(centsPerPackage(rate, grams) * 100) / 100,
  };
}

// ---------------------------------------------------------------------------
// Markets we support: US states with an enacted packaging-EPR program. Deliberately
// US-only — we price every swap in California SB 54 terms (the US flagship schedule),
// which is the wrong basis for EU/PPWR law, and the API's region=EU filter also mixes
// US bills into its response. Pathways are fetched live per state; this list drives the
// chip UI. (state=XX filtering is clean and state-specific.)
// ---------------------------------------------------------------------------
const MARKETS = [
  { code: 'CA', kind: 'state', label: 'California' },
  { code: 'OR', kind: 'state', label: 'Oregon' },
  { code: 'CO', kind: 'state', label: 'Colorado' },
  { code: 'ME', kind: 'state', label: 'Maine' },
  { code: 'MN', kind: 'state', label: 'Minnesota' },
  { code: 'MD', kind: 'state', label: 'Maryland' },
  { code: 'WA', kind: 'state', label: 'Washington' },
];
const MARKET_BY_CODE = Object.fromEntries(MARKETS.map((m) => [m.code, m]));

// --- tiny live-pathways cache (per market, 10 min) --------------------------
const cache = new Map();
async function pathwaysForMarket(code) {
  const m = MARKET_BY_CODE[code];
  if (!m) return [];
  const hit = cache.get(code);
  if (hit && Date.now() - hit.t < 10 * 60 * 1000) return hit.v;
  const qs = m.kind === 'region' ? `region=${m.code}` : `state=${m.code}`;
  const url = `${API_BASE}/compliance/pathways?${qs}`;
  let v = [];
  try {
    const r = await fetch(url, { headers: { accept: 'application/json' } });
    if (r.ok) v = await r.json();
  } catch (e) {
    console.error(`pathways ${code} failed:`, e.message);
  }
  cache.set(code, { t: Date.now(), v });
  return v;
}

// ---------------------------------------------------------------------------
// The quote engine — the real product. Given a spec (components + markets),
// price every component, build the eco-modulation cost curve, and attach the
// live obligations each material triggers in each market.
// ---------------------------------------------------------------------------
async function buildQuote(spec) {
  const markets = (spec.markets || []).filter((c) => MARKET_BY_CODE[c]);
  const components = (spec.components || [])
    .map((c) => {
      const mat = PALETTE_BY_ID[c.material];
      if (!mat) return null;
      const grams = Number(c.grams) > 0 ? Number(c.grams) : mat.default_g;
      return { key: c.key, name: c.name || mat.label, material_id: mat.id, grams, mat };
    })
    .filter(Boolean);

  // Live obligation layer: pull pathways for every selected market, index the
  // enacted laws by the canonical material category they cover.
  const perMarket = await Promise.all(markets.map((c) => pathwaysForMarket(c)));
  const lawsByMarketCategory = {}; // `${code}|${category}` -> [pathway]
  markets.forEach((code, i) => {
    for (const p of perMarket[i]) {
      const cats = new Set((p.material_categories || []).map(canon));
      // A law with no material list, or an ALL/packaging-wide law, applies to any packaging.
      const wildcard = cats.size === 0 || cats.has('all') || cats.has('packaging');
      for (const cat of Object.keys(SPREAD)) {
        if (wildcard || cats.has(cat)) {
          const k = `${code}|${cat}`;
          (lawsByMarketCategory[k] ||= []).push(p);
        }
      }
    }
  });

  // Which canonical categories does this spec actually contain?
  const specCategories = new Set(components.map((c) => c.mat.category));

  // Per-component pricing + the obligations that component's material triggers.
  const componentRows = components.map((c) => {
    const fee = materialFee(c.mat, c.grams);
    // Dedupe pathways by market+bill, split action-required from monitor-only.
    const seen = new Set();
    const actions = [];
    const monitorIds = [];
    for (const code of markets) {
      for (const p of lawsByMarketCategory[`${code}|${c.mat.category}`] || []) {
        const id = `${code}|${p.bill_number}`;
        if (seen.has(id)) continue;
        seen.add(id);
        if (ACTION_REQUIRED.has(p.action_type)) actions.push({ market: code, ...summarizePathway(p) });
        else monitorIds.push(id);
      }
    }
    actions.sort((a, b) =>
      (a.next_deadline_date || '9999').localeCompare(b.next_deadline_date || '9999'));

    // The cost curve: every palette option, priced, ranked cheapest -> dearest, with the
    // delta vs the current choice. Same-family options are flagged (like-for-like redesign).
    const curve = PALETTE.map((alt) => {
      const altRate = ratePerTonne(alt.category, alt.cents);
      return {
        material_id: alt.id,
        label: alt.label,
        category: alt.category,
        category_label: CATEGORY_LABEL[alt.category],
        tag: alt.tag,
        recyclable: alt.recyclable,
        rate_per_tonne: altRate,
        cents_per_package: Math.round(centsPerPackage(altRate, c.grams) * 100) / 100,
        delta_per_tonne: altRate - fee.rate_per_tonne,
        is_current: alt.id === c.mat.id,
        same_family: alt.category === c.mat.category,
      };
    }).sort((a, b) => a.rate_per_tonne - b.rate_per_tonne);

    // Headline swap must be functionally plausible → cheapest option in the SAME family.
    const sameFamilyCheaper = curve.find((x) => x.same_family && !x.is_current && x.rate_per_tonne < fee.rate_per_tonne);
    return {
      key: c.key,
      name: c.name,
      grams: c.grams,
      material_id: c.mat.id,
      material_label: c.mat.label,
      category: c.mat.category,
      category_label: CATEGORY_LABEL[c.mat.category],
      recyclable: c.mat.recyclable,
      ...fee,
      // eco-modulation headroom within the SAME material family (redesign, not re-material)
      eco_mod_swing_per_tonne: fee.worst_per_tonne - fee.best_per_tonne,
      headroom_to_best_per_tonne: fee.rate_per_tonne - fee.best_per_tonne,
      obligation_count: actions.length,
      monitor_count: monitorIds.length,
      monitor_ids: monitorIds,
      obligations: actions,
      cost_curve: curve,
      cheapest_same_family: sameFamilyCheaper || null,
    };
  });

  // Package totals.
  const totalCentsPerPackage = componentRows.reduce((s, r) => s + r.cents_per_package, 0);
  const bestCaseCentsPerPackage = componentRows.reduce(
    (s, r) => s + centsPerPackage(r.best_per_tonne, r.grams), 0);
  const unitsPerYear = Number(spec.unitsPerYear) > 0 ? Number(spec.unitsPerYear) : null;

  // Obligation rollup across the whole spec: distinct action-required laws, PROs, nearest deadline.
  const seenLaw = new Set();
  const seenMonitor = new Set();
  const pros = new Set();
  let nearest = null;
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
    api_base: API_BASE,
    markets: markets.map((c) => MARKET_BY_CODE[c]),
    spec_categories: [...specCategories],
    components: componentRows,
    totals: {
      cents_per_package: Math.round(totalCentsPerPackage * 100) / 100,
      best_case_cents_per_package: Math.round(bestCaseCentsPerPackage * 100) / 100,
      redesign_headroom_cents: Math.round((totalCentsPerPackage - bestCaseCentsPerPackage) * 100) / 100,
      units_per_year: unitsPerYear,
      annual_fee_usd: unitsPerYear ? Math.round((totalCentsPerPackage / 100) * unitsPerYear) : null,
      annual_best_case_usd: unitsPerYear ? Math.round((bestCaseCentsPerPackage / 100) * unitsPerYear) : null,
    },
    obligations: {
      action_law_count: seenLaw.size,
      monitor_count: seenMonitor.size,
      pros: [...pros],
      nearest_deadline: nearest,
    },
    fee_basis: {
      note: 'Fees priced in California SB 54 (2027) terms — the only US program with ' +
        'per-material rates published in enough detail to price a redesign. Obligations ' +
        'above are live across every selected market.',
      citation: SCHEDULE_CITATION,
      source_url: SCHEDULE_SOURCE_URL,
    },
  };
}

function summarizePathway(p) {
  return {
    bill_number: p.bill_number,
    bill_title: p.bill_title,
    action_type: p.action_type,
    action_summary: p.action_summary,
    registration_url: p.registration_url,
    next_deadline_date: p.next_deadline_date,
    entity: p.entity?.name || null,
  };
}

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css' };

function json(res, code, body) {
  const s = JSON.stringify(body);
  res.writeHead(code, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(s) });
  res.end(s);
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  try {
    if (url.pathname === '/api/palette') {
      return json(res, 200, {
        palette: PALETTE.map(({ id, label, category, default_g, recyclable, tag }) => ({
          id, label, category, category_label: CATEGORY_LABEL[category], default_g, recyclable, tag,
        })),
        markets: MARKETS,
        citation: SCHEDULE_CITATION,
        source_url: SCHEDULE_SOURCE_URL,
      });
    }
    if (url.pathname === '/api/quote' && req.method === 'POST') {
      let raw = '';
      for await (const chunk of req) raw += chunk;
      let spec;
      try { spec = JSON.parse(raw || '{}'); }
      catch { return json(res, 400, { error: 'bad JSON' }); }
      return json(res, 200, await buildQuote(spec));
    }
    // static
    let p = url.pathname === '/' ? '/index.html' : url.pathname;
    const file = join(__dirname, 'public', p.replace(/^\/+/, ''));
    if (!file.startsWith(join(__dirname, 'public'))) { res.writeHead(403); return res.end(); }
    const data = await readFile(file);
    res.writeHead(200, { 'content-type': MIME[extname(file)] || 'application/octet-stream' });
    res.end(data);
  } catch (e) {
    if (e.code === 'ENOENT') { res.writeHead(404); return res.end('not found'); }
    console.error(e);
    json(res, 500, { error: e.message });
  }
});

server.listen(PORT, () => {
  console.log(`\n  ◇ Swap Studio  →  http://localhost:${PORT}`);
  console.log(`  API base: ${API_BASE}\n`);
});
