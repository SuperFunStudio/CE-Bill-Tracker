// Producer attribution — WHO owes the packaging obligation, per (jurisdiction × regime), with
// article-level citations. Client for GET /compliance/producer-attribution (open, unauthenticated,
// same posture as /pathways). Self-contained on the label.ts pattern: src/lib/api.ts is WIP and
// must not be modified.
//
// The contract that matters most here is the ABSENT row: the API returns no row for a
// (jurisdiction, regime) pair it holds no cited rule for, and callers MUST render that as
// "unknown — verify yourself", never as "not obligated". Silence is not an exemption.

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export type AttributionRegime =
  | 'packaging_epr'
  | 'plastic_tax'
  | 'sup_levy'
  | 'drs'
  | 'carryout_bag';

export type AttributionSourcing = 'domestic_supplier' | 'self_import' | 'own_brand';

export interface ProducerAttributionRow {
  jurisdiction: string;
  jurisdiction_label: string;
  regime: string;
  // The mechanism, not a synonym for "producer" — different rules attach liability to
  // different parties: franchisor | first_seller | brand_owner | packer_filler | importer |
  // supplier_discharged.
  rule: string;
  liable_party: string | null;
  because: string;
  citation: string;
  // Verbatim primary-source text or null — never a paraphrase presented as a quotation.
  quote: string | null;
  // Where the rule lives: statutory | regulatory | guidance | unresolved. A regulation is
  // amended more easily than a statute, and guidance binds nobody.
  confidence: string;
  sourcing_sensitive: boolean;
  covers_food_service_ware: boolean | null;
  threshold_summary: string | null;
  thresholds: Record<string, unknown> | null;
  exemptions: { label?: string; detail?: string; citation?: string }[];
  authorised_representative: Record<string, unknown> | null;
  registration_identifier: Record<string, unknown> | null;
  open_questions: string[];
  source_url: string | null;
  notes: Record<string, string>;
}

export interface AttributionCoverage {
  entries: number;
  regimes: Record<string, string[]>;
  by_confidence: Record<string, number>;
  unresolved_questions: number;
  researched: string;
}

export interface ProducerAttributionResponse {
  rows: ProducerAttributionRow[];
  count: number;
  coverage: AttributionCoverage;
}

export const REGIME_LABELS: Record<AttributionRegime, string> = {
  packaging_epr: 'Packaging EPR',
  plastic_tax: 'Plastic tax',
  sup_levy: 'Single-use plastic levy',
  drs: 'Deposit return',
  carryout_bag: 'Carryout bag',
};

export const SOURCING_LABELS: Record<AttributionSourcing, string> = {
  domestic_supplier: 'I buy from suppliers in the same country',
  self_import: 'I import it myself',
  own_brand: 'It carries my own brand',
};

/** All cited rows for a regime under the given business shape (no jurisdiction filter — the
 * caller narrows locally, which also gives it the honest list of covered jurisdictions). */
export async function fetchProducerAttribution(params: {
  regime: AttributionRegime;
  franchised: boolean;
  sourcing: AttributionSourcing | null;
}): Promise<ProducerAttributionResponse> {
  const url = new URL(`${API}/compliance/producer-attribution`);
  url.searchParams.set('regime', params.regime);
  url.searchParams.set('franchised', String(params.franchised));
  if (params.sourcing) url.searchParams.set('sourcing', params.sourcing);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`API error ${res.status}: producer-attribution`);
  return (await res.json()) as ProducerAttributionResponse;
}
