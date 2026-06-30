'use client';

import { useEffect, useState } from 'react';
import { fetchBills } from '@/lib/api';
import { formatInstrumentType, fixEncoding, statusBadge } from '@/lib/utils';
import { track } from '@/lib/analytics';
import type { BillSummary, BillParams } from '@/lib/types';

/**
 * The drill-down behind every Insights aggregate: given a chart bucket (a timeline year or a momentum
 * year×stance), it lists the exact bills that make up that count — each linking back to its primary
 * source. Showing the source on every bill is a Battle-of-the-Bills principle: the numbers are only
 * as credible as the receipts behind them, so the panel never shows a count without a way to verify it.
 *
 * Used by the timeline + momentum charts (a hover tooltip can't host clickable links, so the source
 * links live here, in a click-opened panel that scales from 1 to many bills).
 */

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  /** /bills filter for this bucket; null while nothing is selected. */
  params: BillParams | null;
  /** Analytics label for the originating chart (e.g. "timeline" | "momentum"). */
  source: string;
}

function BillRow({ bill, source }: { bill: BillSummary; source: string }) {
  const badge = statusBadge(bill.status);
  const label = [bill.state, bill.bill_number].filter(Boolean).join(' ');
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-3 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-text-primary text-sm">{label || `Bill #${bill.id}`}</span>
        {bill.status && (
          <span className={`shrink-0 rounded-full border px-2 py-0.5 text-meta ${badge.cls}`}>
            {bill.status.replace(/_/g, ' ')}
          </span>
        )}
      </div>
      {bill.title && (
        <p className="text-text-secondary text-xs leading-snug line-clamp-2">{fixEncoding(bill.title)}</p>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-text-muted">
        {bill.instrument_type && <span>{formatInstrumentType(bill.instrument_type)}</span>}
        {bill.source_url ? (
          <a
            href={bill.source_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => track('insights_drilldown_source', { source, bill_id: bill.id })}
            className="text-[rgb(var(--green-accent))] hover:underline"
          >
            View source ↗
          </a>
        ) : (
          <span className="italic opacity-70">source unavailable</span>
        )}
      </div>
    </div>
  );
}

export function BillDrilldownPanel({ open, onClose, title, subtitle, params, source }: Props) {
  const [bills, setBills] = useState<BillSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !params) return;
    let cancelled = false;
    setBills(null);
    setError(null);
    // limit 500: a single (year, status/stance) bucket is at most a few hundred bills.
    fetchBills({ ...params, limit: 500 })
      .then((d) => {
        if (!cancelled) setBills(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load bills.');
      });
    return () => {
      cancelled = true;
    };
  }, [open, params]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-md flex-col overflow-hidden border-l border-border-default bg-bg-secondary shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-border-default p-4">
          <div className="min-w-0">
            <h3 className="font-serif text-lg text-text-primary">{title}</h3>
            {subtitle && <p className="mt-0.5 text-xs text-text-muted">{subtitle}</p>}
            {bills && (
              <p className="mt-0.5 text-xs text-text-muted">
                {bills.length.toLocaleString()} bill{bills.length === 1 ? '' : 's'} · every row links to its source
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-md border border-border-default px-2 py-1 text-text-muted hover:bg-bg-tertiary"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-4">
          {error ? (
            <p className="text-sm text-error">{error}</p>
          ) : !bills ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-16 w-full animate-pulse rounded-lg bg-bg-tertiary" />
              ))}
            </div>
          ) : bills.length === 0 ? (
            <p className="text-body text-text-secondary">No bills in this bucket.</p>
          ) : (
            bills.map((b) => <BillRow key={b.id} bill={b} source={source} />)
          )}
        </div>
      </div>
    </div>
  );
}
