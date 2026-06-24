'use client';
import { useEffect } from 'react';
import { BillDetailPanel } from '@/components/bills/BillDetailPanel';
import { formatDate, daysUntil } from '@/lib/utils';
import type { BillSummary, DeadlineSummary } from '@/lib/types';

/** Title-cases a deadline type slug, e.g. "registration" → "Registration". */
function typeLabel(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/** Fallback detail when the deadline has no matching loaded bill. */
function DeadlineOnlyPanel({ deadline, onClose }: { deadline: DeadlineSummary; onClose: () => void }) {
  const days = daysUntil(deadline.deadline_date);
  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg p-5 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="text-green-accent font-mono font-bold text-sm">{deadline.state}</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border bg-green-accent/10 text-green-accent border-green-accent/30">
              {typeLabel(deadline.deadline_type)}
            </span>
            {days !== null && days >= 0 && days <= 30 && (
              <span className="text-urgency-high text-xs font-bold">{days}d remaining</span>
            )}
          </div>
          <h3 className="text-text-primary text-lg font-bold leading-snug">
            {deadline.bill_title || deadline.description || 'Compliance deadline'}
          </h3>
        </div>
        <button onClick={onClose} className="text-text-muted hover:text-text-primary text-lg shrink-0 mt-0.5">
          ✕
        </button>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        <span>Date: <span className="text-text-secondary">{formatDate(deadline.deadline_date)}</span></span>
        {deadline.bill_number && (
          <span>Bill: <span className="text-text-secondary">{deadline.bill_number}</span></span>
        )}
        {deadline.who_affected && (
          <span>Affects: <span className="text-text-secondary">{deadline.who_affected}</span></span>
        )}
      </div>

      {deadline.description && (
        <div className="bg-bg-primary rounded p-3 text-body text-text-secondary leading-relaxed">
          {deadline.description}
        </div>
      )}
    </div>
  );
}

/**
 * Pop-up detail for a deadline, matching the bill-explorer modal pattern
 * (bottom sheet on mobile, right-aligned panel on desktop). When the related
 * bill is loaded we show the full bill detail; otherwise a deadline-only view.
 */
export function DeadlineModal({
  deadline,
  bill,
  onClose,
}: {
  deadline: DeadlineSummary | null;
  bill: BillSummary | null;
  onClose: () => void;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  useEffect(() => {
    if (deadline) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => { document.body.style.overflow = ''; };
  }, [deadline]);

  if (!deadline) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end md:items-start md:justify-end p-0 md:p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60" />
      <div
        className="relative z-10 w-full md:w-[480px] md:max-w-[40vw] max-h-[90dvh] overflow-y-auto rounded-t-2xl md:rounded-xl md:mt-16"
        onClick={e => e.stopPropagation()}
      >
        {bill ? (
          <BillDetailPanel bill={bill} onClose={onClose} />
        ) : (
          <DeadlineOnlyPanel deadline={deadline} onClose={onClose} />
        )}
      </div>
    </div>
  );
}
