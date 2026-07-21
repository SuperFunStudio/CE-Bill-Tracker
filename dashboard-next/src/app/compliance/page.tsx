'use client';
import { useState, useMemo } from 'react';
import { useDeadlines, useDeadlineStats } from '@/hooks/useDeadlines';
import { useBill } from '@/hooks/useBills';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { DeadlineModal } from '@/components/compliance/DeadlineModal';
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

// Past deadlines are capped to the last 5 years — the historical EPR backfill carries laws back to the
// 1990s, whose compliance dates aren't actionable.
const PAST_DEADLINE_CUTOFF_DAYS = 5 * 365;
// "Later" (>90 days out) can run to hundreds of rows; show a slice, then reveal the rest on request.
const LATER_PREVIEW = 25;

const MONTH_LETTERS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

/** Plain-language relative time for a deadline date. */
function relDays(dateStr: string | null): string | null {
  const n = daysUntil(dateStr);
  if (n === null) return null;
  if (n === 0) return 'today';
  if (n > 0) return `in ${n} day${n === 1 ? '' : 's'}`;
  return `${-n} day${n === -1 ? '' : 's'} ago`;
}

/** The action a row is really asking for — the specific requirement, then the bill, then the type. */
function headlineFor(d: DeadlineSummary): string {
  return d.description || d.bill_title || `${d.deadline_type} deadline`.replace(/_/g, ' ');
}

// Urgency lives in the grouping, not a per-row rainbow: one tone per band.
type Tone = 'over' | 'soon' | 'later';
const BANDS: { key: string; label: string; tone: Tone; test: (n: number | null) => boolean }[] = [
  { key: 'overdue', label: 'Overdue',      tone: 'over',  test: n => n !== null && n < 0 },
  { key: 'soon',    label: 'Next 30 days', tone: 'soon',  test: n => n !== null && n >= 0 && n <= 30 },
  { key: 'quarter', label: 'Next 90 days', tone: 'later', test: n => n !== null && n > 30 && n <= 90 },
  { key: 'later',   label: 'Later',        tone: 'later', test: n => n === null || n > 90 },
];
const TONE: Record<Tone, { tag: string; date: string }> = {
  over:  { tag: 'text-urgency-high',   date: 'text-urgency-high' },
  soon:  { tag: 'text-urgency-medium', date: 'text-text-primary' },
  later: { tag: 'text-text-muted',     date: 'text-text-primary' },
};

