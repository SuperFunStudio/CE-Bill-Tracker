'use client';
import { useState, useMemo } from 'react';
import { useDeadlines } from '@/hooks/useDeadlines';
import { useBills } from '@/hooks/useBills';
import { MetricCard } from '@/components/ui/MetricCard';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { DeadlineTimeline } from '@/components/compliance/DeadlineTimeline';
import { DeadlineModal } from '@/components/compliance/DeadlineModal';
import { deadlineAccentText } from '@/lib/deadlineStyle';
import { useScope, useScopeActive } from '@/components/scope/ScopeContext';
import { useAuth, useProGate } from '@/components/auth/AuthContext';
import { LockIcon } from '@/components/ui/icons';
import { deadlineInScope } from '@/lib/scope';
import { formatMaterial } from '@/components/scope/ScopeOnboarding';
import { formatDate, daysUntil, downloadCsv, STATE_NAMES } from '@/lib/utils';
import type { DeadlineSummary } from '@/lib/types';

/** Single-accent type chip (hue is the brand accent; see deadlineStyle). */
function DeadlineTypeBadge({ type }: { type: string }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border bg-green-accent/10 text-green-accent border-green-accent/30 shrink-0">
      {type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
    </span>
  );
}

/** Compact, clickable "brief headline" row — opens the detail modal. */
function DeadlineRow({ deadline, onSelect }: { deadline: DeadlineSummary; onSelect: (d: DeadlineSummary) => void }) {
  const days = daysUntil(deadline.deadline_date);
  const urgentClass = days !== null && days >= 0 && days <= 30 ? 'border-urgency-high' :
    days !== null && days >= 0 && days <= 90 ? 'border-urgency-medium' :
      'border-border-default';
  const headline = deadline.bill_title || deadline.description || `${deadline.deadline_type} deadline`;

  return (
    <button
      type="button"
      onClick={() => onSelect(deadline)}
      className={`w-full text-left bg-bg-secondary border rounded-lg p-3 flex items-center gap-3 hover:bg-bg-primary/40 transition-colors ${urgentClass}`}
    >
      <span className={`font-mono font-bold text-sm shrink-0 w-8 ${deadlineAccentText(days)}`}>{deadline.state}</span>
      <DeadlineTypeBadge type={deadline.deadline_type} />
      <span className="text-text-primary text-sm truncate flex-1 min-w-0">{headline}</span>
      {days !== null && days >= 0 && days <= 30 && (
        <span className="text-urgency-high text-xs font-bold shrink-0">{days}d</span>
      )}
      <span className="text-text-muted font-mono text-xs shrink-0 hidden sm:inline">{formatDate(deadline.deadline_date)}</span>
      <span className="text-text-muted text-xs shrink-0">›</span>
    </button>
  );
}

// Past "include past deadlines" view is capped to the last 5 years (the historical EPR
// backfill carries laws back to the 1990s; their compliance dates are not actionable).
const PAST_DEADLINE_CUTOFF_DAYS = 5 * 365;

