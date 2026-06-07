import { differenceInDays, parseISO, isValid } from 'date-fns';

/** Fix mojibake from UTF-8 encoded as latin-1 */
export function fixEncoding(text: string | null | undefined): string {
  if (!text) return '';
  return text
    .replace('Ã¢â¬\u201c', '\u2014')
    .replace('Ã¢â¬â¢', '\u2019')
    .replace('Ã¢â¬Å', '\u201c')
    .replace('Ã¢â¬\x9d', '\u201d')
    .replace('Ã¢â¬Ë', '\u2018')
    .replace('Ã ', ' ');
}

/** Format a cost number as "$X.Xm" or "$XXXk" */
export function formatCost(n: number | null | undefined): string {
  if (n == null) return 'N/A';
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}m`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}k`;
  return `$${Math.round(n)}`;
}

/** Days until a date string (ISO format). Negative = past. */
export function daysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const d = parseISO(dateStr);
  if (!isValid(d)) return null;
  return differenceInDays(d, new Date());
}

/** Format a date string for display */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  const d = parseISO(dateStr);
  if (!isValid(d)) return dateStr;
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

const STATUS_GREEN = 'bg-green-100 dark:bg-green-900/40 border-green-400 dark:border-green-700/50 text-green-700 dark:text-green-300';
const STATUS_GRAY = 'bg-gray-100 dark:bg-gray-800 border-border-default text-text-muted';
const STATUS_DEFAULT = 'bg-bg-primary border-border-default text-text-secondary';
const STATUS_RED = 'bg-red-100 dark:bg-red-950/50 border-red-400 dark:border-red-700 text-red-700 dark:text-red-300';

/**
 * Visual treatment for a bill's status badge, tinted by policy stance.
 *
 * A "weakens" bill (exempts/narrows/repeals/preempts the policy) is tinted red with a ▼ marker
 * regardless of status, so an enacted *exemption* is unmistakably distinct from an enacted
 * *grant*. "advances" keeps the status color (enacted stays green) and adds a green ▲ marker.
 * Neutral/unknown stance falls back to plain status coloring — preserving enacted=green.
 */
export function statusBadge(
  status: string | null | undefined,
  stance: string | null | undefined,
): { cls: string; marker: string; markerCls: string; label: string } {
  const s = (status ?? '').toLowerCase();
  const statusCls = s === 'enacted'
    ? STATUS_GREEN
    : s === 'failed' || s === 'tabled'
      ? STATUS_GRAY
      : STATUS_DEFAULT;

  switch (stance?.toLowerCase()) {
    case 'weakens':
      return { cls: STATUS_RED, marker: '▼', markerCls: '', label: 'Weakens / exempts this policy' };
    case 'advances':
      return { cls: statusCls, marker: '▲', markerCls: 'text-green-accent', label: 'Advances this policy' };
    default:
      return { cls: statusCls, marker: '', markerCls: '', label: '' };
  }
}

/** Tailwind class for urgency level */
export function urgencyTextClass(urgency: string | null | undefined): string {
  switch (urgency?.toLowerCase()) {
    case 'high': return 'text-urgency-high';
    case 'medium': return 'text-urgency-medium';
    default: return 'text-text-muted';
  }
}

export function urgencyBgClass(urgency: string | null | undefined): string {
  switch (urgency?.toLowerCase()) {
    case 'high': return 'bg-red-100 dark:bg-red-900/40 text-urgency-high border-urgency-high/30';
    case 'medium': return 'bg-amber-100 dark:bg-amber-900/40 text-urgency-medium border-urgency-medium/30';
    default: return 'bg-gray-100 dark:bg-gray-800 text-text-muted border-border-default';
  }
}

/** Tailwind classes for risk level */
export function riskBgClass(risk: string | null | undefined): string {
  switch (risk?.toLowerCase()) {
    case 'high': return 'bg-red-100 dark:bg-red-900/40 text-risk-high border-risk-high/30';
    case 'medium': return 'bg-amber-100 dark:bg-amber-900/40 text-risk-medium border-risk-medium/30';
    case 'low': return 'bg-green-100 dark:bg-green-900/40 text-risk-low border-risk-low/30';
    default: return 'bg-gray-100 dark:bg-gray-800 text-text-muted border-border-default';
  }
}

/** Score color based on 0-100 composite score */
export function scoreColor(score: number): string {
  if (score >= 70) return 'text-urgency-high';
  if (score >= 40) return 'text-urgency-medium';
  return 'text-green-accent';
}

const INSTRUMENT_DISPLAY: Record<string, string> = {
  epr: 'EPR',
  deposit_return: 'Deposit Return',
  recycled_content: 'Recycled Content',
  right_to_repair: 'Right to Repair',
  labeling: 'Labeling',
  preemption: 'Preemption',
  other: 'Other',
};

/** Slugify instrument type for display */
export function formatInstrumentType(t: string | null | undefined): string {
  if (!t) return '—';
  if (t in INSTRUMENT_DISPLAY) return INSTRUMENT_DISPLAY[t];
  return t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export const STATE_NAMES: Record<string, string> = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
  CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', FL: 'Florida', GA: 'Georgia',
  HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa',
  KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland',
  MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri',
  MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey',
  NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio',
  OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina',
  SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont',
  VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming',
  DC: 'District of Columbia',
};

// FIPS numeric code → state abbreviation (used by us-atlas TopoJSON)
export const FIPS_TO_ABBR: Record<string, string> = {
  '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA',
  '08': 'CO', '09': 'CT', '10': 'DE', '11': 'DC', '12': 'FL',
  '13': 'GA', '15': 'HI', '16': 'ID', '17': 'IL', '18': 'IN',
  '19': 'IA', '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME',
  '24': 'MD', '25': 'MA', '26': 'MI', '27': 'MN', '28': 'MS',
  '29': 'MO', '30': 'MT', '31': 'NE', '32': 'NV', '33': 'NH',
  '34': 'NJ', '35': 'NM', '36': 'NY', '37': 'NC', '38': 'ND',
  '39': 'OH', '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI',
  '45': 'SC', '46': 'SD', '47': 'TN', '48': 'TX', '49': 'UT',
  '50': 'VT', '51': 'VA', '53': 'WA', '54': 'WV', '55': 'WI',
  '56': 'WY',
};

/** Download data as a CSV file from the browser */
export function downloadCsv(filename: string, rows: Record<string, unknown>[]): void {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const csv = [
    headers.join(','),
    ...rows.map(row =>
      headers.map(h => {
        const val = row[h];
        const str = val == null ? '' : String(val);
        return str.includes(',') || str.includes('"') || str.includes('\n')
          ? `"${str.replace(/"/g, '""')}"`
          : str;
      }).join(',')
    ),
  ].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
