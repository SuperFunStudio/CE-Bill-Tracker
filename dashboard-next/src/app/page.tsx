'use client';
import { useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useBills } from '@/hooks/useBills';
import { useDeadlines } from '@/hooks/useDeadlines';
import { useFederalActions, useLitigationCases } from '@/hooks/useFederal';
import { MetricCard } from '@/components/ui/MetricCard';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { SectionHeader } from '@/components/ui/SectionHeader';
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

  const mapData = useMemo(() => {
    let filtered = bills;
    if (billFilters.enactedOnly) filtered = filtered.filter(b => b.status === 'enacted');
    if (billFilters.instrumentType) filtered = filtered.filter(b => b.instrument_type === billFilters.instrumentType);
    const counts: Record<string, number> = {};
    filtered.forEach(b => { counts[b.state] = (counts[b.state] ?? 0) + 1; });
    return counts;
  }, [bills, billFilters.enactedOnly, billFilters.instrumentType]);

  const topStates = useMemo(() =>
    Object.entries(mapData).sort((a, b) => b[1] - a[1]).slice(0, 5),
    [mapData]
  );

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
    <div className="p-6 space-y-6">
      {/* Hero */}
      <div className="rounded-xl p-8 border border-green-accent/30 bg-green-hero">
        <h1 className="text-3xl font-bold text-text-primary mb-2">Signal Dashboard</h1>
        <p className="text-text-secondary text-lg">
          US EPR legislative intelligence — monitoring all 50 states + DC across 10+ material categories
        </p>
      </div>

      {/* Federal Preemption Alert */}
      <AlertBanner
        variant="amber"
        message={
          highPreemption > 0
            ? `⚠ Federal Preemption Watch: ${highPreemption} high-risk federal action(s) tracked. The Oregon NAW constitutional challenge (trial July 13, 2026) could set precedent for Dormant Commerce Clause attacks on all state packaging EPR programs.`
            : '⚠ Federal Preemption Watch: The Oregon NAW case (trial July 13, 2026) could set precedent for Dormant Commerce Clause attacks on all state packaging EPR programs. Monitor the Federal Actions page for updates.'
        }
      />

      {/* Bill Explorer — filters + map */}
      <div>
        <h2 className="text-lg font-semibold text-text-primary mb-3">Bill Explorer</h2>

        <BillFilters filters={billFilters} onChange={setBillFilters} showEprToggle />

        <div className="mt-4">
          <StateMap
            data={mapData}
            selectedState={billFilters.state || null}
            onStateClick={abbr => setBillFilters(prev => ({ ...prev, state: prev.state === abbr ? '' : abbr }))}
            height={380}
          />
        </div>

        {billFilters.state && (
          <div className="mt-2 text-sm text-text-muted">
            Showing <span className="text-green-accent font-medium">{STATE_NAMES[billFilters.state] ?? billFilters.state}</span>
            {' — '}
            <button onClick={() => setBillFilters(prev => ({ ...prev, state: '' }))} className="underline hover:text-text-secondary">clear</button>
          </div>
        )}

        {/* Top States widget — shown when no state selected */}
        {!billFilters.state && topStates.length > 0 && (
          <div className="mt-4">
            <div className="text-text-muted text-xs uppercase tracking-wider mb-3">Most Active States</div>
            <div className="grid grid-cols-5 gap-3">
              {topStates.map(([abbr, count]) => (
                <button
                  key={abbr}
                  onClick={() => setBillFilters(prev => ({ ...prev, state: abbr }))}
                  className="bg-bg-secondary border border-border-default rounded-lg p-3 text-center hover:border-green-accent/50 transition-colors"
                >
                  <div className="text-green-accent font-bold text-lg">{abbr}</div>
                  <div className="text-text-muted text-xs">{count} bills</div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Metrics */}
      <div className="hidden sm:grid grid-cols-5 gap-4">
        <MetricCard label="Enacted EPR Laws" value={billsLoading ? '…' : enactedCount} sublabel={`${packagingStates} packaging EPR states`} accent />
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

      {/* Bill Tracker */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-baseline gap-3">
            <SectionHeader title="Bill Tracker" />
            <span className="text-text-muted text-sm">{tableBills.length} bills</span>
          </div>
          <button
            onClick={handleExport}
            disabled={tableBills.length === 0}
            className="text-sm text-green-accent hover:underline disabled:text-text-muted disabled:no-underline"
          >
            ↓ Export CSV
          </button>
        </div>

        {billsError && <AlertBanner variant="red" message="⚠ Could not load bill data. Ensure the API is running." className="mt-3" />}
        {billsLoading ? (
          <div className="space-y-2 mt-4">{[...Array(5)].map((_, i) => <div key={i} className="h-12 bg-bg-secondary rounded animate-pulse" />)}</div>
        ) : (
          <div className="mt-4">
            <BillTable bills={tableBills} maxRows={50} />
          </div>
        )}
      </div>

      {/* Quick nav */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
        {[
          { href: '/compliance', label: '📅 Upcoming Deadlines', desc: 'Compliance deadlines' },
          { href: '/federal', label: '🏛️ Federal Actions', desc: 'Federal Register + litigation' },
          { href: '/company', label: '🏭 Company Impact', desc: 'Exposure scoring & briefs' },
        ].map(({ href, label, desc }) => (
          <Link key={href} href={href} className="bg-bg-secondary border border-border-default rounded-lg p-4 hover:border-green-accent/50 transition-colors">
            <div className="font-medium text-text-primary text-sm">{label}</div>
            <div className="text-text-muted text-xs mt-1">{desc}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
