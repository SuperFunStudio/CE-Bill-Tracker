'use client';
import { useState, useMemo, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { useBills, useBillTextSearch, useLawsInForce } from '@/hooks/useBills';
import { useFederalActions } from '@/hooks/useFederal';
import { SubscribeSection } from '@/components/about/SubscribeSection';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { FreshnessNote } from '@/components/ui/FreshnessNote';
import { FederalWatchBanner } from '@/components/ui/FederalWatchBanner';
import { StatesTicker } from '@/components/ui/StatesTicker';
import { BillTable } from '@/components/bills/BillTable';
import { BillFilters, DEFAULT_FILTERS, applyBillFilters, matchesKeywordText, resinOptionsFromBills, type BillFilterState } from '@/components/bills/BillFilters';
import { SkeletonList } from '@/components/ui/SkeletonList';
import { ScopedDeadlineBanner } from '@/components/scope/ScopedDeadlineBanner';
import { ScopeBar } from '@/components/scope/ScopeBar';
import { useScope, useScopeActive } from '@/components/scope/ScopeContext';
import { useRegion } from '@/components/layout/RegionContext';
import { regionLabel, REGION_CODES } from '@/components/insights/RegionFilter';
import { highlightIdsFor } from '@/components/map/RegionInsetMap';
import { EU_MEMBERS } from '@/lib/jurisdictions';
import { inScope } from '@/lib/scope';
import { useAuth, useProGate } from '@/components/auth/AuthContext';
import { LockIcon } from '@/components/ui/icons';
import { STATE_NAMES, formatDate, downloadCsv } from '@/lib/utils';
import { resolveFacetTerm, billMatchesFacets } from '@/lib/facetTerms';
import { RESEARCH_EXAMPLES, useFreeAskUsed } from '@/components/research/ResearchThread';
import { useTypedPlaceholder } from '@/components/research/useTypedPlaceholder';
import { AiAnalysisToggle } from '@/components/search/AiAnalysisToggle';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { track } from '@/lib/analytics';
import { useHomeVariant } from '@/components/experiment/useHomeVariant';
import { useAiSurfaceVariant } from '@/components/experiment/useAiSurfaceVariant';
import { HomeVariantVote } from '@/components/experiment/HomeVariantVote';
import { BillDotExplorer } from '@/components/explore/BillDotExplorer';
import { HeadlinesDeadlines } from '@/components/home/HeadlinesDeadlines';
import Link from 'next/link';

const StateMap = dynamic(
  () => import('@/components/map/StateMap').then(m => ({ default: m.StateMap })),
  { ssr: false, loading: () => <div className="h-80 bg-bg-secondary rounded-lg animate-pulse" /> }
);

const RegionInsetMap = dynamic(
  () => import('@/components/map/RegionInsetMap').then(m => ({ default: m.RegionInsetMap })),
  { ssr: false, loading: () => <div className="h-80 bg-bg-secondary rounded-lg animate-pulse" /> }
);

// A slowly-rotating d3-geo globe of laws-in-force by jurisdiction — the "all regions" overview. Canvas
// + window APIs, so client-only (ssr:false).
const CoverageGlobe = dynamic(
  () => import('@/components/map/CoverageGlobe').then(m => ({ default: m.CoverageGlobe })),
  { ssr: false, loading: () => <div className="h-[320px] bg-bg-secondary rounded-lg animate-pulse" /> }
);

/**
 * Run a client navigation inside a view transition where the browser supports one, so the shared ask bar
 * (view-transition-name: ask-bar, set on both surfaces) flies from its place here to the top of /ask
 * instead of the page snapping. Falls back to a plain push in browsers without the API, and honors
 * prefers-reduced-motion — a cut is the correct transition for a reader who asked for less motion.
 */
function navigateWithTransition(go: () => void) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (!doc.startViewTransition || reduced) { go(); return; }
  doc.startViewTransition(go);
}

// Rows the results table shows per page. Five is the default — the table is a browse surface, not a
// spreadsheet, and the page has content below it — but a reader scanning a filtered set shouldn't
// have to page through it five at a time.
const ROWS_PER_PAGE_OPTIONS = [5, 10, 20, 50, 100];

