'use client';
import { useEffect, useState } from 'react';
import type { BillSummary } from '@/lib/types';
import { fixEncoding, formatDate, formatInstrumentType, statusBadge } from '@/lib/utils';
import { BillModal } from '@/components/ui/BillModal';

interface BillTableProps {
  bills: BillSummary[];
  maxRows?: number;
  /** When set, show this many rows per page with manual Prev/Next paging. */
  autoPageSize?: number;
}

function StatusBadge({ status, stance }: { status: string | null; stance: string | null }) {
  if (!status) return <span className="text-text-muted text-xs">—</span>;
  const { cls, marker, markerCls, label } = statusBadge(status, stance);
  return (
    <span
      title={label || undefined}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${cls}`}
    >
      {marker && <span className={`leading-none ${markerCls}`}>{marker}</span>}
      {status.replace(/\b\w/g, c => c.toUpperCase())}
    </span>
  );
}

export function BillTable({ bills, maxRows, autoPageSize }: BillTableProps) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [page, setPage] = useState(0);

  const pageCount = autoPageSize ? Math.max(1, Math.ceil(bills.length / autoPageSize)) : 1;

  // Reset to the first page whenever the filtered list changes.
  useEffect(() => { setPage(0); }, [bills.length]);

  const safePage = page % pageCount;
  const displayBills = autoPageSize
    ? bills.slice(safePage * autoPageSize, safePage * autoPageSize + autoPageSize)
    : maxRows ? bills.slice(0, maxRows) : bills;
  const selectedBill = bills.find(b => b.id === selectedId) ?? null;

  function LitigationBadge({ bill }: { bill: BillSummary }) {
    if (bill.litigation_case_count === 0) return null;
    const risk = bill.max_preemption_risk ?? 0;
    const cls = risk >= 70
      ? 'bg-red-100 dark:bg-red-950/50 border-red-400 dark:border-red-700 text-red-700 dark:text-red-300'
      : risk >= 40
        ? 'bg-amber-100 dark:bg-amber-950/50 border-amber-400 dark:border-amber-700 text-amber-700 dark:text-amber-300'
        : 'bg-bg-primary border-border-default text-text-muted';
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${cls}`}>
        ⚖ {bill.litigation_case_count}
      </span>
    );
  }

  return (
    <div className="space-y-3">
      {/* ── Desktop table (hidden below sm) ── */}
      <div className="hidden sm:block overflow-x-auto rounded-lg border border-border-default">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-bg-secondary border-b border-border-default text-text-secondary text-xs uppercase">
              <th className="px-3 py-2 text-left w-10">State</th>
              <th className="px-3 py-2 text-left w-24">Bill #</th>
              <th className="px-3 py-2 text-left">Title</th>
              <th className="px-3 py-2 text-left w-24">Type</th>
              <th className="px-3 py-2 text-left w-32">Status</th>
              <th className="px-3 py-2 text-left w-28">Last Action</th>
              <th className="px-3 py-2 text-left w-20">Litigation</th>
              <th className="px-2 py-2 w-6" />
            </tr>
          </thead>
          <tbody>
            {displayBills.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-text-muted">
                  No bills match the current filters.
                </td>
              </tr>
            )}
            {displayBills.map(bill => (
              <tr
                key={bill.id}
                onClick={() => setSelectedId(bill.id)}
                className="border-b border-border-default cursor-pointer transition-colors hover:bg-bg-secondary"
              >
                <td className="px-3 py-2">
                  <span className="text-green-accent font-mono font-bold">{bill.state}</span>
                </td>
                <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
                  <span className="text-text-muted">{bill.bill_number ?? '—'}</span>
                  {bill.last_action_date && (
                    <span className="text-text-muted/60 ml-1" title={`${bill.last_action_date} session`}>
                      &rsquo;{bill.last_action_date.slice(2, 4)}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <div className="text-text-primary truncate max-w-xs" title={fixEncoding(bill.title) ?? ''}>
                    {fixEncoding(bill.title) || 'Untitled'}
                  </div>
                  {bill.material_categories && bill.material_categories.length > 0 && (
                    <div className="text-text-muted text-xs mt-0.5 truncate">
                      {bill.material_categories.slice(0, 3).map(c => c.replace(/_/g, ' ')).join(', ')}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 text-text-secondary text-xs">
                  {formatInstrumentType(bill.instrument_type)}
                </td>
                <td className="px-3 py-2">
                  <StatusBadge status={bill.status} stance={bill.policy_stance} />
                </td>
                <td className="px-3 py-2 text-text-muted text-xs">
                  {formatDate(bill.last_action_date)}
                </td>
                <td className="px-3 py-2">
                  <LitigationBadge bill={bill} />
                </td>
                <td className="px-2 py-2 text-text-muted text-xs text-center">›</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Mobile card list (hidden at sm and above) ── */}
      <div className="sm:hidden space-y-2">
        {displayBills.length === 0 && (
          <div className="px-3 py-6 text-center text-text-muted text-sm">
            No bills match the current filters.
          </div>
        )}
        {displayBills.map(bill => (
          <div
            key={bill.id}
            onClick={() => setSelectedId(bill.id)}
            className="rounded-lg border border-border-default bg-bg-secondary cursor-pointer transition-colors p-3 space-y-1.5 active:bg-green-dark/20"
          >
            {/* Row 1: state / bill# / litigation */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-green-accent font-mono font-bold text-sm">{bill.state}</span>
              {bill.bill_number && (
                <span className="text-text-muted font-mono text-xs">
                  {bill.bill_number}
                  {bill.last_action_date && <span className="text-text-muted/60">&nbsp;&rsquo;{bill.last_action_date.slice(2, 4)}</span>}
                </span>
              )}
              <LitigationBadge bill={bill} />
            </div>
            {/* Row 2: title (2-line clamp) */}
            <div className="text-text-primary text-sm line-clamp-2">
              {fixEncoding(bill.title) || 'Untitled'}
            </div>
            {/* Row 3: materials */}
            {bill.material_categories && bill.material_categories.length > 0 && (
              <div className="text-text-muted text-xs">
                {bill.material_categories.slice(0, 3).map(c => c.replace(/_/g, ' ')).join(' · ')}
              </div>
            )}
            {/* Row 4: status + last action + expand indicator */}
            <div className="flex items-center justify-between text-xs">
              <StatusBadge status={bill.status} stance={bill.policy_stance} />
              <div className="flex items-center gap-3 text-text-muted">
                <span>{formatDate(bill.last_action_date)}</span>
                <span>›</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {autoPageSize && pageCount > 1 ? (
        <div className="flex items-center justify-between text-xs text-text-muted">
          <span className="tabular-nums">
            {safePage * autoPageSize + 1}&ndash;{Math.min((safePage + 1) * autoPageSize, bills.length)} of {bills.length}
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={safePage === 0}
              className="hover:text-text-primary disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Previous"
            >
              &lsaquo; Prev
            </button>
            <span className="tabular-nums">Page {safePage + 1} / {pageCount}</span>
            <button
              onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))}
              disabled={safePage >= pageCount - 1}
              className="hover:text-text-primary disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Next"
            >
              Next &rsaquo;
            </button>
          </div>
        </div>
      ) : bills.length > (maxRows ?? Infinity) ? (
        <div className="text-text-muted text-xs text-right">
          Showing {maxRows} of {bills.length} bills
        </div>
      ) : null}

      <BillModal bill={selectedBill} onClose={() => setSelectedId(null)} />
    </div>
  );
}
