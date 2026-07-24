// Region + jurisdiction registry (frontend mirror of app/jurisdictions.py). Region-keyed code→name
// lookups so jurisdiction UI/labels work for US states, the EU (EU-wide + member states), and future
// regions — replacing hardcoded US-state assumptions. Keep in sync with the backend registry.
import { STATE_NAMES } from '@/lib/utils';

export const EU_MEMBERS: Record<string, string> = {
  AT: 'Austria', BE: 'Belgium', BG: 'Bulgaria', HR: 'Croatia', CY: 'Cyprus', CZ: 'Czechia',
  DK: 'Denmark', EE: 'Estonia', FI: 'Finland', FR: 'France', DE: 'Germany', GR: 'Greece',
  HU: 'Hungary', IE: 'Ireland', IT: 'Italy', LV: 'Latvia', LT: 'Lithuania', LU: 'Luxembourg',
  MT: 'Malta', NL: 'Netherlands', PL: 'Poland', PT: 'Portugal', RO: 'Romania', SK: 'Slovakia',
  SI: 'Slovenia', ES: 'Spain', SE: 'Sweden',
};

export const REGION_LABELS: Record<string, string> = {
  US: 'United States',
  EU: 'European Union',
};

// Standalone foreign countries we ingest as their own region (region == state == this code); see
// app/ingestion/foreign.py. EU-member countries also arrive this way but resolve their names via
// EU_MEMBERS, so this map holds only the NON-EU codes. Keep in sync with foreign.py's `region` values
// and RegionInsetMap.tsx's CODE_TO_ISO.
export const FOREIGN_COUNTRY_NAMES: Record<string, string> = {
  JP: 'Japan', UK: 'United Kingdom', CL: 'Chile', CH: 'Switzerland', BR: 'Brazil',
  KR: 'South Korea', ZA: 'South Africa', KE: 'Kenya', CN: 'China', CA: 'Canada',
  AU: 'Australia', NO: 'Norway', MX: 'Mexico', IN: 'India',
};

/** Valid jurisdiction codes → names for a region, including its whole-region sentinel. */
export function jurisdictionsFor(region: string): Record<string, string> {
  if (region === 'EU') return { EU: 'EU-wide', ...EU_MEMBERS };
  return { US: 'Federal', ...STATE_NAMES };
}

export function jurisdictionName(region: string, code: string | null | undefined): string {
  if (!code) return '';
  return jurisdictionsFor(region)[code] ?? code;
}

/**
 * Human name for a jurisdiction *leaf* across every family — the (region, code) pair, not `code`
 * alone (state codes collide with country codes, e.g. US "DE" Delaware vs "DE" Germany). Used by the
 * unified /jurisdictions/[region]/[code] profile route.
 */
export function jurisdictionDisplayName(region: string, code: string): string {
  const r = region.toUpperCase();
  const c = code.toUpperCase();
  if (r === 'US') return c === 'US' ? 'Federal' : STATE_NAMES[c] ?? c;
  if (r === 'EU') return c === 'EU' ? 'European Union' : EU_MEMBERS[c] ?? c;
  // Foreign national law: region == country code (== state).
  return EU_MEMBERS[c] ?? FOREIGN_COUNTRY_NAMES[c] ?? c;
}

/** The sub-jurisdiction noun for a region, for copy ("state" / "member state" / "country"). */
export function unitNoun(region: string): string {
  const r = region.toUpperCase();
  if (r === 'US') return 'state';
  if (r === 'EU') return 'member state';
  return 'country';
}

/**
 * Every (region, code) leaf to statically pre-render at /jurisdictions/[region]/[code] (slugs are
 * lowercased). US states under region "us", the EU-wide act view at eu/eu, and one page per foreign
 * country — every EU member code (they arrive as standalone `region==code` national laws) plus the
 * non-EU foreign codes. Zero-bill jurisdictions still get a page (they render the empty state).
 */
export function allJurisdictionParams(): { region: string; code: string }[] {
  const params: { region: string; code: string }[] = [];
  for (const st of Object.keys(STATE_NAMES)) params.push({ region: 'us', code: st.toLowerCase() });
  // US-federal node (state == "US"): the country-level view, ranked among nations on the Standings
  // board. STATE_NAMES holds only the 50 states + DC/PR, so add it explicitly.
  params.push({ region: 'us', code: 'us' });
  params.push({ region: 'eu', code: 'eu' });
  const countries = new Set([...Object.keys(EU_MEMBERS), ...Object.keys(FOREIGN_COUNTRY_NAMES)]);
  for (const c of countries) params.push({ region: c.toLowerCase(), code: c.toLowerCase() });
  return params;
}