export default function HomePage() {
  const [billFilters, setBillFilters] = useState<BillFilterState>(DEFAULT_FILTERS);
  const [rowsPerPage, setRowsPerPage] = useState(ROWS_PER_PAGE_OPTIONS[0]);
  const { region, regionsParam, regions: selectedRegions, setRegions, isUsView } = useRegion();
  const router = useRouter();

  // Legacy deep links: saved threads used to open on the homepage (?session=). They live at /ask now —
  // forward them rather than 404 the reader's own bookmarks, My Library links, and older emails.
  useEffect(() => {
    const sid = new URLSearchParams(window.location.search).get('session');
    if (sid) router.replace(`/ask/?session=${encodeURIComponent(sid)}`);
  }, [router]);

  // The global region filter (under the nav) drives which jurisdictions the server returns. undefined
  // = "All regions" -> send "all" so the explorer shows every region (not the US-only default).
  // The compliance-dimension filter is applied server-side (compliance_details isn't in the list
  // payload), so it rides the fetch params rather than the client-side applyBillFilters below.
  const dimensionsCsv = billFilters.dimensions.length ? billFilters.dimensions.join(',') : undefined;
  const { data: bills = [], isLoading: billsLoading, error: billsError } = useBills({ ce_relevant: true, limit: 5000, regions: regionsParam ?? 'all', dimensions: dimensionsCsv });
  const { data: federal = [] } = useFederalActions({ limit: 50 });
  // Enacted laws in force by region — the SAME source the globe shades from, so the "Top Regions"
  // ticker ranks identically to the map (combined national + sub-national enacted).
  const { data: lawsInForce = [] } = useLawsInForce();

  const { scope, openEditor: openScopeEditor } = useScope();
  const scopeActive = useScopeActive();

  const { isPro, user, openAuth } = useAuth();
  const gatePro = useProGate();

  // Homepage A/B: variant "b" swaps the bill table for the dot-explorer (client-side bucketing, since
  // the site is a static export). Everything else — ticker, globe, Explore bar — is shared.
  const { variant, ready } = useHomeVariant();

  // Guided-tour capture — the demo-led path (our highest-converting motion for the considered
  // compliance buyer). Opens the shared request-access form, tagged source="home_walkthrough".
  const [walkthroughOpen, setWalkthroughOpen] = useState(false);

  // One adaptive bar with two jobs. Typing filters the table live (Explorer); submitting a question
  // ROUTES to /ask, which owns the conversation. The homepage deliberately doesn't host the answer any
  // more: state that lives only here dies on a nav, a reload, or a discarded tab, which is exactly how
  // long asks were being lost. See docs/ASK_SURFACE_SPEC.md.
  const [query, setQuery] = useState('');
  const freeAskUsed = useFreeAskUsed();
  // A/B: half of devices get the search bar WITHOUT the AI Analysis toggle + Ask button, to see
  // whether that fork in the road is costing us engagement at the top of the page. Nothing is
  // removed for them — the line under the bar links to /ask, which owns questions either way.
  const { variant: aiSurface } = useAiSurfaceVariant();
  const showAiSurface = aiSurface === 'shown';
  // "AI Analysis" mode — OFF (default) = classic keyword filtering of the table; ON unlocks asking
  // grounded, cited questions (and reveals the Ask button). Persisted in localStorage: server render
  // OFF, read the stored value on mount to avoid a hydration mismatch (mirrors BetaContext).
  const [aiModeStored, setAiModeState] = useState(false);
  useEffect(() => {
    try { setAiModeState(localStorage.getItem('ai_analysis_mode') === '1'); } catch { /* ignore */ }
  }, []);
  // In the "hidden" arm there's no control to turn AI mode on, so the bar is keyword-only regardless
  // of what a previous visit stored (the stored preference is preserved, just not honored here).
  const aiMode = aiModeStored && showAiSurface;
  const setAiMode = (v: boolean) => {
    setAiModeState(v);
    try { localStorage.setItem('ai_analysis_mode', v ? '1' : '0'); } catch { /* ignore */ }
    // Entering AI mode: the typed text becomes a question, so stop live-filtering the table by it.
    // Leaving AI mode: resume keyword filtering by whatever is in the box.
    setBillFilters(prev => ({ ...prev, search: v ? '' : query.trim() }));
    track('search_mode_toggled', { mode: v ? 'ai_analysis' : 'keyword' });
  };
  // In keyword mode typing filters the table live; in AI mode it only composes the question.
  const onSearchChange = (v: string) => {
    setQuery(v);
    if (!aiMode) setBillFilters(prev => ({ ...prev, search: v }));
  };
  // Ask hands off to /ask with the question in the URL; that page owns the request and the thread. The
  // view transition carries the bar across so it reads as "let me take you over here" rather than as a
  // page load — see navigateWithTransition.
  const submitQuery = () => {
    if (!aiMode) return;             // asking is only possible in AI Analysis mode
    const q = query.trim();
    if (q.length < 3) return;
    setQuery('');
    setBillFilters(prev => ({ ...prev, search: '' }));
    navigateWithTransition(() => router.push(`/ask/?q=${encodeURIComponent(q)}`));
  };

  // Cycle the example questions through the search-box placeholder, typewriter-style — only in AI mode
  // (in keyword mode the placeholder is the static "Search bills…" line, so the timers would run for a
  // string nobody sees) and only before the reader types, so the animation never fights a real query.
  const typedPlaceholder = useTypedPlaceholder(RESEARCH_EXAMPLES, aiMode && query === '');

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
      // Top Regions ranks by the SAME laws-in-force totals the globe shades from (enacted, with US
      // states + foreign provinces already rolled into the national region code). EU members collapse
      // into the "EU" umbrella. Filtered to REGION_CODES so the ticker can only surface a region the
      // dropdown can also select.
      const KNOWN = new Set(REGION_CODES);
      const data: Record<string, number> = {};
      for (const p of lawsInForce) {
        const k = p.region in EU_MEMBERS ? 'EU' : p.region;
        if (!KNOWN.has(k)) continue;
        data[k] = (data[k] ?? 0) + p.count;
      }
      return { mode: 'regions' as const, label: 'Top Regions', data };
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
  }, [mapSource, billFilters, selectedRegions, lawsInForce]);

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
  // Scoped to the SAME regions as the list fetch: applyBillFilters has no region predicate, so an
  // unscoped search would append out-of-region bills and silently break the region filter (e.g. China
  // selected + "textiles" → 50 EU/US hits, since no Chinese bill's text uses the English word).
  const { data: textHits = [] } = useBillTextSearch(billFilters.search, regionsParam ?? 'all');

  const tableBills = useMemo(() => {
    const base = applyBillFilters(tableSource, billFilters);
    const q = (billFilters.search ?? '').trim();
    if (q.length < 2 || textHits.length === 0) return base;
    // Append full-text-only hits: pass the non-search filters, drop any already shown. The region
    // check is a client-side belt to the server's braces — it also covers the moment after a region
    // switch when the previous query's hits are still being kept (keepPreviousData).
    const baseIds = new Set(base.map(b => b.id));
    const allowedRegions = selectedRegions.length ? new Set(selectedRegions) : null;
    const extra = applyBillFilters(textHits, { ...billFilters, search: '' }).filter(
      (b) => !baseIds.has(b.id) && (!allowedRegions || allowedRegions.has(b.region ?? '')),
    );
    return extra.length ? [...base, ...extra] : base;
  }, [tableSource, billFilters, textHits, selectedRegions]);

  // When the typed term names a material / instrument / resin, say so — and how many of the results
  // are here on the tag alone rather than on a string match. That count is exactly the set the old
  // keyword search dropped: mostly non-English law (Chinese titles, English-only tsvector) and
  // framework-titled statutes. Offering the facet as a real filter turns the accident into a choice.
  const searchFacets = useMemo(
    () => (billFilters.search.trim().length >= 2 ? resolveFacetTerm(billFilters.search) : null),
    [billFilters.search],
  );
  const facetOnlyCount = useMemo(() => {
    if (!searchFacets) return 0;
    return tableBills.filter(
      b => !matchesKeywordText(b, billFilters.search) && billMatchesFacets(b, searchFacets),
    ).length;
  }, [tableBills, searchFacets, billFilters.search]);

  // Promote the bridged term to the real facet filter: the material dropdown for a material term,
  // the instrument select for an instrument one. Clears the keyword so the filter alone is the query.
  function applyFacetFilter() {
    if (!searchFacets) return;
    // search_term, NOT term: `term` is a reserved GA4 traffic-source parameter (campaign keyword) and
    // would overwrite the visitor's acquisition attribution with whatever they typed into the bill search.
    track('search_facet_promoted', { search_term: billFilters.search.trim(), facets: searchFacets.labels.join(',') });
    setQuery('');
    setBillFilters(prev => ({
      ...prev,
      search: '',
      materialCategories: searchFacets.materials.length ? searchFacets.materials : prev.materialCategories,
      polymers: searchFacets.polymers.length ? searchFacets.polymers : prev.polymers,
      instrumentType: !searchFacets.materials.length && searchFacets.instruments.length
        ? searchFacets.instruments[0]
        : prev.instrumentType,
    }));
  }

  // CSV export is a Pro feature: gatePro routes anon → sign-in, Free → checkout, Pro → the download.
  function handleExport() {
    gatePro(() => downloadCsv('atlascircular_bills.csv', tableBills.map(b => ({
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
      {/* Value prop + primary CTA — held back until a signed-out visitor has spent their one free
          question and is reaching for a second (useFreeAskUsed reads the marker /ask writes). A fresh
          visitor gets the clean Explore surface first; the "start free" pitch only lands once they've
          engaged and hit the limit. Never shown to users who've already converted. */}
      {!user && freeAskUsed && (
        <section className="rounded-xl border border-green-accent/30 bg-green-hero p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center justify-between gap-5">
          <div className="max-w-2xl">
            <h1 className="font-serif text-2xl sm:text-3xl text-text-primary leading-tight text-balance">
              Never miss a compliance deadline.
            </h1>
            <p className="mt-2 text-text-secondary text-body leading-relaxed">
              We track every circular-economy bill and EPR obligation, then pull out the dates and
              requirements so you don&apos;t have to. Start free — no card required.
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

      {/* Page masthead: "Explore · N circular economy bills". The count says what the corpus IS —
          that phrase is the tagline this line used to carry — and "See what we track" answers the
          question it provokes by sending readers to the methodology. CSV export moved down to the
          table it exports (see the action row above the results). */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="font-serif text-2xl sm:text-3xl text-text-primary">Explore</h1>
          <span className="text-text-muted text-sm">{tableBills.length} circular economy bills</span>
          <FreshnessNote />
        </div>
        <Link
          href="/methodology"
          onClick={() => track('cta_click', { entry_source: 'explore_methodology' })}
          className="shrink-0 text-sm text-text-secondary hover:text-green-accent transition-colors"
        >
          See what we track <span aria-hidden>→</span>
        </Link>
      </div>

      {/* Ranked leaderboard line, right under the nav. Region-aware + enacted-only: umbrella regions
          on "All regions", US states under a US selection, EU member states under an EU/member one
          (France defers here); hidden for a lone non-EU country with no sub-jurisdictions. */}
      {leaderboard.mode !== 'none' && (
        <StatesTicker
          label={leaderboard.label}
          data={leaderboard.data}
          // Always link through to the full Standings board (/states adapts to the selection: the US
          // momentum board, the EU board, or the two-column States|Nations leaderboard by default).
          restHref="/states"
          restLabel={leaderboard.mode === 'us-states' ? 'The rest' : 'View all'}
          onSelect={code =>
            leaderboard.mode === 'us-states'
              ? setBillFilters(prev => ({ ...prev, state: prev.state === code ? '' : code }))
              : setRegions([code])
          }
        />
      )}

      {/* Compact desktop masthead: the globe drops out of the full-width band and into a fixed 380px
          right rail (≈ the width it gets on a phone, so the same proportions), with the search bar and
          facets taking the left column beside it. Below lg the two stack in DOM order — globe first,
          then the bar — exactly as before. Explicit col/row placement (rather than reordering the DOM)
          keeps the mobile source order intact. */}
      <div className="space-y-8 lg:space-y-0 lg:grid lg:grid-cols-[minmax(0,1fr)_380px] lg:gap-8 lg:items-start">

      {/* Map/globe — moved up to sit right below the ticker. The Regions selector that drives it lives
          in the Explore facets just below. */}
      <section className="lg:col-start-2 lg:row-start-1">
          {soleRegion && (
            <div className="mb-2 flex items-center gap-1.5 text-sm text-text-muted">
              <button onClick={() => setRegions([])} className="text-green-accent hover:underline">← Back to the globe</button>
              {drilledEuMember && (
                <>
                  <span className="mx-0.5">/</span>
                  <button onClick={() => setRegions(['EU'])} className="text-green-accent hover:underline">European Union</button>
                  <span className="mx-0.5">/</span>
                  <span className="text-text-secondary">{regionLabel(soleRegion!)}</span>
                </>
              )}
            </div>
          )}
          {/* Keyed by selection so the zoom-settle animation replays on every drill in/out. */}
          <div key={soleRegion ?? 'all'} className="region-map-in">
          {!soleRegion ? (
            <CoverageGlobe onSelect={code => setRegions([code])} />
          ) : soleRegion === 'US' ? (
            <StateMap
              data={mapData}
              selectedState={billFilters.state || null}
              onStateClick={abbr => setBillFilters(prev => ({ ...prev, state: prev.state === abbr ? '' : abbr }))}
              height={320}
            />
          ) : insetHighlightIds.length ? (
            <RegionInsetMap
              highlightIds={insetHighlightIds}
              caption={soleRegion === 'EU' ? 'European Union · 27 member states — click a country to drill in' : `${regionLabel(soleRegion)} · national law`}
              count={regionCounts[soleRegion]}
              onCountrySelect={insetHighlightIds.length > 1 ? code => setRegions([code]) : undefined}
              height={320}
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

      {/* Explore: one adaptive search/ask bar + facets. The "Explore · N bills" title + Export live at
          the top of the page now; this section is just the bar and its controls. */}
      <section className="lg:col-start-1 lg:row-start-1">
        {/* The search box leads — it sits directly under the globe as the page's primary action, with the
            one-line explainer beneath it. Enter submits a question only when AI Analysis is on
            (submitQuery guards it). */}
        <form onSubmit={e => { e.preventDefault(); submitQuery(); }} style={{ viewTransitionName: 'ask-bar' }}>
          <div className="flex items-center gap-2 rounded-xl border-2 border-green-accent/60 bg-bg-secondary px-3 py-2 focus-within:border-green-accent transition-colors">
            <span aria-hidden className="text-text-muted text-lg leading-none">⌕</span>
            <input
              value={query}
              onChange={e => onSearchChange(e.target.value)}
              placeholder={
                aiMode
                  ? (typedPlaceholder || 'Ask a question about the corpus…')
                  : 'Search bills by keyword…'
              }
              aria-label={aiMode ? 'Ask a question' : 'Search bills by keyword'}
              className="flex-1 min-w-0 bg-transparent text-body text-text-primary placeholder-text-muted focus:outline-none"
            />
          </div>
        </form>

        {/* One line, under the bar: what the box does, and where the questions go. "Ask the Atlas" is
            the link, not a mode name, so it reads the same in both arms of the A/B — in the "hidden"
            arm it's the ONLY route to the AI surface, which is the point of the test. */}
        <p className="mt-2 text-xs text-text-muted truncate">
          <b className="text-text-secondary font-medium">Keywords</b> filter instantly ·{' '}
          <Link
            href="/ask"
            onClick={() => track('cta_click', { entry_source: 'explore_search_hint', variant: aiSurface })}
            className="text-green-accent hover:underline"
          >
            Ask the Atlas
          </Link>{' '}
          for AI analysis
        </p>

        {/* Control row UNDER the bar: AI Analysis toggle + Ask lead (when this device is in the
            "shown" arm); the facets share the same row on desktop and wrap below on mobile. Kept OUT
            of the <form> so a facet dropdown can never accidentally submit a question. */}
        <div className="mt-3 mb-4 flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-text-primary/15 pb-4">
          {showAiSurface && (
            <div className="flex items-center gap-3 shrink-0">
              <AiAnalysisToggle on={aiMode} onChange={setAiMode} />
              {/* Ask is ALWAYS visible so the capability is discoverable; it's just disabled until AI
                  Analysis is on (and there's a long-enough question). submitQuery no-ops when off. */}
              <button
                type="button"
                onClick={submitQuery}
                disabled={!aiMode || query.trim().length < 3}
                title={!aiMode ? 'Turn on AI Analysis to ask a question' : undefined}
                className="shrink-0 rounded-lg bg-green-accent text-bg-primary font-medium text-sm px-5 py-2 hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Ask →
              </button>
            </div>
          )}
          {/* On lg the facets sit in the narrow left column beside the globe, so they take their own
              full-width line under the toggle+Ask row rather than sharing it. With that row absent,
              the facets are the only thing under the bar — so open them rather than hide them behind
              a second click. */}
          <div className="w-full min-w-0 sm:w-auto sm:flex-1 lg:w-full lg:flex-none">
            <BillFilters
              // The A/B bucket resolves after mount, so remount the facets when it lands — their
              // "start expanded" default is initial state, and a prop flip alone wouldn't take.
              key={aiSurface}
              filters={billFilters}
              onChange={setBillFilters}
              hideSearch
              showRegion
              resinOptions={resinOptions}
              expandFiltersByDefault={!showAiSurface}
            />
          </div>
        </div>

        {/* Facet-bridge notice: what the term matched beyond the literal words, and an offer to make
            it a real filter. Only shown when the bridge actually pulled bills in (facetOnlyCount > 0),
            so it explains a visible difference rather than adding noise. */}
        {searchFacets && facetOnlyCount > 0 && (
          <div className="mb-3 text-sm text-text-muted">
            <span className="text-text-secondary">&ldquo;{billFilters.search.trim()}&rdquo;</span>
            {' also matches the '}
            <span className="text-text-secondary">{searchFacets.labels.join(' / ')}</span>
            {' tag — including '}
            <span className="text-green-accent">{facetOnlyCount}</span>
            {facetOnlyCount === 1 ? ' law that never uses' : ' laws that never use'}
            {' the word (non-English statutes, and framework laws that cover it without naming it).'}
            {' '}
            <button type="button" onClick={applyFacetFilter} className="underline hover:text-text-secondary">
              Filter by {searchFacets.labels.join(' / ')} instead
            </button>
          </div>
        )}

        {region === 'US' && billFilters.state && (
          <div className="mb-3 text-sm text-text-muted">
            Showing <span className="text-green-accent font-medium">{STATE_NAMES[billFilters.state] ?? billFilters.state}</span>
            {' — '}
            <Link href={`/jurisdictions/us/${billFilters.state.toLowerCase()}/`} className="underline hover:text-text-secondary">view {STATE_NAMES[billFilters.state] ?? billFilters.state} profile</Link>
            {' · '}
            <button type="button" onClick={() => setBillFilters(prev => ({ ...prev, state: '' }))} className="underline hover:text-text-secondary">clear</button>
          </div>
        )}

      </section>
      </div>

      {/* Bill results table. The personalize-scope bar (state/material/product) sits here, just above
          the table, instead of globally under the nav. */}
      <section>
        <div className="mb-3"><ScopeBar /></div>

        {/* Action row — between the filters and the results it acts on. Left: set a scope (the
            invitation that used to be buried in the deadline banner's tail, now a real button on the
            filter/results seam) + how many rows to show. Right: CSV export, which used to float up in
            the masthead where it read as page furniture rather than "download this table". */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border-default pb-2">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <button
              onClick={() => { track('cta_click', { entry_source: 'explore_scope' }); openScopeEditor(); }}
              className="text-sm text-green-accent hover:underline"
            >
              Set your regional &amp; material scope →
            </button>
            <label className="flex items-center gap-1.5 text-xs text-text-muted">
              Show
              <select
                value={rowsPerPage}
                onChange={e => setRowsPerPage(Number(e.target.value))}
                aria-label="Rows per page"
                className="rounded border border-border-default bg-bg-secondary px-1.5 py-0.5 text-xs text-text-primary focus:border-green-accent focus:outline-none"
              >
                {ROWS_PER_PAGE_OPTIONS.map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
              per page
            </label>
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
              <span className="text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-1.5 py-px no-underline">
                Pro
              </span>
            )}
          </button>
        </div>

        {/* Only fires when live AND snapshot/localStorage all came up empty — otherwise
            last-known data shows with a quiet FreshnessNote instead of a scary banner. */}
        {billsError && <AlertBanner variant="red" message="We're having trouble loading bill data right now — please refresh in a moment." className="mb-3" />}
        {billsLoading ? (
          <SkeletonList rows={5} />
        ) : variant === 'b' ? (
          <BillDotExplorer bills={tableBills} />
        ) : (
          <BillTable bills={tableBills} autoPageSize={rowsPerPage} urlSync />
        )}
      </section>

      {/* Headlines & Deadlines — the signals that aren't bills, bundled below the table (out of the
          way of the bills, which are what visitors came for) and now under a heading that says what
          they are. Two loose notices reading as stray banners is what the section header fixes. The
          deadline count is here rather than at the top so it informs without leading with stress; the
          Oregon court-case wildcard is US-only — irrelevant to a non-US filter.
          The section leads with two date-relevant blocks (documented outcomes / next deadlines) and
          keeps the banners beneath them. Still to come: consortium formations and notes from the
          pulse script, which have no feed to read from yet. */}
      <HeadlinesDeadlines>
        <ScopedDeadlineBanner />
        {isUsView && <FederalWatchBanner highRiskCount={highPreemption} />}
      </HeadlinesDeadlines>

      {/* Guided-tour CTA — a standing home for the demo-led motion, distinct from the free-signup and
          referral CTAs. A 15-min walkthrough is the highest-converting path for the considered
          compliance buyer, so it gets its own band above the newsletter signup. */}
      <section className="border-t border-border-default pt-8">
        <div className="rounded-xl border border-green-accent/30 bg-green-hero px-5 py-4 sm:px-6 sm:py-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="max-w-2xl">
            <h3 className="font-serif text-lg text-text-primary">Unlock the full power of the Atlas.</h3>
            <p className="text-text-secondary text-sm mt-0.5 leading-relaxed">
              Book a 15-minute walkthrough — we&apos;ll map the tracker to the materials and
              jurisdictions your team actually reports on.
            </p>
          </div>
          <button
            onClick={() => { track('cta_click', { entry_source: 'home_walkthrough' }); setWalkthroughOpen(true); }}
            className="shrink-0 rounded-lg bg-green-accent text-bg-primary font-semibold px-5 py-2.5 hover:opacity-90 transition-opacity"
          >
            Book a walkthrough →
          </button>
        </div>
      </section>

      {/* Get free updates */}
      <SubscribeSection className="border-t border-border-default pt-8" />

      {walkthroughOpen && (
        <RequestAccessModal
          plan="bespoke"
          planLabel="a walkthrough"
          heading="Book a walkthrough"
          source="home_walkthrough"
          onClose={() => setWalkthroughOpen(false)}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-border-default pt-6 pb-2 text-center">
        <Link href="/about" className="text-sm text-green-accent hover:underline">
          Learn more about the project &rarr;
        </Link>
      </footer>

      {/* A/B: ask Homepage-B visitors what they think of the new look (self-dismissing, once per device). */}
      {ready && variant === 'b' && <HomeVariantVote />}
    </div>
  );
}
