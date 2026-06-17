'use client';
import { useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useBills } from '@/hooks/useBills';
import { useFederalActions } from '@/hooks/useFederal';
import { SubscribeSection } from '@/components/about/SubscribeSection';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { FreshnessNote } from '@/components/ui/FreshnessNote';
import { FederalWatchBanner } from '@/components/ui/FederalWatchBanner';
import { StatesTicker } from '@/components/ui/StatesTicker';
import { BillTable } from '@/components/bills/BillTable';
import { BillFilters, DEFAULT_FILTERS, applyBillFilters, type BillFilterState } from '@/components/bills/BillFilters';
import { ScopedDeadlineBanner } from '@/components/scope/ScopedDeadlineBanner';
import { useScope, useScopeActive } from '@/components/scope/ScopeContext';
import { inScope } from '@/lib/scope';
import { useAuth, useProGate } from '@/components/auth/AuthContext';
import { LockIcon } from '@/components/ui/icons';
import { STATE_NAMES, formatDate, downloadCsv } from '@/lib/utils';
import Link from 'next/link';

const StateMap = dynamic(
  () => import('@/components/map/StateMap').then(m => ({ default: m.StateMap })),
  { ssr: false, loading: () => <div className="h-80 bg-bg-secondary rounded-lg animate-pulse" /> }
);