export default function CompliancePage() {
  const [daysAhead, setDaysAhead] = useState(1095);
  const [stateFilter, setStateFilter] = useState('');
  const [includePast, setIncludePast] = useState(false);
  const [selected, setSelected] = useState<DeadlineSummary | null>(null);

  const { data: apiDeadlines = [], isLoading } = useDeadlines({ days_ahead: daysAhead, state: stateFilter || undefined });
  const { data: bills = [] } = useBills({ epr_relevant: true, limit: 5000 });

  const { scope } = useScope();
  const scopeActive = useScopeActive();

  const { isPro } = useAuth();
  const gatePro = useProGate();

  // Merge API deadlines with compliance_details.deadlines from bills
  const mergedDeadlines = useMemo(() => {
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
        // Even with "include past" on, don't surface ancient deadlines: the historical
        // backfill carries laws back to the 1990s/2000s whose compliance dates are long gone.
        // Cap the past view at 5 years so it stays a recent-history aid, not an archive dump.
        if (includePast && days !== null && days < -PAST_DEADLINE_CUTOFF_DAYS) return false;
        if (days !== null && days > daysAhead) return false;
        return true;
      })
      .sort((a, b) => a.deadline_date.localeCompare(b.deadline_date));
  }, [apiDeadlines, bills, stateFilter, includePast, daysAhead]);

  // Default the whole page to the reader's personalization scope (materials live on the linked bill).
  // The global "Show everything" toggle in the ScopeBar turns this off.
  const billMaterials = useMemo(() => {
    const map = new Map<number, string[]>();
    for (const b of bills) map.set(b.id, b.material_categories ?? []);
    return map;
  }, [bills]);

  const allDeadlines = useMemo(
    () =>
      scopeActive
        ? mergedDeadlines.filter(d =>
            deadlineInScope(d, scope, dl => (dl.bill_id != null ? billMaterials.get(dl.bill_id) : null)),
          )
        : mergedDeadlines,
    [mergedDeadlines, scopeActive, scope, billMaterials],
  );

  // Timeline shows only upcoming deadlines (today onward), regardless of the include-past toggle.
  const timelineDeadlines = useMemo(
    () => allDeadlines.filter(d => { const n = daysUntil(d.deadline_date); return n !== null && n >= 0; }),
    [allDeadlines],
  );

  const within30 = allDeadlines.filter(d => { const n = daysUntil(d.deadline_date); return n !== null && n >= 0 && n <= 30; }).length;
  const within90 = allDeadlines.filter(d => { const n = daysUntil(d.deadline_date); return n !== null && n >= 0 && n <= 90; }).length;
  const nextDeadline = allDeadlines.find(d => { const n = daysUntil(d.deadline_date); return n !== null && n >= 0; });

  // The bill behind the selected deadline (if it's in the loaded set) powers the modal.
  const selectedBill = useMemo(
    () => (selected?.bill_id != null ? bills.find(b => b.id === selected.bill_id) ?? null : null),
    [selected, bills],
  );

  // CSV export is a Pro feature: gatePro routes anon → sign-in, Free → checkout, Pro → the download.
  function handleExport() {
    gatePro(() => downloadCsv('signalscout_deadlines.csv', allDeadlines.map(d => ({
      State: d.state,
      Type: d.deadline_type,
      Date: d.deadline_date,
      Description: d.description ?? '',
      Bill: d.bill_number ?? '',
      'Who Affected': d.who_affected ?? '',
    }))));
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <GazetteHeader title="Upcoming Deadlines" subtitle="EPR compliance deadlines across all states" />

      {scopeActive && (
        <p className="text-xs text-text-muted -mt-2">
          Filtered to your scope
          {scope.materials.length > 0 && (
            <> · <span className="text-text-secondary">{scope.materials.map(formatMaterial).join(', ')}</span></>
          )}
          {scope.states.length > 0 && (
            <> · <span className="text-text-secondary">{scope.states.join(', ')}</span></>
          )}
          . Use “Show everything” above to see all deadlines.
        </p>
      )}

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total Deadlines" value={allDeadlines.length} accent />
        <MetricCard label="Within 30 Days" value={within30} sublabel={within30 > 0 ? 'Action required' : 'None urgent'} />
        <MetricCard label="Within 90 Days" value={within90} />
        <MetricCard label="Next Deadline" value={nextDeadline ? formatDate(nextDeadline.deadline_date) : 'None'} />
      </div>

      {within30 > 0 && (
        <AlertBanner variant="red" message={`${within30} deadline(s) within the next 30 days require immediate attention.`} />
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
            {[
              { v: 90, l: '90 days' },
              { v: 180, l: '6 months' },
              { v: 365, l: '1 year' },
              { v: 730, l: '2 years' },
              { v: 1095, l: '3 years' },
            ].map(o => (
              <option key={o.v} value={o.v}>{o.l}</option>
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
          <button
            onClick={handleExport}
            title={isPro ? undefined : 'CSV export is a Pro feature'}
            className="text-sm text-green-accent hover:underline inline-flex items-center gap-1.5"
          >
            {!isPro && <LockIcon className="text-xs" />}
            ↓ Export CSV
            {!isPro && (
              <span className="text-[10px] uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-1.5 py-px no-underline">
                Pro
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Timeline */}
      {timelineDeadlines.length > 0 && (
        <div>
          <SectionHeader title={`Timeline — next 3 years (${timelineDeadlines.length})`} />
          <DeadlineTimeline deadlines={timelineDeadlines} onSelect={setSelected} />
        </div>
      )}

      {/* Deadline list — brief headlines; tap any to open its detail */}
      <div>
        <SectionHeader title={`Deadlines (${allDeadlines.length})`} />
        {isLoading ? (
          <div className="space-y-2">{[...Array(5)].map((_, i) => <div key={i} className="h-12 bg-bg-secondary rounded-lg animate-pulse" />)}</div>
        ) : allDeadlines.length === 0 ? (
          <div className="text-center text-text-muted py-12">No deadlines found for the selected filters.</div>
        ) : (
          <div className="space-y-2">
            {allDeadlines.map((d, i) => <DeadlineRow key={`${d.id}-${i}`} deadline={d} onSelect={setSelected} />)}
          </div>
        )}
      </div>

      <DeadlineModal deadline={selected} bill={selectedBill} onClose={() => setSelected(null)} />
    </div>
  );
}
