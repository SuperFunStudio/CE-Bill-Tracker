/**
 * Keyword → facet bridge for the Explore search box.
 *
 * The keyword filter matches a bill's title, ai_summary and bill_number; the deep-text layer matches
 * its statute text through an `english` tsvector. Both are English-string paths, so a bill whose law
 * IS about a material can be invisible to the obvious search term:
 *
 *   - Non-English law: China's circular-economy statutes carry material_categories=["textiles", …]
 *     (the classifier read the Chinese text and saw 纺织 / 废旧纺织品), but their titles are Chinese and
 *     their body text can't match an English tsquery. Typing "textiles" found none of them.
 *   - English law with a framework title: "An Act relating to product stewardship" is tagged
 *     `mattresses` without the word appearing in its title or one-sentence summary.
 *
 * The classifier already resolved each bill onto language-independent axes (material_categories,
 * instrument_types, polymers). This module maps what a person types onto those axes, so the keyword
 * box can union in facet matches instead of relying on string overlap alone. It only ever WIDENS a
 * result set — a wrong guess adds bills, it never hides one.
 *
 * Deliberately a static table, not an LLM call: the box filters on every keystroke, and a synonym
 * lookup has to be instant and predictable. Terms resolve on the WHOLE query (normalized), never on a
 * substring, so "battery" bridges but "battery deposit fee in Maine" does not — a multi-word query is
 * a phrase search, and quietly widening it would be surprising.
 *
 * Vocabularies below are the values actually present in bills.material_categories /
 * instrument_types / polymers, including the drifted near-duplicates ("plastics", "packaging",
 * "paper", "hazardous_waste") folded into their canonical category — kept in step with
 * CATEGORY_ALIASES in BillFilters so the keyword path and the dropdown path agree.
 */

export interface FacetMatch {
  /** Values to match against bills.material_categories (OR). */
  materials: string[];
  /** Values to match against bills.instrument_types / instrument_type (OR). */
  instruments: string[];
  /** Resin codes to match against bills.polymers (OR). */
  polymers: string[];
  /** Display labels for the "also matched" notice, e.g. ["Textiles"]. */
  labels: string[];
}

/** Lowercase; hyphens/underscores/punctuation → spaces; collapse runs of whitespace. Applied to both
 *  the table's keys and the incoming query so "e-waste", "E Waste" and "e_waste" all land together. */
