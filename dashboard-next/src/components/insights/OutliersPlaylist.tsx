'use client';

import { useEffect, useState } from 'react';
import { fetchBills } from '@/lib/api';
import { fixEncoding } from '@/lib/utils';
import { track } from '@/lib/analytics';
import { BillModal } from '@/components/ui/BillModal';
import type { BillSummary } from '@/lib/types';

/**
 * "The Outliers" — a browsable list of the in-scope bills classified as instrument_type "other":
 * circular-economy bills whose mechanism doesn't map to a named instrument (disposal bans, product
 * standards, reuse/refill mandates, organics diversion). It's the discovery surface for the catch-all
 * bucket — a playlist of the bills that don't fit a neat box. Each row opens the standard BillModal.
 */
export function OutliersPlaylist() {
  const [open, setOpen] = useState(false);
  const [bills, setBills] = useState<BillSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<BillSummary | null>(null);

  // Lazy-load on first expand; keep the result cached for the session.
  useEffect(() => {
    if (!open || bills) return;
    let cancelled = false;
    fetchBills({ instrument_type: 'other', ce_relevant: true, limit: 200 })
      .then((d) => {
        if (!cancelled) setBills(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load the outliers.');
      });
    return () => {
      cancelled = true;
    };
  }, [open, bills]);

  return (
    <div className="rounded-lg border border-border-default bg-bg-primary">
      <button
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next) track('insights_outliers_open');
        }}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="flex items-baseline gap-2">
          <span className="font-serif text-text-primary text-sm font-semibold">The Outliers</span>
          <span className="text-text-muted text-xs">
            bills that don&apos;t fit a box{bills ? ` · ${bills.length}` : ''}
          </span>
        </span>
        <span className="text-text-muted text-xs">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="border-t border-border-default">
          {error ? (
            <p className="px-4 py-3 text-sm text-red-600 dark:text-red-400">{error}</p>
          ) : !bills ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-9 w-full animate-pulse rounded bg-bg-tertiary" />
              ))}
            </div>
          ) : bills.length === 0 ? (
            <p className="px-4 py-3 text-body text-text-secondary">No outlier bills right now.</p>
          ) : (
            <ul className="max-h-96 divide-y divide-border-default overflow-y-auto">
              {bills.map((bill) => (
                <li key={bill.id}>
                  <button
                    onClick={() => {
                      setSelected(bill);
                      track('insights_outliers_bill', { bill_id: bill.id });
                    }}
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-bg-tertiary"
                  >
                    <span className="shrink-0 font-mono text-text-muted text-meta w-16">
                      {bill.state} {bill.bill_number ?? ''}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-text-secondary text-sm">
                      {fixEncoding(bill.title) || 'Untitled'}
                    </span>
                    {bill.status && (
                      <span className="shrink-0 text-text-muted text-meta capitalize">
                        {bill.status.replace(/_/g, ' ')}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <BillModal bill={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
