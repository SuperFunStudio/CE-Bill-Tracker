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
const STATUS_RED = 'bg-red-100 dark:bg-red-900/40 border-red-400 dark:border-red-700/50 text-red-700 dark:text-red-300';

/**
 * A bill "weakens" the circular economy when it exempts/narrows/repeals/preempts a policy rather
 * than establishing one (e.g. OR HB-4030 exempting berry/seafood packaging from EPR). Surfacing
 * that publicly is gated on HUMAN REVIEW, not the AI call alone.
 *
 * We measured the AI's precision on this exact label (scripts/measure_stance_precision.py):
 * ~75% — roughly 1 in 4 auto-"weakens" calls is wrong, and the errors cluster in the worst
 * category, branding EPR-*establishing* bills (RI HB-7023, NY bottle-bill modernizations) as
 * harmful. A confidence_score floor doesn't help: that score is relevance confidence, not stance
 * confidence, and every auto-"weakens" bill already clears 0.7. So a public red "weakens" flag
 * requires a human spot-check (bills.reviewed). Unreviewed AI-"weakens" stays on /beta as the
 * review queue; promoting one to reviewed is what earns it the public flag.
 */
export function isWeakening(bill: {
  policy_stance?: string | null;
  reviewed?: boolean;
}): boolean {
  return bill.policy_stance === 'weakens' && bill.reviewed === true;
}

/**
 * Visual treatment for a bill's status badge. Normally colored by progression only (enacted=green,
 * failed/tabled=gray, else default). When `weakening` is set (see isWeakening — AI-classified at the
 * confidence floor), the badge flips to red and carries a "weakens circular economy" label so a
 * harmful enacted law reads as harmful rather than as a neutral-green achievement.
 */
export function statusBadge(
  status: string | null | undefined,
  weakening = false,
): { cls: string; marker: string; markerCls: string; label: string } {
  if (weakening) {
    return { cls: STATUS_RED, marker: '', markerCls: '', label: 'weakens circular economy' };
  }
  const s = (status ?? '').toLowerCase();
  const statusCls = s === 'enacted'
    ? STATUS_GREEN
    : s === 'failed' || s === 'tabled'
      ? STATUS_GRAY
      : STATUS_DEFAULT;
  return { cls: statusCls, marker: '', markerCls: '', label: '' };
}

/**
 * Human-readable label for a raw status token. Replaces `_`/`-` separators with
 * spaces and Title-cases — so `passed_chamber` renders "Passed Chamber" rather
 * than the underscore-preserving "Passed_chamber" the badges used to show.
 */
export function formatStatusLabel(status: string | null | undefined): string {
  if (!status) return '—';
  return status
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Canonical color for a legislative stage, keyed off the status palette in
 * theme.css (--status-*). One source of truth so the timeline dots, momentum
 * chart, and any future status-colored surface stay in sync. Returns a CSS
 * `var()` string usable both in className-free `style` props and in recharts.
 */
export const STATUS_COLORS = {
  introduced: 'var(--status-introduced)',
  committee:  'var(--status-committee)',
  advancing:  'var(--status-advancing)',
  enacted:    'var(--status-enacted)',
  weakens:    'var(--status-weakens)',
  dormant:    'var(--status-dormant)',
} as const;

export type StatusKey = keyof typeof STATUS_COLORS;

export function statusColor(key: string | null | undefined): string {
  const k = (key ?? '').toLowerCase();
  if (k in STATUS_COLORS) return STATUS_COLORS[k as StatusKey];
  if (k === 'failed' || k === 'tabled') return STATUS_COLORS.dormant;
  if (k === 'passed_chamber' || k === 'passed') return STATUS_COLORS.advancing;
  if (k === 'in_committee') return STATUS_COLORS.committee;
  return STATUS_COLORS.dormant;
}

/**
 * Maps a 0–100 risk/preemption score to a level with a TEXT label, so severity
 * is never conveyed by color alone (WCAG 1.4.1). Thresholds mirror scoreColor().
 */
export function riskLevel(score: number | null | undefined): {
  label: 'High' | 'Medium' | 'Low' | 'N/A';
  textClass: string;
} {
  if (score == null || Number.isNaN(score)) return { label: 'N/A', textClass: 'text-text-muted' };
  if (score >= 70) return { label: 'High', textClass: 'text-risk-high' };
  if (score >= 40) return { label: 'Medium', textClass: 'text-risk-medium' };
  return { label: 'Low', textClass: 'text-risk-low' };
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
  incentives: 'Incentives',
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

/**
 * A LegiScan deep link for a bill — a reliable backup when the primary source link is dead.
 * LegiScan's stable scheme is legiscan.com/{STATE}/bill/{NUMBER} (works for "US" federal bills too);
 * it resolves to the latest matching session. Returns null when we lack a state or bill number.
 */
export function legiscanUrl(state?: string | null, billNumber?: string | null): string | null {
  if (!state || !billNumber) return null;
  // LegiScan's URL scheme uses no separator (HB2156, not "HB-2156"/"HB 2156"), and our bill_numbers
  // are almost all hyphenated — so strip everything but letters/digits or the link 404s.
  const num = billNumber.replace(/[^a-zA-Z0-9]/g, '');
  if (!num) return null;
  return `https://legiscan.com/${state.toUpperCase()}/bill/${num}`;
}

export interface SourceLink {
  href: string;
  label: string;
  /** true when href is a fallback (resolved redirect or LegiScan), not the original source_url. */
  isFallback: boolean;
  /** Short user-facing note explaining the fallback, or null when the original link is used as-is. */
  note: string | null;
}

/**
 * Resolve the best outbound "View Source" link for a bill, honoring audited link health
 * (source_url_status, set by scripts/audit_bill_source_links.py) so a click never lands on a
 * dead/moved page when we already know better:
 *   - redirected -> link to the resolved URL (the page moved)
 *   - dead       -> link to a LegiScan backup (or keep the original with a warning if none exists)
 *   - alive / blocked / unchecked (null) -> the original source_url as-is. "blocked" means we
 *     couldn't verify (a WAF/timeout), NOT that it's broken — we never downgrade an unproven link.
 * Returns null only when there's no usable link at all.
 */
export function resolveSourceLink(bill: {
  source_url: string | null;
  source_url_status?: string | null;
  source_url_final?: string | null;
  state: string;
  bill_number: string | null;
}): SourceLink | null {
  const { source_url, source_url_status, source_url_final, state, bill_number } = bill;

  if (source_url_status === 'redirected' && source_url_final) {
    return { href: source_url_final, label: 'View Source ↗', isFallback: true,
             note: 'The original source page moved — this is the updated link.' };
  }

  if (source_url_status === 'dead') {
    const ls = legiscanUrl(state, bill_number);
    if (ls) {
      return { href: ls, label: 'View on LegiScan ↗', isFallback: true,
               note: 'The original source link is unavailable — showing the bill on LegiScan instead.' };
    }
    if (source_url) {
      return { href: source_url, label: 'View Source ↗', isFallback: false,
               note: 'This source link may be unavailable.' };
    }
    return null;
  }

  if (source_url) {
    return { href: source_url, label: 'View Source ↗', isFallback: false, note: null };
  }

  // No source_url at all — offer LegiScan if we can build one.
  const ls = legiscanUrl(state, bill_number);
  return ls ? { href: ls, label: 'View on LegiScan ↗', isFallback: true, note: null } : null;
}

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
