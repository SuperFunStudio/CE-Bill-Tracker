'use client';
import { useState, useMemo } from 'react';
import { useDeadlines, useDeadlineStats } from '@/hooks/useDeadlines';
import { useBill } from '@/hooks/useBills';
import { MetricCard } from '@/components/ui/MetricCard';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { DeadlineTimeline } from '@/components/compliance/DeadlineTimeline';
import { DeadlineModal } from '@/components/compliance/DeadlineModal';
import { deadlineAccentText } from '@/lib/deadlineStyle';
import { useScope, useScopeActive } from '@/components/scope/ScopeContext';
import { useAuth, useProGate } from '@/components/auth/AuthContext';
import { UpcomingDeadlinesLock } from '@/components/compliance/UpcomingDeadlinesLock';
import { ComplianceChecker } from '@/components/compliance/ComplianceChecker';
import { LockIcon } from '@/components/ui/icons';
import { deadlineInScope } from '@/lib/scope';
import { formatMaterial } from '@/components/scope/ScopeOnboarding';
import { formatDate, daysUntil, downloadCsv, STATE_NAMES } from '@/lib/utils';
import type { DeadlineSummary } from '@/lib/types';
import { SkeletonList } from '@/components/ui/SkeletonList';
import { EmptyState } from '@/components/ui/EmptyState';

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

  const { scope } = useScope();
  const scopeActive = useScopeActive();
  const { isPro, isAdmin, loading } = useAuth();
  const gatePro = useProGate();

  // A live Pro seat (or admin) sees the full calendar; everyone else gets the server-capped teaser.
  const proView = isPro || isAdmin;

  // The list itself is gated server-side: Pro → full merged calendar, free → soonest few rows. We pass
  // the reader's scope only for the free path (so the teaser is relevant); Pro gets everything and
  // filters client-side, which keeps the "show everything" toggle instant (no refetch).
  const scopeMaterials = scopeActive && scope.materials.length ? scope.materials.join(',') : undefined;
  const scopeStates = scopeActive && scope.states.length ? scope.states.join(',') : undefined;
  const { data: deadlines = [], isLoading } = useDeadlines({
    days_ahead: daysAhead,
    state: stateFilter || undefined,
    materials: proView ? undefined : scopeMaterials,
    states: proView ? undefined : scopeStates,
  });

  // Ungated counts drive the metric cards (and the locked-remaining math) for free + Pro alike.
  const { data: stats } = useDeadlineStats({
    days_ahead: daysAhead,
    state: stateFilter || undefined,
    materials: scopeMaterials,
    states: scopeStates,
  });

  // The bill behind the selected deadline powers the modal's full detail (fetched on demand; the bulk
  // list no longer carries compliance_details).
  const { data: selectedBill } = useBill(selected?.bill_id ?? null);

  // Client-side window filter (Pro list spans up to 5y of past dates so this toggle works without a
  // refetch; the free teaser is already upcoming-only so this is a no-op there).
  const windowed = useMemo(
    () =>
      deadlines.filter(d => {
        const days = daysUntil(d.deadline_date);
        if (!includePast && days !== null && days < 0) return false;
        if (includePast && days !== null && days < -PAST_DEADLINE_CUTOFF_DAYS) return false;
        if (days !== null && days > daysAhead) return false;
        return true;
      }),
    [deadlines, includePast, daysAhead],
  );

  // Default to the reader's scope (materials live on the deadline's linked bill, denormalized onto the
  // row). The global "Show everything" toggle in the ScopeBar turns this off.
  const allDeadlines = useMemo(
    () =>
      scopeActive
        ? windowed.filter(d => deadlineInScope(d, scope, dl => dl.material_categories))
        : windowed,
    [windowed, scopeActive, scope],
  );

  // Timeline shows only upcoming deadlines (today onward). Pro-only — it's the full-calendar view.
  const timelineDeadlines = useMemo(
    () => allDeadlines.filter(d => { const n = daysUntil(d.deadline_date); return n !== null && n >= 0; }),
    [allDeadlines],
  );

  const totalUpcoming = stats?.total_upcoming ?? 0;
  const lockedRemaining = Math.max(0, totalUpcoming - allDeadlines.length);

  // CSV export is a Pro feature: gatePro routes anon → sign-in, Free → checkout, Pro → the download.
  function handleExport() {
    gatePro(() => downloadCsv('signalscout_deadlines.csv', allDeadlines.map(d => ({
      State: d.state,
      Type: d.deadline_type,
      Date: d.deadline_date,
      Description: d.description ?? '',
      Bill: d.bill_number ?? '',
      'Who Affected': d.who_affected ?? '',
    }))), 'csv_export_deadlines');
  }

  return (
    <>
      <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <GazetteHeader title="Compliance" subtitle="Which laws apply to you, and your upcoming deadlines" />

      {/* Self-serve: pick your products → see applicable laws + next steps (region-aware, free). */}
      <ComplianceChecker />

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

      {/* Metrics — true aggregate counts (ungated), so free visitors see exactly what they're missing */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total Deadlines" value={totalUpcoming} accent />
        <MetricCard label="Within 30 Days" value={stats?.within_30 ?? 0} sublabel={(stats?.within_30 ?? 0) > 0 ? 'Action required' : 'None urgent'} />
        <MetricCard label="Within 90 Days" value={stats?.within_90 ?? 0} />
        <MetricCard label="Next Deadline" value={stats?.next_date ? formatDate(stats.next_date) : 'None'} />
      </div>

      {(stats?.within_30 ?? 0) > 0 && (
        <AlertBanner variant="red" message={`${stats?.within_30} deadline(s) within the next 30 days require immediate attention.`} />
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

        {proView && (
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary">
              <input type="checkbox" checked={includePast} onChange={e => setIncludePast(e.target.checked)} className="accent-green-accent" />
              Include past deadlines
            </label>
          </div>
        )}

        <div className="flex items-end ml-auto pb-1">
          <button
            onClick={handleExport}
            title={isPro ? undefined : 'CSV export is a Pro feature'}
            className="text-sm text-green-accent hover:underline inline-flex items-center gap-1.5"
          >
            {!isPro && <LockIcon className="text-xs" />}
            ↓ Export CSV
            {!isPro && (
              <span className="text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-1.5 py-px no-underline">
                Pro
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Timeline — Pro only (the full-calendar view) */}
      {proView && timelineDeadlines.length > 0 && (
        <div>
          <SectionHeader title={`Timeline — next 3 years (${timelineDeadlines.length})`} />
          <DeadlineTimeline deadlines={timelineDeadlines} onSelect={setSelected} />
        </div>
      )}

      {/* Deadline list — brief headlines; tap any to open its detail */}
      <div>
        <SectionHeader
          title={
            proView || totalUpcoming <= allDeadlines.length
              ? `Deadlines (${allDeadlines.length})`
              : `Deadlines (showing ${allDeadlines.length} of ${totalUpcoming})`
          }
        />
        {(isLoading || loading) ? (
          <SkeletonList rows={5} />
        ) : allDeadlines.length === 0 ? (
          <EmptyState title="No deadlines found for the selected filters." />
        ) : (
          <div className="space-y-2">
            {allDeadlines.map((d, i) => <DeadlineRow key={`${d.id}-${i}`} deadline={d} onSelect={setSelected} />)}
          </div>
        )}
      </div>

      {/* Free visitors: the unlock card sits right below the teaser rows (no full-page blur — the data
          they don't have was simply never sent). */}
      {!loading && !proView && <UpcomingDeadlinesLock lockedCount={lockedRemaining} />}

      <DeadlineModal deadline={selected} bill={selectedBill ?? null} onClose={() => setSelected(null)} />
      </div>
    </>
  );
}
