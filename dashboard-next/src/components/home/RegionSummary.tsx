'use client';
import { useMemo, type ReactNode } from 'react';
import type { BillSummary } from '@/lib/types';
import { billHref, fixEncoding, formatDate } from '@/lib/utils';
import { fmtCount } from '@/lib/mapScale';

// Status buckets for the summary strip. "In progress" folds the US funnel stages together — the
// summary is a glance, the table carries the detail.
const BUCKETS: { key: string; label: string; match: (s: string) => boolean; tone: string }[] = [
  { key: 'enacted', label: 'Enacted', match: s => s === 'enacted', tone: 'var(--status-enacted)' },
  {
    key: 'progress', label: 'In progress',
    match: s => ['introduced', 'in_committee', 'passed_chamber', 'passed'].includes(s),
    tone: 'var(--status-introduced)',
  },
  { key: 'stopped', label: 'Failed / vetoed', match: s => s === 'failed' || s === 'vetoed', tone: 'var(--status-dormant)' },
];

/**
 * Compact summary header for a jurisdiction in focus — what used to be a full-height country map. The
 * table beside it is already filtered in place; this says where you are (name, crumbs), what's there
 * (counts by status) and what moved last (latest action), with a small locator map when one helps.
 */
export function RegionSummary({
  name, kind, bills, crumbs, locator,
}: {
  name: string;
  /** "National law", "US state", "27 member states"… */
  kind: string;
  /** The bills in focus — the table's current set. */
  bills: BillSummary[];
  /** Breadcrumb controls ("All regions / European Union"). */
  crumbs?: ReactNode;
  /** Small locator map, for a lone country. */
  locator?: ReactNode;
}) {
  const { counts, latest } = useMemo(() => {
    const c: Record<string, number> = {};
    let last: BillSummary | null = null;
    for (const b of bills) {
      const s = (b.status ?? '').toLowerCase();
      const bucket = BUCKETS.find(x => x.match(s));
      if (bucket) c[bucket.key] = (c[bucket.key] ?? 0) + 1;
      if (b.last_action_date && (!last || b.last_action_date > (last.last_action_date ?? ''))) last = b;
    }
    return { counts: c, latest: last as BillSummary | null };
  }, [bills]);

  return (
    <section className="surface-card p-4" aria-label={`${name} summary`}>
      {crumbs && <div className="mb-2 flex flex-wrap items-center gap-1 text-xs text-text-muted">{crumbs}</div>}
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="font-serif text-xl leading-tight text-text-primary">{name}</h2>
          <p className="mt-0.5 text-xs text-text-muted">
            {kind} · {fmtCount(bills.length)} tracked {bills.length === 1 ? 'measure' : 'measures'}
          </p>
          <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
            {BUCKETS.map(b => (
              <div key={b.key} className="min-w-0">
                <dt className="flex items-center gap-1.5 text-xs text-text-muted">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: b.tone }} aria-hidden />
                  {b.label}
                </dt>
                <dd className="text-lg font-semibold text-text-primary tabular-nums">{fmtCount(counts[b.key] ?? 0)}</dd>
              </div>
            ))}
          </dl>
        </div>
        {locator && <div className="w-32 shrink-0 sm:w-40">{locator}</div>}
      </div>
      {latest && (
        <p className="mt-3 border-t border-border-default pt-2.5 text-xs text-text-muted">
          <span className="field-label mr-1.5">Latest action</span>
          {formatDate(latest.last_action_date)} ·{' '}
          <a href={billHref(latest)} className="link-quiet">
            {latest.bill_number ? `${latest.bill_number} — ` : ''}
            {fixEncoding(latest.title)?.slice(0, 90) || 'Untitled'}
            {(fixEncoding(latest.title)?.length ?? 0) > 90 ? '…' : ''}
          </a>
        </p>
      )}
    </section>
  );
}
