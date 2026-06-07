'use client';
import { useMemo } from 'react';
import type { DeadlineSummary } from '@/lib/types';
import { formatDate, daysUntil } from '@/lib/utils';
import { deadlineAccentText, deadlineAccentDot } from '@/lib/deadlineStyle';

/** Group deadlines into [YYYY-MM, items[]] buckets, chronologically. */
function groupByMonth(deadlines: DeadlineSummary[]): [string, DeadlineSummary[]][] {
  const groups = new Map<string, DeadlineSummary[]>();
  for (const d of deadlines) {
    const key = d.deadline_date.slice(0, 7);
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(d);
  }
  return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

function monthLabel(yyyymm: string): string {
  const [y, m] = yyyymm.split('-').map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function DeadlineEntry({ d, onSelect }: { d: DeadlineSummary; onSelect: (d: DeadlineSummary) => void }) {
  const days = daysUntil(d.deadline_date);
  return (
    <button
      type="button"
      onClick={() => onSelect(d)}
      className="flex items-start gap-2 text-left w-full group/entry"
    >
      <span className={`mt-[5px] h-2 w-2 shrink-0 rounded-full ${deadlineAccentDot(days)}`} />
      <div className="min-w-0">
        {/* Brief headline — opens the detail modal */}
        <div className={`text-xs font-medium leading-snug group-hover/entry:underline ${deadlineAccentText(days)}`}>
          {d.state} {d.bill_number ?? ''}
        </div>
        {d.description && (
          <div className="text-text-muted text-[11px] leading-snug line-clamp-2">{d.description}</div>
        )}
        <div className="text-text-muted text-[10px] font-mono mt-0.5">{formatDate(d.deadline_date)}</div>
      </div>
    </button>
  );
}

/**
 * A "gazette spine" timeline of compliance deadlines across the next few years.
 * Mobile: a vertical spine read top-to-bottom. Desktop: a horizontal spine you
 * scroll through, with each month hanging off a node on the rule. Each headline
 * opens the deadline detail modal.
 */
export function DeadlineTimeline({
  deadlines,
  onSelect,
}: {
  deadlines: DeadlineSummary[];
  onSelect: (d: DeadlineSummary) => void;
}) {
  const groups = useMemo(() => groupByMonth(deadlines), [deadlines]);
  if (!groups.length) return null;

  return (
    <div>
      {/* ── Mobile: vertical spine ── */}
      <div className="md:hidden relative pl-5 border-l border-text-primary/20 space-y-6">
        {groups.map(([ym, items]) => (
          <div key={ym} className="relative">
            <span className="absolute -left-[1.55rem] top-1 h-2.5 w-2.5 rounded-full bg-green-accent ring-2 ring-bg-primary" />
            <h3 className="font-serif uppercase tracking-wider text-text-secondary text-xs mb-2">
              {monthLabel(ym)}
            </h3>
            <div className="space-y-2.5">
              {items.map((d, i) => <DeadlineEntry key={`${d.id}-${i}`} d={d} onSelect={onSelect} />)}
            </div>
          </div>
        ))}
      </div>

      {/* ── Desktop: horizontal-scroll spine ── */}
      <div className="hidden md:block">
        <div className="overflow-x-auto pb-2">
          <div className="flex min-w-max border-t border-text-primary/20">
            {groups.map(([ym, items]) => (
              <div key={ym} className="relative w-56 shrink-0 px-4 pt-6">
                <span className="absolute -top-[6px] left-4 h-3 w-3 rounded-full bg-green-accent ring-2 ring-bg-primary" />
                <h3 className="font-serif uppercase tracking-wider text-text-secondary text-xs mb-3">
                  {monthLabel(ym)}
                </h3>
                <div className="space-y-3 border-l border-text-primary/10 pl-3">
                  {items.map((d, i) => <DeadlineEntry key={`${d.id}-${i}`} d={d} onSelect={onSelect} />)}
                </div>
              </div>
            ))}
          </div>
        </div>
        <p className="text-text-muted text-[11px] italic mt-1">
          Scroll horizontally to move through the timeline →
        </p>
      </div>
    </div>
  );
}
