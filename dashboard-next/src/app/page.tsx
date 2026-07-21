'use client';
import { useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useBills, useBillTextSearch } from '@/hooks/useBills';
import { useFederalActions } from '@/hooks/useFederal';
import { SubscribeSection } from '@/components/about/SubscribeSection';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { FreshnessNote } from '@/components/ui/FreshnessNote';
import { FederalWatchBanner } from '@/components/ui/FederalWatchBanner';
import { StatesTicker } from '@/components/ui/StatesTicker';
import { BillTable } from '@/components/bills/BillTable';
import { BillFilters, DEFAULT_FILTERS, applyBillFilters, resinOptionsFromBills, type BillFilterState } from '@/components/bills/BillFilters';
import { SkeletonList } from '@/components/ui/SkeletonList';
import { ScopedDeadlineBanner } from '@/components/scope/ScopedDeadlineBanner';
import { ScopeBar } from '@/components/scope/ScopeBar';
import { useScope, useScopeActive } from '@/components/scope/ScopeContext';
import { useRegion } from '@/components/layout/RegionContext';
import { regionLabel } from '@/components/insights/RegionFilter';
import { highlightIdsFor } from '@/components/map/RegionInsetMap';
import { EU_MEMBERS } from '@/lib/jurisdictions';
import { inScope } from '@/lib/scope';
import { useAuth, useProGate } from '@/components/auth/AuthContext';
import { LockIcon } from '@/components/ui/icons';
import { STATE_NAMES, formatDate, downloadCsv } from '@/lib/utils';
import { useResearch, ResearchThread, ResearchWall, RESEARCH_EXAMPLES } from '@/components/research/ResearchThread';
import Link from 'next/link';

const StateMap = dynamic(
  () => import('@/components/map/StateMap').then(m => ({ default: m.StateMap })),
  { ssr: false, loading: () => <div className="h-80 bg-bg-secondary rounded-lg animate-pulse" /> }
);

const RegionInsetMap = dynamic(
  () => import('@/components/map/RegionInsetMap').then(m => ({ default: m.RegionInsetMap })),
  { ssr: false, loading: () => <div className="h-80 bg-bg-secondary rounded-lg animate-pulse" /> }
);

const CoverageStrip = dynamic(
  () => import('@/components/map/CoverageStrip').then(m => ({ default: m.CoverageStrip })),
  { ssr: false, loading: () => <div className="h-24 bg-bg-secondary rounded-lg animate-pulse" /> }
);

