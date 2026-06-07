'use client';
import { useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useBills } from '@/hooks/useBills';
import { useDeadlines } from '@/hooks/useDeadlines';
import { useFederalActions, useLitigationCases } from '@/hooks/useFederal';
import { MetricCard } from '@/components/ui/MetricCard';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { FederalWatchBanner } from '@/components/ui/FederalWatchBanner';
import { Masthead } from '@/components/ui/Masthead';
import { StatesTicker } from '@/components/ui/StatesTicker';
import { BillTable } from '@/components/bills/BillTable';
import { BillFilters, DEFAULT_FILTERS, applyBillFilters, type BillFilterState } from '@/components/bills/BillFilters';
import { STATE_NAMES, formatDate, downloadCsv } from '@/lib/utils';
import Link from 'next/link';

const StateMap = dynamic(
  () => import('@/components/map/StateMap').then(m => ({ default: m.StateMap })),
  { ssr: false, loading: () => <div className="h-80 bg-bg-secondary rounded-lg animate-pulse" /> }
);

export default function HomePage() {
  const [billFilters, setBillFilters] = useState<BillFilterState>(DEFAULT_FILTERS);

  const { data: bills = [], isLoading: billsLoading, error: billsError } = useBills({ epr_relevant: true, limit: 500 });
  const { data: deadlines = [] } = useDeadlines({ days_ahead: 365 });
  const { data: federal = [] } = useFederalActions({ limit: 50 });
  const { data: litigationCases = [] } = useLitigationCases();

  const enactedCount = useMemo(() => bills.filter(b => b.status === 'enacted').length, [bills]);
  const activeStates = useMemo(() => new Set(bills.map(b => b.state)).size, [bills]);
  const materialCount = useMemo(() => {
    const cats = new Set<string>();
    bills.forEach(b => (b.material_categories ?? []).forEach(c => cats.add(c)));
    return cats.size;
  }, [bills]);
  const packagingStates = useMemo(() => {
    const pkgCats = new Set(['plastic_packaging', 'paper_packaging', 'packaging']);
    const states = new Set<string>();
    bills.forEach(b => {
      if (b.status === 'enacted') {
        const cats = new Set(b.material_categories ?? []);
        if ([...cats].some(c => pkgCats.has(c))) states.add(b.state);
      }
    });
    return states.size;
  }, [bills]);
  const highPreemption = useMemo(() => federal.filter(f => f.preemption_risk === 'High').length, [federal]);
  const activeLitigation = useMemo(() => litigationCases.filter(c => c.case_status === 'active').length, [litigationCases]);

  // Map honors every active filter EXCEPT state, so all states stay visible/clickable.
  const mapData = useMemo(() => {
    const filtered = applyBillFilters(bills, { ...billFilters, state: '' });
    const counts: Record<string, number> = {};
    filtered.forEach(b => { counts[b.state] = (counts[b.state] ?? 0) + 1; });
    return counts;
  }, [bills, billFilters]);

  const tableBills = useMemo(() => applyBillFilters(bills, billFilters), [bills, billFilters]);

  function handleExport() {
    downloadCsv('signalscout_bills.csv', tableBills.map(b => ({
      State: b.state,
      Bill: b.bill_number ?? '',
      Title: b.title ?? '',
      Status: b.status ?? '',
      Urgency: b.urgency ?? '',
      Instrument: b.instrument_type ?? '',
      Materials: (b.material_categories ?? []).join('; '),
      'Last Action': formatDate(b.last_action_date),
      'Source URL': b.source_url ?? '',
    })));
  }

  return (
    <div className="p-6 space-y-8 max-w-6xl">
      {/* Masthead — gazette, condenses on scroll */}
      <Masthead />

      {/* Top-states leaderboard line, right under the subhead */}
      <StatesTicker
        data={mapData}
        onStateClick={abbr => setBillFilters(prev => ({ ...prev, state: prev.state === abbr ? '' : abbr }))}
      />

      {/* Map */}
      <section>
        <StateMap
          data={mapData}
          selectedState={billFilters.state || null}
          onStateClick={abbr => setBillFilters(prev => ({ ...prev, state: prev.state === abbr ? '' : abbr }))}
          height={380}
        />
      </section>

      {/* 2 ── Bill Explorer: filters + auto-advancing results */}
      <section>
        <div className="flex items-baseline justify-between mb-3 gap-3">
          <div className="flex items-baseline gap-3">
            <h2 className="font-serif text-2xl text-text-primary">Bill Explorer</h2>
            <span className="text-text-muted text-sm">{tableBills.length} bills</span>
          </div>
          <button
            onClick={handleExport}
            disabled={tableBills.length === 0}
            className="text-sm text-green-accent hover:underline disabled:text-text-muted disabled:no-underline shrink-0"
          >
            ↓ Export CSV
          </button>
        </div>

        <BillFilters filters={billFilters} onChange={setBillFilters} />

        {billFilters.state && (
          <div className="mt-2 text-sm text-text-muted">
            Showing <span className="text-green-accent font-medium">{STATE_NAMES[billFilters.state] ?? billFilters.state}</span>
            {' — '}
            <button onClick={() => setBillFilters(prev => ({ ...prev, state: '' }))} className="underline hover:text-text-secondary">clear</button>
          </div>
        )}

        {billsError && <AlertBanner variant="red" message="⚠ Could not load bill data. Ensure the API is running." className="mt-3" />}
        {billsLoading ? (
          <div className="space-y-2 mt-4">{[...Array(5)].map((_, i) => <div key={i} className="h-12 bg-bg-secondary rounded animate-pulse" />)}</div>
        ) : (
          <div className="mt-4">
            <BillTable bills={tableBills} autoPageSize={5} />
          </div>
        )}
      </section>

      {/* 3 ── Federal watch (pithy, dismissible) */}
      <FederalWatchBanner highRiskCount={highPreemption} />

      {/* Metrics */}
      <div className="hidden sm:grid grid-cols-5 gap-4">
        <MetricCard label="Enacted Laws" value={billsLoading ? '…' : enactedCount} sublabel={`${packagingStates} packaging EPR states`} accent />
        <MetricCard label="States With Activity" value={billsLoading ? '…' : activeStates} sublabel="across all instrument types" />
        <MetricCard label="Material Categories" value={billsLoading ? '…' : materialCount} sublabel="packaging · e-waste · batteries · more" />
        <MetricCard label="Upcoming Deadlines" value={deadlines.length} sublabel="within next 365 days" />
        <MetricCard label="Active Litigation" value={activeLitigation} sublabel="judicial challenges tracked" />
      </div>
      <div className="grid sm:hidden grid-cols-3 gap-2">
        <MetricCard label="Enacted" value={billsLoading ? '…' : enactedCount} accent compact />
        <MetricCard label="States" value={billsLoading ? '…' : activeStates} compact />
        <MetricCard label="Deadlines" value={deadlines.length} compact />
      </div>

      {/* Quick nav */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {[
          { href: '/compliance', label: 'Upcoming Deadlines', desc: 'Compliance deadlines' },
          { href: '/federal', label: 'Federal Actions', desc: 'Federal Register + litigation' },
          { href: '/company', label: 'Company Impact', desc: 'Exposure scoring & briefs' },
        ].map(({ href, label, desc }) => (
          <Link key={href} href={href} className="bg-bg-secondary border border-border-default rounded-lg p-4 hover:border-green-accent/50 transition-colors">
            <div className="font-serif text-text-primary text-base">{label}</div>
            <div className="text-text-muted text-xs mt-1">{desc}</div>
          </Link>
        ))}
      </div>

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
    </div>
  );
}
