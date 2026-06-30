'use client';
import { useMemo, useState } from 'react';
import type { BillSearchHit, BillSummary } from '@/lib/types';
import { applyBillFilters, type BillFilterState } from './BillFilters';
import { useBillTextSearch, useBillTextCoverage } from '@/hooks/useBills';
import { fixEncoding } from '@/lib/utils';
import { BillModal } from '@/components/ui/BillModal';
import { track } from '@/lib/analytics';

/** Render one ts_headline fragment, turning the server's <mark>…</mark> into <mark> elements.
 *  The bill text is HTML-stripped at ingest, so the only markup is the highlight — and we still
 *  build React nodes (never dangerouslySetInnerHTML), so any stray character is escaped by React. */
function Snippet({ fragment }: { fragment: string }) {
  const parts = fragment.split(/(<mark>|<\/mark>)/);
  let on = false;
  return (
    <span className="text-text-secondary">
      {parts.map((p, i) => {
        if (p === '<mark>') { on = true; return null; }
        if (p === '</mark>') { on = false; return null; }
        if (!p) return null;
        return on
          ? <mark key={i} className="rounded bg-green-accent/25 px-0.5 text-text-primary">{p}</mark>
          : <span key={i}>{p}</span>;
      })}
    </span>
  );
}

interface Props {
  /** The raw search term from the filter box. */
  query: string;
  /** IDs already shown in the main table — so we surface only ADDITIONAL full-text matches. */
  shownIds: Set<number>;
  /** Active filters; applied (minus the search term) so deep-text hits respect state/material/etc. */
  filters: BillFilterState;
}

/** "N more bills mention '<term>' in their full bill text" — the opt-in deep-search result group.
 *  Surfaces bills whose statutory text matches the query but whose title/summary do NOT (those are
 *  already in the table), with the matched snippet highlighted. Driven by SB 707/footwear-type gaps. */
export function FullTextMatches({ query, shownIds, filters }: Props) {
  const [selected, setSelected] = useState<BillSummary | null>(null);
  const { data: hits = [], isFetching } = useBillTextSearch(query);
  const { data: coverage } = useBillTextCoverage();
  const q = query.trim();
  const indexed = coverage?.indexed_bills ?? 0;
  const coverageNote =
    coverage && coverage.total_bills > 0 && indexed < coverage.total_bills
      ? `Full-text search covers ${indexed.toLocaleString()} of ${coverage.total_bills.toLocaleString()} bills — some aren’t indexed yet.`
      : null;

  const extra = useMemo(() => {
    // Keep deep-text hits consistent with the rest of the view (state/material/status), but don't
    // re-filter by the search term itself, then drop anything already visible in the table.
    const allowed = new Set(
      applyBillFilters(hits as BillSummary[], { ...filters, search: '' }).map(b => b.id),
    );
    return (hits as BillSearchHit[]).filter(h => allowed.has(h.id) && !shownIds.has(h.id));
  }, [hits, filters, shownIds]);

  if (q.length < 2) return null;
  if (!extra.length) {
    if (isFetching) {
      // Quiet while the debounced query is still settling.
      return <p className="text-text-muted text-meta">Searching full bill text…</p>;
    }
    // Index not populated on this environment → stay hidden. Once it is, be honest that we looked:
    // an empty deep search means "not in the text we've indexed", not "nowhere in any bill".
    if (indexed === 0) return null;
    return (
      <p className="text-text-muted text-meta">
        No additional matches in the full bill text.{coverageNote ? ` ${coverageNote}` : ''}
      </p>
    );
  }

  return (
    <section className="space-y-3 rounded-lg border border-border-default bg-bg-secondary/40 p-4">
      <div>
        <h3 className="font-serif text-sm text-text-primary">
          {extra.length} more {extra.length === 1 ? 'bill' : 'bills'} mention{' '}
          <span className="text-green-accent">“{q}”</span> in the full bill text
        </h3>
        <p className="text-text-muted text-meta">
          The term appears in the statute itself, not the title or summary.
        </p>
      </div>
      <ul className="space-y-2">
        {extra.map(h => (
          <li key={h.id}>
            <button
              onClick={() => {
                track('bill_open', { bill_id: h.id, state: h.state, instrument_type: h.instrument_type, source: 'fulltext' });
                setSelected(h);
              }}
              className="w-full rounded-md border border-border-default bg-bg-primary/40 p-2.5 text-left transition-colors hover:border-green-accent"
            >
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-xs font-bold text-green-accent">{h.state}</span>
                <span className="font-mono text-xs text-text-muted">{h.bill_number ?? '—'}</span>
                <span className="truncate text-sm text-text-primary">{fixEncoding(h.title) || 'Untitled'}</span>
              </div>
              {h.snippets.length > 0 && (
                <div className="mt-1 space-y-0.5 text-xs leading-relaxed">
                  {h.snippets.slice(0, 2).map((s, i) => (
                    <div key={i} className="text-text-muted">… <Snippet fragment={s} /> …</div>
                  ))}
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>
      {coverageNote && <p className="text-text-muted text-meta">{coverageNote}</p>}
      <BillModal bill={selected} onClose={() => setSelected(null)} />
    </section>
  );
}
