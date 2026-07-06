// Human-facing rendering of the extracted compliance dimensions (see app/classification/
// sonnet_extractor.py). Kept separate from components so the bill detail panel, Insights charts, and
// the future "Ask the Bills" page all format a dimension the same way.
import type { ComplianceDetails } from '@/lib/types';

const titleize = (s: string | null | undefined): string =>
  (s ?? '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

/** Ordered display labels for the eight dimensions. */
export const DIMENSION_LABELS: Record<string, string> = {
  collection_targets: 'Collection / Recovery Targets',
  recycled_content: 'Recycled-Content Minimums',
  eco_modulation: 'Eco-Modulation',
  fee_amounts: 'Fees',
  penalties: 'Penalties',
  bans_restrictions: 'Bans & Restrictions',
  pro_structure: 'PRO Structure',
  labeling: 'Labeling',
};

export interface DimensionCard {
  key: string;
  label: string;
  summary: string;      // one-line human summary of the details
  excerpt?: string;     // verbatim source_excerpt (original language) for citation
}

/** Condense one dimension's structured detail into a short readable line. */
function summarize(key: string, env: Record<string, unknown>): string {
  switch (key) {
    case 'collection_targets': {
      const t = (env.targets as CollTarget[] | undefined) ?? [];
      if (!t.length) return 'Sets collection/recovery targets';
      return t.slice(0, 3).map(x =>
        [x.percent != null ? `${x.percent}%` : null, x.material, x.by_year ? `by ${x.by_year}` : null,
          x.basis && x.basis !== 'unspecified' ? `(${titleize(x.basis)})` : null]
          .filter(Boolean).join(' ')).join('; ');
    }
    case 'recycled_content': {
      const m = (env.minimums as Minimum[] | undefined) ?? [];
      return m.slice(0, 3).map(x =>
        [x.percent != null ? `${x.percent}%` : null, x.material, x.by_year ? `by ${x.by_year}` : null]
          .filter(Boolean).join(' ')).join('; ') || 'Minimum recycled-content required';
    }
    case 'eco_modulation': {
      const c = (env.criteria as string[] | undefined) ?? [];
      return c.length ? `Modulated on: ${c.slice(0, 5).join(', ')}` : 'Fees are eco-modulated';
    }
    case 'fee_amounts': {
      const r = (env.rates as Rate[] | undefined) ?? [];
      return r.slice(0, 3).map(x =>
        [x.amount != null ? `${x.amount} ${x.currency ?? ''}`.trim() : null, titleize(x.basis),
          x.material ? `— ${x.material}` : null].filter(Boolean).join(' ')).join('; ')
        || 'Producer fees apply';
    }
    case 'penalties': {
      const a = env.max_amount as number | null | undefined;
      return a != null
        ? `Up to ${a} ${(env.currency as string) ?? ''}${env.per ? ` per ${env.per}` : ''}`.trim()
        : 'Penalties for non-compliance';
    }
    case 'bans_restrictions': {
      const items = (env.items as BanItem[] | undefined) ?? [];
      return items.slice(0, 3).map(x =>
        `${x.target}${x.type ? ` (${titleize(x.type)})` : ''}${x.effective_date ? `, ${x.effective_date}` : ''}`)
        .join('; ') || 'Bans or material restrictions';
    }
    case 'pro_structure': {
      const parts = [titleize(env.model as string)];
      if (env.needs_assessment) parts.push('needs-assessment required');
      const named = (env.named_pros as string[] | undefined) ?? [];
      if (named.length) parts.push(named.slice(0, 2).join(', '));
      return parts.filter(Boolean).join(' · ') || 'PRO / stewardship organization';
    }
    case 'labeling': {
      const reqs = (env.requirements as LabelReq[] | undefined) ?? [];
      return reqs.slice(0, 4).map(x => titleize(x.type)).filter(Boolean).join(', ')
        || 'On-product labeling required';
    }
    default:
      return '';
  }
}

/** The dimensions that are `present` on a bill, in display order, ready to render. */
export function presentDimensions(cd: ComplianceDetails | null | undefined): DimensionCard[] {
  if (!cd) return [];
  return Object.keys(DIMENSION_LABELS)
    .map((key): DimensionCard | null => {
      const env = (cd as Record<string, unknown>)[key] as Record<string, unknown> | undefined;
      if (!env || env.status !== 'present') return null;
      return {
        key,
        label: DIMENSION_LABELS[key],
        summary: summarize(key, env),
        excerpt: (env.source_excerpt as string) || undefined,
      };
    })
    .filter((x): x is DimensionCard => x !== null);
}

/** The present dimensions keyed by dimension key — for aligning two bills (e.g. a draft vs the strong
 *  baseline) dimension-by-dimension. Only `present` dimensions appear; callers read the raw envelope's
 *  `status` for absent/not_applicable. */
export function dimensionMap(cd: ComplianceDetails | null | undefined): Record<string, DimensionCard> {
  const out: Record<string, DimensionCard> = {};
  for (const d of presentDimensions(cd)) out[d.key] = d;
  return out;
}

/** The raw status of one dimension envelope (present | absent | not_applicable | undefined). */
export function dimensionStatus(cd: ComplianceDetails | null | undefined, key: string): string | undefined {
  const env = (cd as Record<string, unknown> | null | undefined)?.[key] as { status?: string } | undefined;
  return env?.status;
}

// Local structural aliases (kept here so this module stays self-contained for formatting).
interface CollTarget { material: string; percent: number | null; by_year: string | null; basis: string; }
interface Minimum { material: string; percent: number | null; by_year: string | null; }
interface Rate { basis: string; amount: number | null; currency?: string; material?: string | null; }
interface BanItem { target: string; type: string; effective_date: string | null; }
interface LabelReq { type: string; on_pack?: boolean; detail?: string; }
