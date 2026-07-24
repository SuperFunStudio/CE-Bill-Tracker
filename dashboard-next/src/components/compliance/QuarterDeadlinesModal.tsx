'use client';
import { useEffect, useMemo } from 'react';
import { formatDate, daysUntil } from '@/lib/utils';
import type { DeadlineSummary } from '@/lib/types';

/** Plain-language relative time for a deadline date. */
function relDays(dateStr: string | null): string | null {
  const n = daysUntil(dateStr);
  if (n === null) return null;
  if (n === 0) return 'today';
  if (n > 0) return `in ${n} day${n === 1 ? '' : 's'}`;
  return `${-n} day${n === -1 ? '' : 's'} ago`;
}

/** The action a row is really asking for — the requirement, then the bill, then the type. */
function headlineFor(d: DeadlineSummary): string {
  return d.description || d.bill_title || `${d.deadline_type} deadline`.replace(/_/g, ' ');
}

/**
 * The list of deadlines that fall inside one quarter, opened from the density
 * rail on the Upcoming Deadlines page. Mirrors DeadlineModal's shell (bottom
 * sheet on mobile, right-aligned panel on desktop, Escape to close). Selecting
 * a row hands off to the full per-deadline detail modal — glance → quarter →
 * the specific bill and its next steps.
 */
export function QuarterDeadlinesModal({
  title,
  items,
  onClose,
  onSelect,
}: {
  title: string | null;
  items: DeadlineSummary[];
  onClose: () => void;
  onSelect: (d: DeadlineSummary) => void;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  useEffect(() => {
    if (title) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => { document.body.style.overflow = ''; };
  }, [title]);

  const sorted = useMemo(
    () => items.slice().sort((a, b) => a.deadline_date.localeCompare(b.deadline_date)),
    [items],
  );

  if (!title) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end md:items-start md:justify-end p-0 md:p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60" />
      <div
        className="relative z-10 w-full md:w-[480px] md:max-w-[40vw] max-h-[90dvh] overflow-y-auto rounded-t-2xl md:rounded-xl md:mt-16 bg-bg-secondary border border-border-default"
        onClick={e => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 bg-bg-secondary/95 backdrop-blur border-b border-border-default px-5 py-3 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-text-primary font-semibold leading-tight">{title}</h3>
            <p className="text-xs text-text-muted">
              {sorted.length} deadline{sorted.length === 1 ? '' : 's'} · soonest first
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-text-muted hover:text-text-primary text-lg shrink-0"
          >
            ✕
          </button>
        </div>

        <div className="divide-y divide-border-default">
          {sorted.map((d, i) => {
            const rel = relDays(d.deadline_date);
            const who = [d.who_affected, [d.state, d.bill_number].filter(Boolean).join(' ')]
              .filter(Boolean)
              .join(' · ');
            return (
              <button
                key={`${d.id}-${i}`}
                type="button"
                onClick={() => onSelect(d)}
                className="w-full text-left grid grid-cols-[6rem_1fr_auto] items-center gap-x-3 py-2.5 px-5 hover:bg-bg-primary transition-colors"
              >
                <span className="font-mono text-sm font-semibold text-text-primary">
                  {formatDate(d.deadline_date)}
                  {rel && <span className="block text-meta font-normal text-text-muted">{rel}</span>}
                </span>
                <span className="min-w-0">
                  <span className="block text-sm text-text-primary truncate">{headlineFor(d)}</span>
                  {who && <span className="block text-xs text-text-muted truncate">{who}</span>}
                </span>
                <span className="font-mono text-xs text-text-secondary border border-border-default rounded px-1.5 py-0.5 shrink-0">
                  {d.state}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