export default function HomePage() {
  const [billFilters, setBillFilters] = useState<BillFilterState>(DEFAULT_FILTERS);

  const { data: bills = [], isLoading: billsLoading, error: billsError } = useBills({ epr_relevant: true, limit: 5000 });
  const { data: federal = [] } = useFederalActions({ limit: 50 });

  const { scope } = useScope();
  const scopeActive = useScopeActive();

  const { isPro } = useAuth();
  const gatePro = useProGate();

  const highPreemption = useMemo(() => federal.filter(f => f.preemption_risk === 'High').length, [federal]);

  // When a scope is active, the table defaults to the reader's states + materials. The map applies
  // only the material side of the scope so every state stays visible/clickable (matching the
  // existing "map ignores state filter" behavior).
  const tableSource = useMemo(
    () => (scopeActive ? bills.filter(b => inScope(b, scope)) : bills),
    [bills, scopeActive, scope],
  );
  const mapSource = useMemo(
    () => (scopeActive ? bills.filter(b => inScope(b, { states: [], materials: scope.materials })) : bills),
    [bills, scopeActive, scope],
  );

  // Map honors every active filter EXCEPT state, so all states stay visible/clickable.
  const mapData = useMemo(() => {
    const filtered = applyBillFilters(mapSource, { ...billFilters, state: '' });
    const counts: Record<string, number> = {};
    filtered.forEach(b => { counts[b.state] = (counts[b.state] ?? 0) + 1; });
    return counts;
  }, [mapSource, billFilters]);

  const tableBills = useMemo(() => applyBillFilters(tableSource, billFilters), [tableSource, billFilters]);

  // CSV export is a Pro feature: gatePro routes anon → sign-in, Free → checkout, Pro → the download.
  function handleExport() {
    gatePro(() => downloadCsv('signalscout_bills.csv', tableBills.map(b => ({
      State: b.state,
      Bill: b.bill_number ?? '',
      Title: b.title ?? '',
      Status: b.status ?? '',
      Urgency: b.urgency ?? '',
      Instrument: b.instrument_type ?? '',
      Materials: (b.material_categories ?? []).join('; '),
      'Last Action': formatDate(b.last_action_date),
      'Source URL': b.source_url ?? '',
    }))), 'csv_export_bills');
  }

  return (
    <div className="p-6 space-y-8 max-w-6xl mx-auto">
      {/* Scoped deadline banner — "3 deadlines hitting your plastic packaging" (only when a scope is set) */}
      <ScopedDeadlineBanner bills={bills} />

      {/* Top-states leaderboard line, right under the nav */}
      <StatesTicker
        data={mapData}
        onStateClick={abbr => setBillFilters(prev => ({ ...prev, state: prev.state === abbr ? '' : abbr }))}
      />

      {/* Bill Explorer: search + filters sit above the map */}
      <section>
        <div className="flex items-baseline justify-between mb-3 gap-3">
          <div className="flex items-baseline gap-3 flex-wrap">
            <h2 className="font-serif text-2xl text-text-primary">Bill Explorer</h2>
            <span className="text-text-muted text-sm">{tableBills.length} bills</span>
            <FreshnessNote />
          </div>
          <button
            onClick={handleExport}
            disabled={tableBills.length === 0}
            title={isPro ? undefined : 'CSV export is a Pro feature'}
            className="text-sm text-green-accent hover:underline disabled:text-text-muted disabled:no-underline shrink-0 inline-flex items-center gap-1.5"
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

        <BillFilters filters={billFilters} onChange={setBillFilters} />

        {billFilters.state && (
          <div className="mt-2 text-sm text-text-muted">
            Showing <span className="text-green-accent font-medium">{STATE_NAMES[billFilters.state] ?? billFilters.state}</span>
            {' — '}
            <Link href={`/states/${billFilters.state.toLowerCase()}/`} className="underline hover:text-text-secondary">view {STATE_NAMES[billFilters.state] ?? billFilters.state} profile</Link>
            {' · '}
            <button onClick={() => setBillFilters(prev => ({ ...prev, state: '' }))} className="underline hover:text-text-secondary">clear</button>
          </div>
        )}
      </section>

      {/* Map */}
      <section>
        <StateMap
          data={mapData}
          selectedState={billFilters.state || null}
          onStateClick={abbr => setBillFilters(prev => ({ ...prev, state: prev.state === abbr ? '' : abbr }))}
          height={380}
        />
      </section>

      {/* Bill results table — below the map */}
      <section>
        {/* Only fires when live AND snapshot/localStorage all came up empty — otherwise
            last-known data shows with a quiet FreshnessNote instead of a scary banner. */}
        {billsError && <AlertBanner variant="red" message="We're having trouble loading bill data right now — please refresh in a moment." className="mb-3" />}
        {billsLoading ? (
          <div className="space-y-2">{[...Array(5)].map((_, i) => <div key={i} className="h-12 bg-bg-secondary rounded animate-pulse" />)}</div>
        ) : (
          <BillTable bills={tableBills} autoPageSize={5} />
        )}
      </section>

      {/* Federal watch (pithy, dismissible) */}
      <FederalWatchBanner highRiskCount={highPreemption} />

      {/* Portfolio Exposure front door — promote the paid translation from a buried tab */}
      <section className="rounded-xl border border-green-accent/30 bg-green-dark/20 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="max-w-xl">
          <h2 className="font-serif text-xl text-text-primary mb-1">See what this means for your portfolio</h2>
          <p className="text-text-secondary text-sm leading-relaxed">
            Translate the firehose into your exposure — which enacted laws hit your materials and
            states, what each one requires, and when your next deadline falls.
          </p>
        </div>
        <Link
          href="/company"
          className="shrink-0 rounded-lg bg-green-accent text-bg-primary font-semibold px-5 py-2.5 hover:opacity-90 transition-opacity text-center"
        >
          See your exposure →
        </Link>
      </section>

      {/* Get free updates */}
      <SubscribeSection className="border-t border-border-default pt-8" />

      {/* Federal preemption context — target of the banner's "Learn more" */}
      <section id="federal-context" className="scroll-mt-6 border-t border-border-default pt-6">
        <h2 className="font-serif text-2xl text-text-primary mb-2">Federal preemption watch</h2>
        <p className="text-text-secondary text-sm sm:text-base max-w-3xl leading-relaxed">
          The Oregon NAW constitutional challenge — trial <span className="text-text-primary font-medium">July 13, 2026</span> —
          argues that state packaging EPR programs violate the Dormant Commerce Clause. A ruling for the
          plaintiffs could set precedent for challenges to packaging laws in every state, which is why it&rsquo;s
          the single most important thing to watch this year.
          {highPreemption > 0 && (
            <> Right now <span className="text-text-primary font-medium">{highPreemption}</span> high-risk federal action(s) are tracked.</>
          )}
        </p>
        <Link href="/federal" className="inline-block mt-3 text-sm text-green-accent hover:underline">
          View Federal Actions &rarr;
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-border-default pt-6 pb-2 text-center">
        <Link href="/about" className="text-sm text-green-accent hover:underline">
          Learn more about the project &rarr;
        </Link>
      </footer>
    </div>
  );
}