export default function CompliancePage() {
  const [daysAhead, setDaysAhead] = useState(1095);
  const [stateFilter, setStateFilter] = useState('');
  const [includePast, setIncludePast] = useState(false);
  const [showAllLater, setShowAllLater] = useState(false);
  const [selected, setSelected] = useState<DeadlineSummary | null>(null);

  const { scope } = useScope();
  const scopeActive = useScopeActive();
  const { isPro, isAdmin, loading } = useAuth();
  const gatePro = useProGate();
  const proView = isPro || isAdmin;

  // The list is gated server-side: Pro → full merged calendar (spans up to 5y of past dates too),
  // free → the soonest few rows. Pass scope only on the free path so the teaser stays relevant.
  const scopeMaterials = scopeActive && scope.materials.length ? scope.materials.join(',') : undefined;
  const scopeStates = scopeActive && scope.states.length ? scope.states.join(',') : undefined;
  const { data: deadlines = [], isLoading } = useDeadlines({
    days_ahead: daysAhead,
    state: stateFilter || undefined,
    materials: proView ? undefined : scopeMaterials,
    states: proView ? undefined : scopeStates,
  });
  const { data: stats } = useDeadlineStats({
    days_ahead: daysAhead,
    state: stateFilter || undefined,
    materials: scopeMaterials,
    states: scopeStates,
  });

  // The bill behind the selected deadline powers the modal's full detail (fetched on demand).
  const { data: selectedBill } = useBill(selected?.bill_id ?? null);

  // Scope first (materials live on the linked bill, denormalized onto the row), then windows.
  const scoped = useMemo(
    () => (scopeActive ? deadlines.filter(d => deadlineInScope(d, scope, dl => dl.material_categories)) : deadlines),
    [deadlines, scopeActive, scope],
  );

  // Overdue is surfaced even when "include past" is off (the Pro fetch already carries recent past dates),
  // so an overdue obligation never hides — it's the loudest thing on the page.
  const overdueCount = useMemo(
    () => scoped.filter(d => { const n = daysUntil(d.deadline_date); return n !== null && n < 0 && n >= -PAST_DEADLINE_CUTOFF_DAYS; }).length,
    [scoped],
  );

  // The display set: horizon + include-past window, sorted soonest-first.
  const windowed = useMemo(
    () =>
      scoped
        .filter(d => {
          const days = daysUntil(d.deadline_date);
          if (!includePast && days !== null && days < 0) return false;
          if (includePast && days !== null && days < -PAST_DEADLINE_CUTOFF_DAYS) return false;
          if (days !== null && days > daysAhead) return false;
          return true;
        })
        .slice()
        .sort((a, b) => a.deadline_date.localeCompare(b.deadline_date)),
    [scoped, includePast, daysAhead],
  );

  // Group into urgency bands (the grouping IS the signal).
  const bands = useMemo(
    () =>
      BANDS.map(band => ({
        ...band,
        items: windowed.filter(d => band.test(daysUntil(d.deadline_date))),
      })).filter(b => b.items.length > 0),
    [windowed],
  );

  // The one glance-chart: deadline density over the next 12 months, single hue.
  const rail = useMemo(() => {
    const now = new Date();
    const buckets = Array.from({ length: 12 }, (_, i) => {
      const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
      return { key: `${d.getFullYear()}-${d.getMonth()}`, letter: MONTH_LETTERS[d.getMonth()], count: 0 };
    });
    const idx = new Map(buckets.map((b, i) => [b.key, i]));
    for (const d of windowed) {
      const dt = new Date(d.deadline_date);
      const i = idx.get(`${dt.getFullYear()}-${dt.getMonth()}`);
      if (i != null) buckets[i].count++;
    }
    return buckets;
  }, [windowed]);
  const railMax = Math.max(1, ...rail.map(b => b.count));
  const railTotal = rail.reduce((s, b) => s + b.count, 0);

  const totalUpcoming = stats?.total_upcoming ?? 0;
  const shownCount = windowed.length;
  const lockedRemaining = Math.max(0, totalUpcoming - shownCount);
  const nextRel = relDays(stats?.next_date ?? null);

  function handleExport() {
    gatePro(() => downloadCsv('signalscout_deadlines.csv', windowed.map(d => ({
      State: d.state,
      Type: d.deadline_type,
      Date: d.deadline_date,
      Description: d.description ?? '',
      Bill: d.bill_number ?? '',
      'Who Affected': d.who_affected ?? '',
    }))), 'csv_export_deadlines');
  }

  const controlCls = 'bg-bg-primary border border-border-default rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-green-accent';

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <GazetteHeader title="Upcoming Deadlines" subtitle="What you must do, and by when." />

      {/* One honest summary line — replaces the four metric tiles. */}
      <p className="text-body text-text-secondary">
        <span className="text-text-primary font-semibold">{totalUpcoming}</span> deadline{totalUpcoming === 1 ? '' : 's'} ahead
        {nextRel && <> · next <span className="text-text-primary font-semibold">{nextRel}</span></>}
        {(stats?.within_30 ?? 0) > 0 && <> · <span className="text-urgency-medium font-semibold">{stats?.within_30} within 30 days</span></>}
        {overdueCount > 0 && <> · <span className="text-urgency-high font-semibold">{overdueCount} overdue</span></>}
      </p>

      {/* Quiet inline controls — no boxed filter panel. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="flex items-center gap-1.5 text-xs text-text-muted uppercase tracking-wider">
          Horizon
          <select value={daysAhead} onChange={e => setDaysAhead(Number(e.target.value))} className={controlCls}>
            {[{ v: 90, l: '90 days' }, { v: 180, l: '6 months' }, { v: 365, l: '1 year' }, { v: 730, l: '2 years' }, { v: 1095, l: '3 years' }].map(o => (
              <option key={o.v} value={o.v}>{o.l}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-xs text-text-muted uppercase tracking-wider">
          State
          <select value={stateFilter} onChange={e => setStateFilter(e.target.value)} className={controlCls}>
            <option value="">All</option>
            {Object.entries(STATE_NAMES).map(([a, n]) => <option key={a} value={a}>{a} — {n}</option>)}
          </select>
        </label>
        {proView && (
          <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary">
            <input type="checkbox" checked={includePast} onChange={e => setIncludePast(e.target.checked)} className="accent-green-accent" />
            Include past
          </label>
        )}
        <button
          onClick={handleExport}
          title={isPro ? undefined : 'CSV export is a Pro feature'}
          className="ml-auto text-sm text-green-accent hover:underline inline-flex items-center gap-1.5"
        >
          {!isPro && <LockIcon className="text-xs" />}
          ↓ Export CSV
          {!isPro && (
            <span className="text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-1.5 py-px no-underline">Pro</span>
          )}
        </button>
      </div>

      {scopeActive && (
        <p className="text-xs text-text-muted -mt-2">
          Filtered to your scope
          {scope.materials.length > 0 && <> · <span className="text-text-secondary">{scope.materials.map(formatMaterial).join(', ')}</span></>}
          {scope.states.length > 0 && <> · <span className="text-text-secondary">{scope.states.join(', ')}</span></>}
          . Use “Show everything” in the scope bar to see all deadlines.
        </p>
      )}

      {/* The one glance-chart: shape of the year (Pro; the full calendar). */}
      {proView && railTotal > 0 && (
        <div className="grid grid-cols-12 gap-1 items-end h-14 border-b border-border-default pb-1" aria-label="Deadline density by month over the next year">
          {rail.map((b, i) => (
            <div key={i} className="flex flex-col items-center justify-end gap-1 h-full" title={`${b.count} deadline${b.count === 1 ? '' : 's'}`}>
              <div
                className="w-full max-w-[24px] rounded-t-sm bg-green-accent/50"
                style={{ height: `${b.count ? Math.max(6, (b.count / railMax) * 100) : 0}%` }}
              />
              <span className="text-meta text-text-muted font-mono">{b.letter}</span>
            </div>
          ))}
        </div>
      )}

      {/* The agenda — grouped by urgency, time-ordered. */}
      {(isLoading || loading) ? (
        <SkeletonList rows={6} />
      ) : windowed.length === 0 ? (
        <EmptyState title="No deadlines found for the selected filters." />
      ) : (
        <div className="space-y-7">
          {bands.map(band => {
            const isLater = band.key === 'later';
            const items = isLater && !showAllLater ? band.items.slice(0, LATER_PREVIEW) : band.items;
            const tone = TONE[band.tone];
            return (
              <section key={band.key}>
                <div className="flex items-baseline gap-3 mb-2">
                  <h2 className={`font-mono text-xs uppercase tracking-widest font-semibold ${tone.tag}`}>{band.label}</h2>
                  <span className="text-xs text-text-muted">{band.items.length}</span>
                  {band.key === 'overdue' && <span className="text-xs text-urgency-high">act now</span>}
                </div>
                <div className="divide-y divide-border-default border-y border-border-default">
                  {items.map((d, i) => {
                    const rel = relDays(d.deadline_date);
                    const who = [d.who_affected, [d.state, d.bill_number].filter(Boolean).join(' ')].filter(Boolean).join(' · ');
                    return (
                      <button
                        key={`${d.id}-${i}`}
                        type="button"
                        onClick={() => setSelected(d)}
                        className="w-full text-left grid grid-cols-[6.5rem_1fr_auto] items-center gap-x-4 gap-y-0.5 py-2.5 hover:bg-bg-secondary transition-colors"
                      >
                        <span className={`font-mono text-sm font-semibold ${tone.date}`}>
                          {formatDate(d.deadline_date)}
                          {rel && <span className={`block text-meta font-normal ${tone.tag}`}>{rel}</span>}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm text-text-primary truncate">{headlineFor(d)}</span>
                          {who && <span className="block text-xs text-text-muted truncate">{who}</span>}
                        </span>
                        <span className="font-mono text-xs text-text-secondary border border-border-default rounded px-1.5 py-0.5 shrink-0">{d.state}</span>
                      </button>
                    );
                  })}
                </div>
                {isLater && band.items.length > LATER_PREVIEW && (
                  <button
                    type="button"
                    onClick={() => setShowAllLater(v => !v)}
                    className="mt-2 text-sm text-green-accent hover:underline"
                  >
                    {showAllLater ? 'Show fewer' : `Show all ${band.items.length} →`}
                  </button>
                )}
              </section>
            );
          })}
        </div>
      )}

      {/* Free visitors: the unlock card sits below the teaser rows. */}
      {!loading && !proView && <UpcomingDeadlinesLock lockedCount={lockedRemaining} />}

      {/* Self-serve "which laws apply to my products?" — a different job from the calendar, so it's
          tucked into a disclosure rather than competing with the deadline agenda above. */}
      <details className="rounded-lg border border-border-default bg-bg-secondary">
        <summary className="cursor-pointer px-4 py-3 text-sm text-text-secondary">
          Not sure what applies to you? Check which laws hit your products →
        </summary>
        <div className="px-4 pb-4">
          <ComplianceChecker />
        </div>
      </details>

      <DeadlineModal deadline={selected} bill={selectedBill ?? null} onClose={() => setSelected(null)} />
    </div>
  );
}