export default function HomePage() {
  const [billFilters, setBillFilters] = useState<BillFilterState>(DEFAULT_FILTERS);
  const { region, regionsParam, regions: selectedRegions, setRegions, isUsView } = useRegion();

  // The global region filter (under the nav) drives which jurisdictions the server returns. undefined
  // = "All regions" -> send "all" so the explorer shows every region (not the US-only default).
  // The compliance-dimension filter is applied server-side (compliance_details isn't in the list
  // payload), so it rides the fetch params rather than the client-side applyBillFilters below.
  const dimensionsCsv = billFilters.dimensions.length ? billFilters.dimensions.join(',') : undefined;
  const { data: bills = [], isLoading: billsLoading, error: billsError } = useBills({ ce_relevant: true, limit: 5000, regions: regionsParam ?? 'all', dimensions: dimensionsCsv });
  const { data: federal = [] } = useFederalActions({ limit: 50 });

  const { scope } = useScope();
  const scopeActive = useScopeActive();

  const { isPro, user, openAuth } = useAuth();
  const gatePro = useProGate();

  // The unified surface: one adaptive bar. Typing filters the table live (Explorer); submitting a
  // question routes to the grounded, cited research answer over the same corpus (Ask the Atlas).
  const research = useResearch();
  const [query, setQuery] = useState('');
  const submitQuery = () => {
    const q = query.trim();
    if (q.length < 3) return;
    research.ask(q);
    setQuery('');
    setBillFilters(prev => ({ ...prev, search: '' }));
  };
  const backToBrowsing = () => {
    research.newThread();
    setQuery('');
    setBillFilters(prev => ({ ...prev, search: '' }));
  };

  const highPreemption = useMemo(() => federal.filter(f => f.preemption_risk === 'High').length, [federal]);

  // Resin filter options come from the full bill set, so the choices are stable regardless of the
  // active scope/filters. Empty (and the filter stays hidden) until the polymer scan tags bills.
  const resinOptions = useMemo(() => resinOptionsFromBills(bills), [bills]);

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

  // Region-aware, ENACTED-ONLY leaderboard under the masthead. Enacted is the fair common
  // denominator across jurisdictions (the US introduced→enacted funnel has no EU analog). Mode
  // follows the region selection: no filter → umbrella regions (EU members collapse into EU);
  // US in scope → US states; an EU / EU-member selection → EU member states (so France defers to
  // the EU nation-state board); a lone non-EU country → no sub-jurisdiction board (hidden).
  const leaderboard = useMemo(() => {
    const enacted = applyBillFilters(mapSource, { ...billFilters, state: '', enactedOnly: true });
    const tally = (keyOf: (b: (typeof enacted)[number]) => string | null) => {
      const c: Record<string, number> = {};
      for (const b of enacted) { const k = keyOf(b); if (k) c[k] = (c[k] ?? 0) + 1; }
      return c;
    };
    if (selectedRegions.length === 0) {
      return { mode: 'regions' as const, label: 'Top Regions',
        data: tally(b => (b.region && b.region in EU_MEMBERS ? 'EU' : b.region || 'US')) };
    }
    if (selectedRegions.includes('US')) {
      return { mode: 'us-states' as const, label: 'Top States',
        data: tally(b => (b.region === 'US' && b.state ? b.state : null)) };
    }
    if (selectedRegions.includes('EU') || selectedRegions.some(r => r in EU_MEMBERS)) {
      return { mode: 'eu-members' as const, label: 'Top Member States',
        data: tally(b => (b.region && b.region in EU_MEMBERS ? b.region : null)) };
    }
    return { mode: 'none' as const, label: '', data: {} as Record<string, number> };
  }, [mapSource, billFilters, selectedRegions]);

  // Region-level counts for the world switcher bubbles. Reflects the currently-loaded set, so it's
  // complete on the default "all regions" landing (the moment the overview matters most); a single
  // active region filter narrows the fetch, which is fine since that region is the one in focus.
  const regionCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    mapSource.forEach(b => { if (b.region) counts[b.region] = (counts[b.region] ?? 0) + 1; });
    return counts;
  }, [mapSource]);

  // The map now *shows the selected region* rather than being a control. Exactly one region selected
  // → its cropped map (US states, the EU bloc, or a single-country locator). "All regions" (=[]) or a
  // multi-select → the coverage readout instead. highlightIds is empty for a code we have no geometry
  // for, in which case we fall back to a text focus panel.
  const soleRegion = selectedRegions.length === 1 ? selectedRegions[0] : null;
  const insetHighlightIds = soleRegion && soleRegion !== 'US' ? highlightIdsFor(soleRegion) : [];
  // A drilled-in EU member (e.g. clicked France on the bloc map) gets a "back to the EU bloc" crumb.
  const drilledEuMember = !!soleRegion && soleRegion !== 'EU' && soleRegion in EU_MEMBERS;

  // Full-text search: bills whose statute text matches the term (their title/summary may not). These
  // are merged into the one table below so search is just another filter — no separate results list.
  const { data: textHits = [] } = useBillTextSearch(billFilters.search);

  const tableBills = useMemo(() => {
    const base = applyBillFilters(tableSource, billFilters);
    const q = (billFilters.search ?? '').trim();
    if (q.length < 2 || textHits.length === 0) return base;
    // Append full-text-only hits: pass the non-search filters, drop any already shown.
    const baseIds = new Set(base.map(b => b.id));
    const extra = applyBillFilters(textHits, { ...billFilters, search: '' }).filter(
      (b) => !baseIds.has(b.id),
    );
    return extra.length ? [...base, ...extra] : base;
  }, [tableSource, billFilters, textHits]);

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
      Resins: (b.polymers ?? []).join('; '),
      'Last Action': formatDate(b.last_action_date),
      'Source URL': b.source_url ?? '',
    }))), 'csv_export_bills');
  }

  return (
    <div className="p-6 space-y-8 max-w-6xl mx-auto">
      {/* Above-the-fold value prop + primary CTA — signed-out visitors only, so the app view stays
          uncluttered for users who've already converted. The single loudest action is "start free". */}
      {!user && (
        <section className="rounded-xl border border-green-accent/30 bg-green-hero p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center justify-between gap-5">
          <div className="max-w-2xl">
            <h1 className="font-serif text-2xl sm:text-3xl text-text-primary leading-tight text-balance">
              A compliance deadline never slips past you when someone's already read every bill.
            </h1>
            <p className="mt-2 text-text-secondary text-body leading-relaxed">
              We track every circular-economy bill and EPR obligation across all 50 states — and pull out the dates and requirements so you don't have to.
              Start free — no card required.
            </p>
          </div>
          <div className="flex flex-col gap-2 shrink-0 sm:w-48">
            <button
              onClick={openAuth}
              className="rounded-lg bg-green-accent text-bg-primary font-semibold px-5 py-2.5 hover:opacity-90 transition-opacity"
            >
              Start free →
            </button>
            <Link
              href="/pricing"
              className="text-center text-meta text-text-secondary hover:text-text-primary transition-colors"
            >
              See plans &amp; pricing
            </Link>
          </div>
        </section>
      )}

      {/* Ranked leaderboard line, right under the nav. Region-aware + enacted-only: umbrella regions
          on "All regions", US states under a US selection, EU member states under an EU/member one
          (France defers here); hidden for a lone non-EU country with no sub-jurisdictions. */}
      {leaderboard.mode !== 'none' && (
        <StatesTicker
          label={leaderboard.label}
          data={leaderboard.data}
          // "The rest →" only means the US state standings board — don't offer it under the world/EU
          // leaderboards, where it wrongly dropped viewers onto the US-states page.
          restHref={leaderboard.mode === 'us-states' ? '/states' : undefined}
          onSelect={code =>
            leaderboard.mode === 'us-states'
              ? setBillFilters(prev => ({ ...prev, state: prev.state === code ? '' : code }))
              : setRegions([code])
          }
        />
      )}

      {/* Explore: one adaptive search/ask bar + facets, above the map */}
      <section>
        <div className="flex items-baseline justify-between mb-3 gap-3">
          <div className="flex items-baseline gap-3 flex-wrap">
            <h2 className="font-serif text-2xl text-text-primary">Explore</h2>
            <span className="text-text-muted text-sm">{tableBills.length} bills</span>
            <FreshnessNote />
          </div>
          {!research.active && (
            <button
              onClick={handleExport}
              disabled={tableBills.length === 0}
              title={isPro ? undefined : 'CSV export is a Pro feature'}
              className="text-sm text-green-accent hover:underline disabled:text-text-muted disabled:no-underline shrink-0 inline-flex items-center gap-1.5"
            >
              {!isPro && <LockIcon className="text-xs" />}
              ↓ Export CSV
              {!isPro && (
                <span className="text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-1.5 py-px no-underline">
                  Pro
                </span>
              )}
            </button>
          )}
        </div>

        {/* The adaptive bar — keywords filter the table instantly; a full question gets a cited answer. */}
        <form onSubmit={e => { e.preventDefault(); submitQuery(); }} className="mb-3">
          <div className="flex items-center gap-2 rounded-xl border-2 border-green-accent/60 bg-bg-secondary px-3 py-2 focus-within:border-green-accent transition-colors">
            <span aria-hidden className="text-text-muted text-lg leading-none">⌕</span>
            <input
              value={query}
              onChange={e => { setQuery(e.target.value); setBillFilters(prev => ({ ...prev, search: e.target.value })); }}
              placeholder={research.hasAsked ? 'Ask a follow-up — or type keywords to browse' : 'Search bills, or ask a question…'}
              aria-label="Search bills or ask a question"
              className="flex-1 min-w-0 bg-transparent text-body text-text-primary placeholder-text-muted focus:outline-none"
            />
            <button
              type="submit"
              disabled={research.busy || query.trim().length < 3}
              className="shrink-0 rounded-lg bg-green-accent text-bg-primary font-medium text-sm px-4 py-1.5 hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {research.busy ? 'Thinking…' : research.hasAsked ? 'Ask follow-up' : 'Ask →'}
            </button>
          </div>
          <p className="mt-1.5 text-xs text-text-muted">
            <b className="text-text-secondary font-medium">Type keywords</b> to filter the bills instantly ·{' '}
            <b className="text-text-secondary font-medium">ask a full question</b> for a grounded, cited answer over the same corpus.
          </p>
        </form>

        {/* Example questions — only before the first ask */}
        {!research.active && (
          <div className="flex flex-wrap gap-2 mb-3">
            {RESEARCH_EXAMPLES.map(ex => (
              <button
                key={ex}
                type="button"
                onClick={() => { setQuery(''); research.ask(ex); }}
                className="rounded-full border border-border-default px-3 py-1.5 text-xs text-text-secondary hover:border-text-primary/40 hover:text-text-primary text-left"
              >
                {ex}
              </button>
            ))}
          </div>
        )}

        <BillFilters filters={billFilters} onChange={setBillFilters} hideSearch resinOptions={resinOptions} />

        {region === 'US' && billFilters.state && (
          <div className="mt-2 text-sm text-text-muted">
            Showing <span className="text-green-accent font-medium">{STATE_NAMES[billFilters.state] ?? billFilters.state}</span>
            {' — '}
            <Link href={`/jurisdictions/us/${billFilters.state.toLowerCase()}/`} className="underline hover:text-text-secondary">view {STATE_NAMES[billFilters.state] ?? billFilters.state} profile</Link>
            {' · '}
            <button onClick={() => setBillFilters(prev => ({ ...prev, state: '' }))} className="underline hover:text-text-secondary">clear</button>
          </div>
        )}

      </section>

      {/* When the reader asks a question, the grounded answer + its cited evidence take over from the
          browse view (map + full table); "back to browsing" returns here. Otherwise: Explorer as usual. */}
      {research.active ? (
        <section className="space-y-5">
          {research.wall && <ResearchWall wall={research.wall} onSignIn={openAuth} />}
          {research.restoring && (
            <div className="space-y-2 border-t border-border-default pt-6">
              <div className="h-6 w-2/3 animate-pulse rounded bg-bg-tertiary" />
              <div className="h-24 w-full animate-pulse rounded-lg bg-bg-tertiary" />
            </div>
          )}
          <ResearchThread research={research} />
          {(research.hasAsked || research.wall) && (
            <button type="button" onClick={backToBrowsing} className="text-sm text-green-accent hover:underline">
              ← Back to browsing all bills
            </button>
          )}
        </section>
      ) : (
        <>
      {/* Map — the Regions dropdown is the primary selector; this shows a *view of that selection*.
          All regions → a ranked coverage readout. US → the states choropleth. EU → the bloc, cropped
          to Europe. A single country → a cropped locator. A code with no geometry → a text panel. */}
      <section>
        {drilledEuMember && (
          <div className="mb-2 text-sm text-text-muted">
            <button onClick={() => setRegions(['EU'])} className="text-green-accent hover:underline">← European Union</button>
            <span className="mx-1.5">/</span>
            <span className="text-text-secondary">{regionLabel(soleRegion!)}</span>
          </div>
        )}
        {/* Keyed by selection so the zoom-settle animation replays on every drill in/out. */}
        <div key={soleRegion ?? 'all'} className="region-map-in">
        {!soleRegion ? (
          <CoverageStrip data={regionCounts} onSelect={code => setRegions([code])} />
        ) : soleRegion === 'US' ? (
          <StateMap
            data={mapData}
            selectedState={billFilters.state || null}
            onStateClick={abbr => setBillFilters(prev => ({ ...prev, state: prev.state === abbr ? '' : abbr }))}
            height={380}
          />
        ) : insetHighlightIds.length ? (
          <RegionInsetMap
            highlightIds={insetHighlightIds}
            caption={soleRegion === 'EU' ? 'European Union · 27 member states — click a country to drill in' : `${regionLabel(soleRegion)} · national law`}
            count={regionCounts[soleRegion]}
            // Click-to-drill only on the multi-country bloc; a single-country inset has nowhere to go.
            onCountrySelect={insetHighlightIds.length > 1 ? code => setRegions([code]) : undefined}
            height={380}
          />
        ) : (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border-default bg-bg-secondary/40 text-center px-6 py-10">
            <div className="text-meta uppercase tracking-wider text-text-muted">
              {regionLabel(soleRegion)} · national law
            </div>
            <p className="mt-2 max-w-md text-sm text-text-secondary">
              The laws below are the view. A map lights up once we ingest this jurisdiction&apos;s geography.
            </p>
          </div>
        )}
        </div>
      </section>

      {/* Bill results table — below the map. The personalize-scope bar (state/material/product) sits
          here, just above the table, instead of globally under the nav. */}
      <section>
        <div className="mb-3"><ScopeBar /></div>
        {/* Only fires when live AND snapshot/localStorage all came up empty — otherwise
            last-known data shows with a quiet FreshnessNote instead of a scary banner. */}
        {billsError && <AlertBanner variant="red" message="We're having trouble loading bill data right now — please refresh in a moment." className="mb-3" />}
        {billsLoading ? (
          <SkeletonList rows={5} />
        ) : (
          <BillTable bills={tableBills} autoPageSize={5} urlSync />
        )}
      </section>
        </>
      )}

      {/* Alerts, bundled below the table (out of the way of the bills, which are what visitors came
          for). The scoped deadline count is here rather than at the top so it informs without leading
          with stress; the Oregon court-case wildcard is US-only — irrelevant to a non-US filter. */}
      <div className="space-y-3">
        <ScopedDeadlineBanner />
        {isUsView && <FederalWatchBanner highRiskCount={highPreemption} />}
      </div>

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
            <> We're tracking <span className="text-text-primary font-medium">{highPreemption}</span> high-risk federal {highPreemption === 1 ? 'action' : 'actions'} right now.</>
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