function normalize(term: string): string {
  return term
    .toLowerCase()
    .replace(/["'’]/g, '')
    .replace(/[-_/&.,]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

type FacetEntry = { materials?: string[]; instruments?: string[]; polymers?: string[]; label: string };

// One entry per facet value, listing the words a reader would actually type for it. Keys are
// normalized at module load, so entries here may be written naturally (hyphens, mixed case).
// `value` may list several stored values when the classifier's vocabulary drifted (e.g. bills tagged
// "plastics" or "plastic_products" alongside the canonical "plastic_packaging") — mirrors
// CATEGORY_ALIASES in BillFilters so the keyword path and the dropdown path find the same bills.
const MATERIAL_TERMS: { value: string | string[]; label: string; terms: string[] }[] = [
  { value: 'textiles', label: 'Textiles', terms: ['textile', 'textiles', 'waste textiles', 'apparel', 'clothing', 'clothes', 'garment', 'garments', 'fashion', 'footwear', 'shoes'] },
  { value: 'electronics', label: 'Electronics', terms: ['electronics', 'electronic', 'electronic waste', 'e-waste', 'ewaste', 'weee', 'electricals', 'electrical equipment', 'consumer electronics', 'appliances', 'white goods'] },
  { value: ['batteries', 'nickel_cadmium'], label: 'Batteries', terms: ['battery', 'batteries', 'accumulators', 'lithium-ion', 'li-ion', 'ev batteries'] },
  { value: 'nickel_cadmium', label: 'Nickel-cadmium', terms: ['nickel cadmium', 'nicad', 'ni-cd'] },
  { value: ['plastic_packaging', 'plastics', 'plastic_products', 'packaging'], label: 'Plastic packaging', terms: ['plastic', 'plastics', 'plastic packaging', 'single-use plastic', 'single-use plastics'] },
  { value: ['paper_packaging', 'paper', 'packaging'], label: 'Paper packaging', terms: ['paper', 'paper packaging', 'cardboard', 'corrugated', 'fiber', 'fibre', 'cartons'] },
  { value: 'glass', label: 'Glass', terms: ['glass', 'cullet'] },
  { value: 'metals', label: 'Metals', terms: ['metal', 'metals', 'aluminum', 'aluminium', 'steel', 'scrap metal', 'cans', 'ferrous', 'non-ferrous'] },
  { value: 'paint', label: 'Paint', terms: ['paint', 'paints', 'coatings', 'architectural paint'] },
  { value: 'carpet', label: 'Carpet', terms: ['carpet', 'carpets', 'rugs', 'flooring'] },
  { value: 'mattresses', label: 'Mattresses', terms: ['mattress', 'mattresses', 'bedding'] },
  { value: 'tires', label: 'Tires', terms: ['tire', 'tires', 'tyre', 'tyres', 'rubber'] },
  { value: ['pharmaceuticals', 'medical_sharps'], label: 'Pharmaceuticals', terms: ['pharmaceutical', 'pharmaceuticals', 'drugs', 'medicine', 'medicines', 'medication', 'medications'] },
  { value: 'medical_sharps', label: 'Medical sharps', terms: ['sharps', 'medical sharps', 'needles', 'syringes'] },
  { value: 'solar_panels', label: 'Solar panels', terms: ['solar', 'solar panel', 'solar panels', 'photovoltaic', 'photovoltaics', 'pv'] },
  { value: 'organics', label: 'Organics', terms: ['organics', 'organic waste', 'food waste', 'food scraps', 'compost', 'composting', 'biowaste', 'green waste', 'yard waste'] },
  { value: 'biobased', label: 'Bio-based', terms: ['biobased', 'bio-based', 'bioplastic', 'bioplastics', 'compostable', 'biodegradable', 'biomaterial', 'biomaterials'] },
  { value: 'agriculture', label: 'Agriculture', terms: ['agriculture', 'agricultural', 'farming', 'farm', 'soil', 'soil health', 'regenerative agriculture', 'manure', 'crops'] },
  { value: 'water', label: 'Water', terms: ['water', 'wastewater', 'sewage', 'sludge', 'biosolids'] },
  { value: 'biodiversity', label: 'Biodiversity', terms: ['biodiversity', 'ecosystem', 'ecosystems'] },
  { value: ['hazardous_materials', 'hazardous_waste'], label: 'Hazardous materials', terms: ['hazardous', 'hazardous materials', 'hazardous waste', 'hazmat', 'toxic', 'toxics', 'pfas'] },
  { value: 'mercury', label: 'Mercury', terms: ['mercury', 'mercury-added'] },
  { value: 'auto_switches', label: 'Auto switches', terms: ['auto switches', 'mercury switches', 'automotive switches'] },
  { value: 'thermostats', label: 'Thermostats', terms: ['thermostat', 'thermostats'] },
  { value: 'lighting', label: 'Lighting', terms: ['lighting', 'lamps', 'light bulbs', 'bulbs', 'fluorescent', 'fluorescent lamps'] },
  { value: 'pesticides', label: 'Pesticides', terms: ['pesticide', 'pesticides', 'herbicide', 'herbicides'] },
  { value: 'vehicles', label: 'Vehicles', terms: ['vehicle', 'vehicles', 'automotive', 'car', 'cars', 'elv', 'end-of-life vehicles'] },
  { value: 'construction', label: 'Construction', terms: ['construction', 'demolition', 'construction and demolition', 'c&d', 'building materials', 'concrete', 'aggregates'] },
  { value: 'used_oil', label: 'Used oil', terms: ['used oil', 'motor oil', 'lubricants', 'oil filters'] },
  { value: 'furniture', label: 'Furniture', terms: ['furniture', 'furnishings'] },
  { value: 'marine_debris', label: 'Marine debris', terms: ['marine debris', 'marine litter', 'ocean plastic'] },
  { value: 'microplastics', label: 'Microplastics', terms: ['microplastic', 'microplastics'] },
  { value: 'critical_minerals', label: 'Critical minerals', terms: ['critical minerals', 'rare earths', 'rare earth'] },
];

const INSTRUMENT_TERMS: { value: string | string[]; label: string; terms: string[] }[] = [
  { value: 'epr', label: 'EPR', terms: ['epr', 'extended producer responsibility', 'producer responsibility'] },
  // A handful of rows carry the legacy `product_stewardship` value; "stewardship" should find both.
  { value: ['epr', 'product_stewardship'], label: 'EPR / stewardship', terms: ['stewardship', 'product stewardship'] },
  { value: 'deposit_return', label: 'Deposit return', terms: ['deposit', 'deposits', 'deposit return', 'drs', 'bottle bill', 'container deposit', 'redemption', 'refund value'] },
  { value: 'right_to_repair', label: 'Right to repair', terms: ['repair', 'repairs', 'right to repair', 'repairability', 'reparability', 'repairable', 'spare parts'] },
  { value: 'recycled_content', label: 'Recycled content', terms: ['recycled content', 'pcr', 'post-consumer recycled', 'post-consumer resin', 'minimum recycled content'] },
  { value: 'incentives', label: 'Incentives', terms: ['incentive', 'incentives', 'tax credit', 'tax credits', 'grant', 'grants', 'subsidy', 'subsidies', 'rebate', 'rebates', 'funding'] },
  { value: 'labeling', label: 'Labeling', terms: ['label', 'labels', 'labeling', 'labelling'] },
  { value: 'preemption', label: 'Preemption', terms: ['preemption', 'preempt', 'preemptive'] },
  { value: 'disposal_ban', label: 'Disposal ban', terms: ['ban', 'bans', 'disposal ban', 'landfill ban', 'incineration ban'] },
  { value: 'organics_diversion', label: 'Organics diversion', terms: ['organics diversion', 'food waste diversion', 'diversion'] },
  { value: 'waste_shipment', label: 'Waste shipment', terms: ['waste shipment', 'waste shipments', 'transboundary', 'transfrontier', 'basel', 'waste export', 'waste import', 'waste trade', 'scrap export'] },
];

// Resin codes. Bare two-letter codes (PP, PS, PC, PE, PA) are deliberately NOT terms — "PA" reads as
// Pennsylvania far more often than polyamide — so they're reachable by full polymer name instead.
const POLYMER_TERMS: { value: string; label: string; terms: string[] }[] = [
  { value: 'PET', label: 'PET', terms: ['pet', 'polyethylene terephthalate'] },
  { value: 'HDPE', label: 'HDPE', terms: ['hdpe', 'high-density polyethylene'] },
  { value: 'LDPE', label: 'LDPE', terms: ['ldpe', 'low-density polyethylene'] },
  { value: 'PVC', label: 'PVC', terms: ['pvc', 'polyvinyl chloride', 'vinyl'] },
  { value: 'PLA', label: 'PLA', terms: ['pla', 'polylactic acid'] },
  { value: 'ABS', label: 'ABS', terms: ['abs', 'acrylonitrile butadiene styrene'] },
  { value: 'EVA', label: 'EVA', terms: ['eva', 'ethylene-vinyl acetate'] },
  { value: 'PUR', label: 'PUR', terms: ['pur', 'polyurethane'] },
  { value: 'PP', label: 'PP', terms: ['polypropylene'] },
  { value: 'PS', label: 'PS', terms: ['polystyrene', 'styrofoam', 'expanded polystyrene', 'eps'] },
  { value: 'PC', label: 'PC', terms: ['polycarbonate'] },
  { value: 'PE', label: 'PE', terms: ['polyethylene'] },
  { value: 'PA', label: 'PA (nylon)', terms: ['polyamide', 'nylon'] },
];

// term → the facets it resolves to. Built once; a term listed under several facets merges into one
// entry (e.g. "packaging" below, which is meaningless as a single material).
const TERM_INDEX: Map<string, FacetEntry[]> = (() => {
  const index = new Map<string, FacetEntry[]>();
  const add = (term: string, entry: FacetEntry) => {
    const key = normalize(term);
    if (!key) return;
    const existing = index.get(key);
    if (existing) existing.push(entry);
    else index.set(key, [entry]);
  };
  for (const m of MATERIAL_TERMS) {
    const values = Array.isArray(m.value) ? m.value : [m.value];
    for (const t of m.terms) add(t, { materials: values, label: m.label });
  }
  for (const i of INSTRUMENT_TERMS) {
    const values = Array.isArray(i.value) ? i.value : [i.value];
    for (const t of i.terms) add(t, { instruments: values, label: i.label });
  }
  for (const p of POLYMER_TERMS) {
    for (const t of p.terms) add(t, { polymers: [p.value], label: p.label });
  }
  // "packaging" isn't one material — it's the packaging family. Registered last so it merges with
  // nothing above (no single facet owns the word).
  for (const t of ['packaging', 'packaging waste', 'ppp', 'containers and packaging']) {
    add(t, { materials: ['plastic_packaging', 'paper_packaging', 'packaging'], label: 'Packaging' });
  }
  return index;
})();

/**
 * Resolve a typed query to the facets it names, or null when it names none.
 *
 * Matching is exact on the normalized whole query, then on a naive singular/plural of it — enough for
 * "battery"/"batteries" style pairs without the false positives a stemmer would bring ("glass" must
 * not become "glas"). Multi-word queries only match multi-word terms that are listed verbatim.
 */
export function resolveFacetTerm(query: string): FacetMatch | null {
  const q = normalize(query);
  if (q.length < 2) return null;
  const candidates = [q];
  if (q.endsWith('ies')) candidates.push(`${q.slice(0, -3)}y`);      // batteries → battery
  else if (q.endsWith('es')) candidates.push(q.slice(0, -2));         // tyres → tyre (also -s below)
  if (q.endsWith('s')) candidates.push(q.slice(0, -1));              // textiles → textile
  else candidates.push(`${q}s`);                                      // textile → textiles

  const entries = candidates.map(c => TERM_INDEX.get(c)).find(Boolean);
  if (!entries) return null;

  const materials = new Set<string>();
  const instruments = new Set<string>();
  const polymers = new Set<string>();
  const labels: string[] = [];
  for (const e of entries) {
    e.materials?.forEach(v => materials.add(v));
    e.instruments?.forEach(v => instruments.add(v));
    e.polymers?.forEach(v => polymers.add(v));
    if (!labels.includes(e.label)) labels.push(e.label);
  }
  return { materials: [...materials], instruments: [...instruments], polymers: [...polymers], labels };
}

/** Does this bill carry any facet the query resolved to? Mirrors the OR semantics of the facet
 *  dropdowns, and matches the instrument anywhere in the law's set (not just its primary). */
export function billMatchesFacets(
  bill: {
    material_categories?: string[] | null;
    instrument_types?: string[] | null;
    instrument_type?: string | null;
    polymers?: string[] | null;
  },
  facets: FacetMatch,
): boolean {
  if (facets.materials.length) {
    const mats = bill.material_categories ?? [];
    if (facets.materials.some(m => mats.includes(m))) return true;
  }
  if (facets.instruments.length) {
    const insts = bill.instrument_types ?? (bill.instrument_type ? [bill.instrument_type] : []);
    if (facets.instruments.some(i => insts.includes(i))) return true;
  }
  if (facets.polymers.length) {
    const pol = bill.polymers ?? [];
    if (facets.polymers.some(p => pol.includes(p))) return true;
  }
  return false;
}
