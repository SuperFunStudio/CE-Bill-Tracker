'use client';
import { useState, useMemo } from 'react';
import { useDeadlines } from '@/hooks/useDeadlines';
import { useBills } from '@/hooks/useBills';
import { MetricCard } from '@/components/ui/MetricCard';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { formatDate, daysUntil, downloadCsv, STATE_NAMES } from '@/lib/utils';
import type { DeadlineSummary } from '@/lib/types';

const DEADLINE_TYPE_COLORS: Record<string, string> = {
  registration: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 border-blue-400 dark:border-blue-700',
  reporting:    'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 border-purple-400 dark:border-purple-700',
  compliance:   'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 border-amber-400 dark:border-amber-700',
  effective:    'bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300 border-rose-400 dark:border-rose-700',
  fee:          'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 border-green-400 dark:border-green-700',
  labeling:     'bg-cyan-100 dark:bg-cyan-900/40 text-cyan-700 dark:text-cyan-300 border-cyan-400 dark:border-cyan-700',
};

function DeadlineTypeBadge({ type }: { type: string }) {
  const cls = DEADLINE_TYPE_COLORS[type.toLowerCase()] ?? 'bg-gray-100 dark:bg-gray-800 text-text-muted border-border-default';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${cls}`}>
      {type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
    </span>
  );
}

function DeadlineCard({ deadline }: { deadline: DeadlineSummary }) {
  const days = daysUntil(deadline.deadline_date);
  const urgentClass = days !== null && days <= 30 ? 'border-urgency-high' :
    days !== null && days <= 90 ? 'border-urgency-medium' :
      'border-border-default';

  return (
    <div className={`bg-bg-secondary border rounded-lg p-4 ${urgentClass}`}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-green-accent font-mono font-bold text-sm">{deadline.state}</span>
          <DeadlineTypeBadge type={deadline.deadline_type} />
          {days !== null && days <= 30 && (
            <span className="text-urgency-high text-xs font-bold">{days}d remaining</span>
          )}
        </div>
        <div className="text-text-primary font-mono text-sm shrink-0">
          {formatDate(deadline.deadline_date)}
        </div>
      </div>

      {deadline.description && (
        <p className="text-text-secondary text-sm mb-2">{deadline.description}</p>
      )}

      <div className="flex flex-wrap gap-3 text-xs text-text-muted">
        {deadline.bill_number && (
          <span>Bill: <span className="text-text-secondary">{deadline.bill_number}</span></span>
        )}
        {deadline.who_affected && (
          <span>Affects: <span className="text-text-secondary">{deadline.who_affected}</span></span>
        )}
      </div>
    </div>
  );
}

export default function CompliancePage() {
  const [daysAhead, setDaysAhead] = useState(365);
  const [stateFilter, setStateFilter] = useState('');
  const [includePast, setIncludePast] = useState(false);

  const { data: apiDeadlines = [], isLoading } = useDeadlines({ days_ahead: daysAhead, state: stateFilter || undefined });
  const { data: bills = [] } = useBills({ epr_relevant: true, limit: 5000 });

  // Merge API deadlines with compliance_details.deadlines from bills
  const allDeadlines = useMemo(() => {
    const seen = new Set<string>();
    const merged: DeadlineSummary[] = [];

    for (const d of apiDeadlines) {
      const key = `${d.state}|${d.deadline_date}|${d.deadline_type}`;
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(d);
      }
    }

    // Extract from compliance_details: explicit deadlines plus the key implementation/
    // enforcement dates (effective_date, compliance_date) that the bulk classifier pulled
    // out of each bill but that don't live in the `deadlines` array.
    const pushDeadline = (
      bill: (typeof bills)[number],
      type: string,
      date: string | null | undefined,
      description: string | null | undefined,
    ) => {
      if (!date) return;
      const key = `${bill.state}|${date}|${type}`;
      if (seen.has(key)) return;
      seen.add(key);
      merged.push({
        id: -1,
        state: bill.state,
        deadline_type: type,
        deadline_date: date,
        description: description ?? null,
        who_affected: null,
        bill_id: bill.id,
        bill_number: bill.bill_number,
        bill_title: bill.title,
      });
    };

    for (const bill of bills) {
      if (stateFilter && bill.state !== stateFilter) continue;
      const details = bill.compliance_details;
      for (const cd of details?.deadlines ?? []) {
        pushDeadline(bill, cd.type ?? 'compliance', cd.date, cd.description);
      }
      pushDeadline(bill, 'effective', details?.effective_date, `${bill.bill_number ?? 'Bill'} takes effect`);
      pushDeadline(bill, 'compliance', details?.compliance_date, `${bill.bill_number ?? 'Bill'} compliance date`);
    }

    return merged
      .filter(d => {
        const days = daysUntil(d.deadline_date);
        if (!includePast && days !== null && days < 0) return false;
        if (days !== null && days > daysAhead) return false;
        return true;
      })
      .sort((a, b) => a.deadline_date.localeCompare(b.deadline_date));
  }, [apiDeadlines, bills, stateFilter, includePast, daysAhead]);

  const within30 = allDeadlines.filter(d => { const n = daysUntil(d.deadline_date); return n !== null && n >= 0 && n <= 30; }).length;
  const within90 = allDeadlines.filter(d => { const n = daysUntil(d.deadline_date); return n !== null && n >= 0 && n <= 90; }).length;
  const nextDeadline = allDeadlines.find(d => { const n = daysUntil(d.deadline_date); return n !== null && n >= 0; });

  function handleExport() {
    downloadCsv('signalscout_deadlines.csv', allDeadlines.map(d => ({
      State: d.state,
      Type: d.deadline_type,
      Date: d.deadline_date,
      Description: d.description ?? '',
      Bill: d.bill_number ?? '',
      'Who Affected': d.who_affected ?? '',
    })));
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary mb-1">Upcoming Deadlines</h1>
        <p className="text-text-muted text-sm">Upcoming EPR compliance deadlines across all states</p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total Deadlines" value={allDeadlines.length} accent />
        <MetricCard label="Within 30 Days" value={within30} sublabel={within30 > 0 ? 'Action required' : 'None urgent'} />
        <MetricCard label="Within 90 Days" value={within90} />
        <MetricCard label="Next Deadline" value={nextDeadline ? formatDate(nextDeadline.deadline_date) : 'None'} />
      </div>

      {within30 > 0 && (
        <AlertBanner variant="red" message={`⚠ ${within30} deadline(s) within the next 30 days require immediate attention.`} />
      )}

      {/* Filters */}
      <div className="bg-bg-secondary border border-border-default rounded-lg p-4 flex flex-wrap gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Horizon</label>
          <select
            value={daysAhead}
            onChange={e => setDaysAhead(Number(e.target.value))}
            className="bg-bg-primary border border-border-default rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-green-accent"
          >
            {[30, 90, 180, 365, 730].map(d => (
              <option key={d} value={d}>{d} days</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">State</label>
          <select
            value={stateFilter}
            onChange={e => setStateFilter(e.target.value)}
            className="bg-bg-primary border border-border-default rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-green-accent"
          >
            <option value="">All States</option>
            {Object.entries(STATE_NAMES).map(([a, n]) => <option key={a} value={a}>{a} — {n}</option>)}
          </select>
        </div>

        <div className="flex items-end pb-1">
          <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary">
            <input type="checkbox" checked={includePast} onChange={e => setIncludePast(e.target.checked)} className="accent-green-accent" />
            Include past deadlines
          </label>
        </div>

        <div className="flex items-end ml-auto pb-1">
          <button onClick={handleExport} className="text-sm text-green-accent hover:underline">
            ↓ Export CSV
          </button>
        </div>
      </div>

      {/* Deadline list */}
      <div>
        <SectionHeader title={`Deadlines (${allDeadlines.length})`} />
        {isLoading ? (
          <div className="space-y-3">{[...Array(5)].map((_, i) => <div key={i} className="h-24 bg-bg-secondary rounded-lg animate-pulse" />)}</div>
        ) : allDeadlines.length === 0 ? (
          <div className="text-center text-text-muted py-12">No deadlines found for the selected filters.</div>
        ) : (
          <div className="space-y-3">
            {allDeadlines.map((d, i) => <DeadlineCard key={`${d.id}-${i}`} deadline={d} />)}
          </div>
        )}
      </div>
    </div>
  );
}
