'use client';
import { useState, useMemo, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { useBills, useBillTextSearch, useLawsInForce } from '@/hooks/useBills';
import { useFederalSummary } from '@/hooks/useFederal';
import { SubscribeSection } from '@/components/about/SubscribeSection';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { FreshnessNote } from '@/components/ui/FreshnessNote';
import { FederalWatchBanner } from '@/components/ui/FederalWatchBanner';
import { BillTable } from '@/components/bills/BillTable';
import { BillFilters, DEFAULT_FILTERS, applyBillFilters, matchesKeywordText, resinOptionsFromBills, type BillFilterState } from '@/components/bills/BillFilters';
import { SkeletonList } from '@/components/ui/SkeletonList';
import { ScopedDeadlineBanner } from '@/components/scope/ScopedDeadlineBanner';
import { ScopeBar } from '@/components/scope/ScopeBar';
import { useScope, useScopeActive } from '@/components/scope/ScopeContext';
import { useRegion } from '@/components/layout/RegionContext';
import { regionLabel, REGION_CODES } from '@/components/insights/RegionFilter';
import { highlightIdsFor, enactedCountsByIso } from '@/components/map/RegionInsetMap';
import { EU_MEMBERS } from '@/lib/jurisdictions';
import { inScope } from '@/lib/scope';
import { useAuth, useProGate } from '@/components/auth/AuthContext';
import { LockIcon } from '@/components/ui/icons';
import { STATE_NAMES, formatDate, downloadCsv } from '@/lib/utils';
import { resolveFacetTerm, billMatchesFacets } from '@/lib/facetTerms';
import { useFreeAskUsed } from '@/components/research/ResearchThread';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { track } from '@/lib/analytics';
import { useHomeVariant } from '@/components/experiment/useHomeVariant';
import { HomeVariantVote } from '@/components/experiment/HomeVariantVote';
import { BillDotExplorer } from '@/components/explore/BillDotExplorer';
import { CorpusJsonLd } from '@/components/seo/CorpusJsonLd';
import { HeadlinesDeadlines } from '@/components/home/HeadlinesDeadlines';
import { JurisdictionTopList } from '@/components/home/JurisdictionTopList';
import { RegionSummary } from '@/components/home/RegionSummary';
import { fmtCount } from '@/lib/mapScale';
import type { BillSummary } from '@/lib/types';
import Link from 'next/link';

const StateMap = dynamic(
  () => import('@/components/map/StateMap').then(m => ({ default: m.StateMap })),
  { ssr: false, loading: () => <div className="h-[300px] bg-bg-secondary rounded-lg animate-pulse" /> }
);

const RegionInsetMap = dynamic(
  () => import('@/components/map/RegionInsetMap').then(m => ({ default: m.RegionInsetMap })),
  { ssr: false, loading: () => <div className="h-[120px] bg-bg-secondary rounded-lg animate-pulse" /> }
);

// A slowly-rotating d3-geo globe of laws-in-force by jurisdiction — the "all regions" overview. Canvas
// + window APIs, so client-only (ssr:false).
const CoverageGlobe = dynamic(
  () => import('@/components/map/CoverageGlobe').then(m => ({ default: m.CoverageGlobe })),
  { ssr: false, loading: () => <div className="h-[340px] bg-bg-secondary rounded-lg animate-pulse" /> }
);

// Rows per page. 25 by default: the table is the page's subject now (it sits at the top of the right
// column, beside the map), so a screenful of laws is the point. The size control lives in the table
// footer.
const ROWS_PER_PAGE_OPTIONS = [10, 25, 50, 100];
const DEFAULT_ROWS = 25;

/** ISO numeric ids a bill's jurisdiction occupies on the globe (EU-central law → every member). */
function globeIdsForBill(b: BillSummary): string[] {
  if (b.region === 'US') return ['840'];
  return b.region ? highlightIdsFor(b.region) : [];
}

export default function HomePage() {
  const [billFilters, setBillFilters] = useState<BillFilterState>(DEFAULT_FILTERS);
  const [rowsPerPage, setRowsPerPage] = useState(DEFAULT_ROWS);
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
  // Counts, not rows: the banner below only ever needed the high-preemption tally, and the rows are
  // CAP_FEDERAL now. /federal-actions/summary stays public precisely so this surface keeps working.
  const { data: federalStats } = useFederalSummary();
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

  // The Explore bar carries both modes INSIDE the field: a Filter | Ask segmented toggle at its left
  // edge. Filter (the default) narrows the table live on every keystroke; Ask sends the question to
  // /ask on Enter, where the thread lives (state that lives only on this page dies on a nav, a reload,
  // or a discarded tab — see docs/ASK_SURFACE_SPEC.md). History: a mode toggle sat ABOVE the bar until
  // 2026-08-13, when an A/B removed it in favour of a helper line under the bar linking to /ask. The
  // helper line is gone now and the mode lives in the field itself, defaulting to Filter, so a reader
  // who never touches it gets exactly the keyword box that won that test.
  const [query, setQuery] = useState('');
  const [searchMode, setSearchMode] = useState<'filter' | 'ask'>('filter');
  const freeAskUsed = useFreeAskUsed();
  const onSearchChange = (v: string) => {
    setQuery(v);
    if (searchMode === 'filter') setBillFilters(prev => ({ ...prev, search: v }));
  };
  function switchSearchMode(mode: 'filter' | 'ask') {
    if (mode === searchMode) return;
    track('explore_search_mode', { mode });
    setSearchMode(mode);
    // The table follows the box only in Filter mode: entering Ask releases the keyword filter, and
    // coming back applies whatever is typed.
    setBillFilters(prev => ({ ...prev, search: mode === 'filter' ? query : '' }));
  }
  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (searchMode !== 'ask' || q.length < 3) return;
    track('cta_click', { entry_source: 'explore_ask_mode' });
    router.push(`/ask/?q=${encodeURIComponent(q)}`);
  }

  // The table row (or top-list entry) under the pointer — its jurisdiction is outlined on the map.
  const [hoverBill, setHoverBill] = useState<BillSummary | null>(null);
  const [hoverCode, setHoverCode] = useState<string | null>(null);

  // Below lg the map and the table can't sit side by side; the table leads and the map is one tap away.
  const [mobileView, setMobileView] = useState<'list' | 'map'>('list');

  const highPreemption = federalStats?.high_preemption ?? 0;

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
    () => (scopeActive ? bills.filter(b => inScope(b, { regions: [], states: [], materials: scope.materials })) : bills),
    [bills, scopeActive, scope],
  );

  // The state map shades ENACTED laws per state — the one map metric site-wide (lib/mapScale), so it
  // reads on the same scale as the globe. Honors every active filter EXCEPT state, so all states stay
  // visible/clickable. City ordinances ("OR-PORTLAND") don't count toward their state.
  const mapData = useMemo(() => {
    const filtered = applyBillFilters(mapSource, { ...billFilters, state: '', enactedOnly: true });
    const counts: Record<string, number> = {};
    filtered.forEach(b => {
      if (b.region === 'US' && b.state in STATE_NAMES) counts[b.state] = (counts[b.state] ?? 0) + 1;
    });
    return counts;
  }, [mapSource, billFilters]);

  // Per-country enacted counts for the regional inset maps (EU bloc, lone-country locator) — the same
  // numbers the globe shades from.
  const countsByIso = useMemo(() => enactedCountsByIso(lawsInForce), [lawsInForce]);

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
      return { mode: 'regions' as const, label: 'Top regions', data };
    }
    if (selectedRegions.includes('US')) {
      return { mode: 'us-states' as const, label: 'Top states',
        // STATE_NAMES keys only: city ordinances ("OR-PORTLAND") must not rank as states.
        data: tally(b => (b.region === 'US' && b.state && b.state in STATE_NAMES ? b.state : null)) };
    }
    if (selectedRegions.includes('EU') || selectedRegions.some(r => r in EU_MEMBERS)) {
      return { mode: 'eu-members' as const, label: 'Top member states',
        data: tally(b => (b.region && b.region in EU_MEMBERS ? b.region : null)) };
    }
    return { mode: 'none' as const, label: '', data: {} as Record<string, number> };
  }, [mapSource, billFilters, selectedRegions, lawsInForce]);

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

  // ── Focus + copy ────────────────────────────────────────────────────────────────────────────────
  // The jurisdiction the page is filtered to, if exactly one: a US state, else the sole region.
  const focusState = soleRegion === 'US' && billFilters.state ? billFilters.state : null;
  const placeName = (code: string) =>
    ['US', 'EU', 'UK', 'NL'].includes(code) ? `the ${regionLabel(code)}` : regionLabel(code);
  // Scoped header count: "1,672 tracked measures in the United States".
  const scopePhrase = focusState
    ? `in ${STATE_NAMES[focusState] ?? focusState}`
    : soleRegion
      ? `in ${placeName(soleRegion)}`
      : selectedRegions.length > 1
        ? `in ${selectedRegions.length} regions`
        : 'across all regions';

  // Map ↔ table sync: the row (or top-list entry) under the pointer is outlined on whichever map shows.
  const hoverGlobeIds = useMemo(() => {
    if (hoverBill) return globeIdsForBill(hoverBill);
    if (hoverCode && leaderboard.mode === 'regions') return hoverCode === 'US' ? ['840'] : highlightIdsFor(hoverCode);
    return [];
  }, [hoverBill, hoverCode, leaderboard.mode]);
  const hoverStateAbbr = hoverBill
    ? (hoverBill.region === 'US' && hoverBill.state in STATE_NAMES ? hoverBill.state : null)
    : leaderboard.mode === 'us-states' ? hoverCode : null;
  const hoverEuIds = useMemo(() => {
    const code = hoverBill?.region ?? (leaderboard.mode === 'eu-members' ? hoverCode : null);
    return code && (code === 'EU' || code in EU_MEMBERS) ? highlightIdsFor(code) : [];
  }, [hoverBill, hoverCode, leaderboard.mode]);

  const topListName = (code: string) =>
    leaderboard.mode === 'us-states' ? STATE_NAMES[code] ?? code : regionLabel(code);

  const crumbSep = <span aria-hidden className="text-text-muted/60">/</span>;
  const crumbBtn = 'link-quiet text-text-secondary';

  return (
    <div className="mx-auto max-w-[1600px] px-4 pb-8 pt-4 sm:px-6">
      {/* schema.org Dataset for the corpus. The bills on this page are fetched client-side, so a
          crawler that doesn't run JS sees an empty frame — this is the machine-readable description
          it gets instead. Pre-rendered into the static HTML at build despite living in a client
          component. See components/seo/CorpusJsonLd. */}
      <CorpusJsonLd />

      {/* Value prop + primary CTA — held back until a signed-out visitor has spent their one free
          question and is reaching for a second (useFreeAskUsed reads the marker /ask writes). One slim
          band, not a hero: the title, search and the first laws still land above the fold beneath it. */}
      {!user && freeAskUsed && (
        <section className="mb-4 flex flex-col gap-3 rounded-lg border border-border-default bg-bg-secondary px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-text-secondary">
            <span className="font-serif text-base text-text-primary">Never miss a compliance deadline.</span>{' '}
            We pull the dates and requirements out of every circular-economy law. Start free — no card required.
          </p>
          <div className="flex shrink-0 items-center gap-4">
            <Link href="/pricing" className="link-arrow text-xs">Plans</Link>
            <button
              onClick={openAuth}
              className="rounded-md bg-text-primary px-4 py-1.5 text-sm font-semibold text-bg-primary transition-opacity hover:opacity-90"
            >
              Start free
            </button>
          </div>
        </section>
      )}

      {/* ── Top of page: capped at ~25% of the viewport. One line of title + scoped count beside the
          search field, then ONE toolbar row (region · state · filters · scope · export). Nothing else
          stacks above the table. ── */}
      <header>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between lg:gap-8">
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
            <h1 className="font-serif text-2xl leading-none text-text-primary sm:text-[1.75rem]">Explore</h1>
            <p className="text-sm text-text-secondary">
              <span className="font-semibold text-text-primary tabular-nums">{fmtCount(tableBills.length)}</span>
              {' '}tracked {tableBills.length === 1 ? 'measure' : 'measures'} {scopePhrase}
            </p>
            <Link
              href="/methodology"
              onClick={() => track('cta_click', { entry_source: 'explore_methodology' })}
              className="link-arrow text-xs"
            >
              See what we track
            </Link>
            <FreshnessNote />
          </div>

          {/* Search, with the mode inside the field: Filter (live keyword filter, the default) | Ask
              (Enter hands the question to /ask). Never narrower than ~27 characters of input. Still a
              <form> so Enter is a submit, not a page navigation. */}
          <form onSubmit={submitSearch} className="w-full lg:max-w-xl" style={{ viewTransitionName: 'ask-bar' }}>
            <div className="flex h-11 items-center gap-2 rounded-lg border border-border-default bg-bg-secondary pl-1.5 pr-1.5 transition-colors focus-within:border-text-primary">
              <div role="radiogroup" aria-label="Search mode" className="flex shrink-0 rounded-md bg-bg-tertiary p-0.5 text-xs font-medium">
                {(['filter', 'ask'] as const).map(m => (
                  <button
                    key={m}
                    type="button"
                    role="radio"
                    aria-checked={searchMode === m}
                    onClick={() => switchSearchMode(m)}
                    className={`rounded px-2.5 py-1 transition-colors ${
                      searchMode === m ? 'bg-bg-secondary text-text-primary shadow-sm' : 'text-text-muted hover:text-text-primary'
                    }`}
                  >
                    {m === 'filter' ? 'Filter' : 'Ask'}
                  </button>
                ))}
              </div>
              <input
                value={query}
                onChange={e => onSearchChange(e.target.value)}
                placeholder={searchMode === 'filter' ? 'Keyword, bill number or material…' : 'Ask a question about circular-economy law…'}
                aria-label={searchMode === 'filter' ? 'Filter laws by keyword' : 'Ask the Atlas a question'}
                enterKeyHint={searchMode === 'ask' ? 'send' : 'search'}
                className="min-w-[27ch] flex-1 bg-transparent text-body text-text-primary placeholder-text-muted focus:outline-none"
              />
              {searchMode === 'ask' ? (
                <button
                  type="submit"
                  disabled={query.trim().length < 3}
                  className="shrink-0 rounded-md bg-green-accent px-3 py-1.5 text-sm font-semibold text-bg-primary transition-opacity hover:opacity-90 disabled:opacity-40"
                >
                  Ask
                </button>
              ) : query && (
                <button
                  type="button"
                  onClick={() => onSearchChange('')}
                  aria-label="Clear search"
                  className="shrink-0 px-2 text-text-muted hover:text-text-primary"
                >
                  ×
                </button>
              )}
            </div>
          </form>
        </div>

        <div className="mt-2 border-b border-border-default">
          <BillFilters
            filters={billFilters}
            onChange={setBillFilters}
            hideSearch
            showRegion
            resinOptions={resinOptions}
            trailing={
              <>
                <button
                  onClick={() => { track('cta_click', { entry_source: 'explore_scope' }); openScopeEditor(); }}
                  className="h-8 text-sm text-text-secondary transition-colors hover:text-text-primary hover:underline underline-offset-2"
                >
                  Set scope
                </button>
                <button
                  onClick={handleExport}
                  disabled={tableBills.length === 0}
                  title={isPro ? undefined : 'CSV export is a Pro feature'}
                  className="inline-flex h-8 items-center gap-1.5 text-sm text-text-secondary transition-colors hover:text-text-primary disabled:text-text-muted"
                >
                  {!isPro && <LockIcon className="text-xs" />}
                  Export CSV
                  {!isPro && (
                    <span className="rounded-full border border-border-default px-1.5 py-px text-[11px] uppercase tracking-wider text-text-muted">
                      Pro
                    </span>
                  )}
                </button>
              </>
            }
          />
        </div>
      </header>

      {/* Active-scope strip (renders only when a personalization scope is set). */}
      <ScopeBar />

      {/* Facet-bridge notice: what the term matched beyond the literal words, and an offer to make
          it a real filter. Only shown when the bridge actually pulled bills in (facetOnlyCount > 0),
          so it explains a visible difference rather than adding noise. */}
      {searchFacets && facetOnlyCount > 0 && (
        <div className="mt-3 text-sm text-text-muted">
          <span className="text-text-secondary">&ldquo;{billFilters.search.trim()}&rdquo;</span>
          {' also matches the '}
          <span className="text-text-secondary">{searchFacets.labels.join(' / ')}</span>
          {' tag — including '}
          <span className="font-semibold text-text-primary">{fmtCount(facetOnlyCount)}</span>
          {facetOnlyCount === 1 ? ' law that never uses' : ' laws that never use'}
          {' the word (non-English statutes, and framework laws that cover it without naming it).'}
          {' '}
          <button type="button" onClick={applyFacetFilter} className="link-quiet">
            Filter by {searchFacets.labels.join(' / ')} instead
          </button>
        </div>
      )}

      {/* Below lg: the table leads; the map is one tap away. */}
      <div role="tablist" aria-label="View" className="mt-3 inline-flex rounded-md border border-border-default p-0.5 text-sm lg:hidden">
        {(['list', 'map'] as const).map(v => (
          <button
            key={v}
            role="tab"
            aria-selected={mobileView === v}
            onClick={() => setMobileView(v)}
            className={`rounded px-4 py-1 transition-colors ${mobileView === v ? 'bg-text-primary text-bg-primary' : 'text-text-secondary'}`}
          >
            {v === 'list' ? 'List' : 'Map'}
          </button>
        ))}
      </div>

      {/* ── Split view: map column (38%) | table (62%). The table starts at the top of the content
          area; the map column holds the overview, the focus summary and the top-10. DOM order puts the
          table first (it's the subject), grid placement puts the map on the left at lg. ── */}
      <div className="mt-3 lg:mt-4 lg:grid lg:grid-cols-[minmax(0,38fr)_minmax(0,62fr)] lg:items-start lg:gap-6">
        <section
          aria-label="Laws"
          className={`${mobileView === 'list' ? 'block' : 'hidden'} min-w-0 lg:col-start-2 lg:row-start-1 lg:block`}
        >
          {/* Only fires when live AND snapshot/localStorage all came up empty — otherwise
              last-known data shows with a quiet FreshnessNote instead of a scary banner. */}
          {billsError && <AlertBanner variant="red" message="We're having trouble loading bill data right now — please refresh in a moment." className="mb-3" />}
          {billsLoading ? (
            <SkeletonList rows={8} />
          ) : variant === 'b' ? (
            <BillDotExplorer bills={tableBills} />
          ) : (
            <BillTable
              bills={tableBills}
              autoPageSize={rowsPerPage}
              pageSizeOptions={ROWS_PER_PAGE_OPTIONS}
              onPageSizeChange={setRowsPerPage}
              onRowHover={setHoverBill}
              urlSync
            />
          )}
        </section>

        <aside
          aria-label="Map"
          className={`${mobileView === 'map' ? 'block' : 'hidden'} space-y-5 lg:sticky lg:top-4 lg:col-start-1 lg:row-start-1 lg:block`}
        >
          {/* Keyed by selection so the zoom-settle animation replays on every drill in/out. */}
          <div key={soleRegion ?? 'all'} className="region-map-in space-y-4">
            {!soleRegion ? (
              <CoverageGlobe onSelect={code => setRegions([code])} highlightIds={hoverGlobeIds} height={340} />
            ) : (
              <>
                {/* Filtering is in place: the table beside this is already narrowed. The summary says
                    where you are and what's there, instead of a full-height map of one country. */}
                <RegionSummary
                  name={focusState ? STATE_NAMES[focusState] ?? focusState : regionLabel(soleRegion)}
                  kind={
                    focusState ? 'US state'
                      : soleRegion === 'US' ? 'Federal and state law'
                        : soleRegion === 'EU' ? 'EU-wide law'
                          : drilledEuMember ? 'National law · EU member state'
                            : 'National law'
                  }
                  bills={tableBills}
                  crumbs={
                    <>
                      <button onClick={() => setRegions([])} className={crumbBtn}>All regions</button>
                      {drilledEuMember && (
                        <>{crumbSep}<button onClick={() => setRegions(['EU'])} className={crumbBtn}>European Union</button></>
                      )}
                      {focusState && (
                        <>{crumbSep}<button onClick={() => setBillFilters(prev => ({ ...prev, state: '' }))} className={crumbBtn}>United States</button></>
                      )}
                      {focusState && (
                        <Link href={`/jurisdictions/us/${focusState.toLowerCase()}/`} className="link-arrow ml-auto text-xs">
                          {STATE_NAMES[focusState] ?? focusState} profile
                        </Link>
                      )}
                    </>
                  }
                  locator={
                    soleRegion !== 'US' && soleRegion !== 'EU' && insetHighlightIds.length ? (
                      <RegionInsetMap
                        highlightIds={insetHighlightIds}
                        countsByIso={countsByIso}
                        selectedIds={insetHighlightIds}
                        height={110}
                      />
                    ) : undefined
                  }
                />
                {soleRegion === 'US' ? (
                  <StateMap
                    data={mapData}
                    selectedState={billFilters.state || null}
                    highlightState={hoverStateAbbr}
                    onStateClick={abbr => setBillFilters(prev => ({ ...prev, state: prev.state === abbr ? '' : abbr }))}
                    height={300}
                  />
                ) : soleRegion === 'EU' ? (
                  <RegionInsetMap
                    highlightIds={insetHighlightIds}
                    countsByIso={countsByIso}
                    previewIds={hoverEuIds}
                    onCountrySelect={code => setRegions([code])}
                    height={300}
                  />
                ) : null}
              </>
            )}
          </div>

          {leaderboard.mode !== 'none' && (
            <JurisdictionTopList
              label={leaderboard.label}
              data={leaderboard.data}
              nameOf={topListName}
              selected={leaderboard.mode === 'us-states' ? billFilters.state || null : soleRegion}
              onHover={setHoverCode}
              // The full Standings board (/states adapts to the selection: the US momentum board, the
              // EU board, or the two-column States|Nations leaderboard by default).
              restHref="/states"
              onSelect={code =>
                leaderboard.mode === 'us-states'
                  ? setBillFilters(prev => ({ ...prev, state: prev.state === code ? '' : code }))
                  : setRegions([code])
              }
            />
          )}
        </aside>
      </div>

      <div className="mt-12 space-y-10">
        {/* Headlines & Deadlines — the signals that aren't bills, below the table (out of the way of
            the bills, which are what visitors came for). The Oregon court-case wildcard is US-only. */}
        <HeadlinesDeadlines>
          <ScopedDeadlineBanner />
          {isUsView && <FederalWatchBanner highRiskCount={highPreemption} />}
        </HeadlinesDeadlines>

        {/* Guided-tour CTA — a standing home for the demo-led motion (the highest-converting path for
            the considered compliance buyer). Ink, not accent: the accent is reserved for data and the
            page's one primary action. */}
        <section className="border-t border-border-default pt-8">
          <div className="flex flex-col justify-between gap-4 rounded-lg border border-border-default bg-bg-secondary px-5 py-4 sm:flex-row sm:items-center sm:px-6 sm:py-5">
            <div className="max-w-2xl">
              <h3 className="font-serif text-lg text-text-primary">Unlock the full power of the Atlas.</h3>
              <p className="mt-0.5 text-sm leading-relaxed text-text-secondary">
                Book a 15-minute walkthrough — we&apos;ll map the tracker to the materials and
                jurisdictions your team actually reports on.
              </p>
            </div>
            <button
              onClick={() => { track('cta_click', { entry_source: 'home_walkthrough' }); setWalkthroughOpen(true); }}
              className="shrink-0 rounded-md border border-text-primary px-5 py-2 text-sm font-semibold text-text-primary transition-colors hover:bg-text-primary hover:text-bg-primary"
            >
              Book a walkthrough
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

        <footer className="border-t border-border-default pt-6 pb-2 text-center">
          <Link href="/about" className="link-arrow">Learn more about the project</Link>
        </footer>
      </div>

      {/* A/B: ask Homepage-B visitors what they think of the new look (self-dismissing, once per device). */}
      {ready && variant === 'b' && <HomeVariantVote />}
    </div>
  );
}
