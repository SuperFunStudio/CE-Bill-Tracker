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

/** Valid jurisdiction codes → names for a region, including its whole-region sentinel. */
export function jurisdictionsFor(region: string): Record<string, string> {
  if (region === 'EU') return { EU: 'EU-wide', ...EU_MEMBERS };
  return { US: 'Federal', ...STATE_NAMES };
}

export function jurisdictionName(region: string, code: string | null | undefined): string {
  if (!code) return '';
  return jurisdictionsFor(region)[code] ?? code;
}
