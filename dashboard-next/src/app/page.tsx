'use client';
import { useState, useMemo, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { useBills, useBillTextSearch, useLawsInForce } from '@/hooks/useBills';
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
import { regionLabel, REGION_CODES } from '@/components/insights/RegionFilter';
import { highlightIdsFor } from '@/components/map/RegionInsetMap';
import { EU_MEMBERS } from '@/lib/jurisdictions';
import { inScope } from '@/lib/scope';
import { useAuth, useProGate } from '@/components/auth/AuthContext';
import { LockIcon } from '@/components/ui/icons';
import { STATE_NAMES, formatDate, downloadCsv } from '@/lib/utils';
import { useResearch, ResearchThread, ResearchWall, RESEARCH_EXAMPLES } from '@/components/research/ResearchThread';
import { AiAnalysisToggle } from '@/components/search/AiAnalysisToggle';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { track } from '@/lib/analytics';
import { useHomeVariant } from '@/components/experiment/useHomeVariant';
import { HomeVariantVote } from '@/components/experiment/HomeVariantVote';
import { BillDotExplorer } from '@/components/explore/BillDotExplorer';
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
  { ssr: false, loading: () => <div className="h-[420px] bg-bg-secondary rounded-lg animate-pulse" /> }
);

/**
 * Types the example questions out, one character at a time, as the search box's placeholder — a hint
 * that the bar answers real questions, not just keyword filters. Runs only while `active` (input empty
 * and no thread yet). Types a question with an eased, human rhythm, holds it long enough to read, then
 * the whole line vanishes at once (no backspacing) and a cursor blinks for a beat before the next
 * question begins. Returns the display string (typed text + cursor); '' when idle so the caller can
 * fall back to a static placeholder.
 */
function useTypedPlaceholder(phrases: string[], active: boolean): string {
  const [text, setText] = useState('');
  const [cursorOn, setCursorOn] = useState(true);
  useEffect(() => {
    if (!active) { setText(''); setCursorOn(true); return; }
    let phrase = 0, char = 0;
    let timer: ReturnType<typeof setTimeout>;
    // Ease-out per-character delay: a touch deliberate at the start of a question, quickening as it
    // flows, with an extra beat after punctuation. Reads as typed by a person, not a metronome.
    const charDelay = (s: string, i: number) => {
      const prev = s[i - 1];
      if (prev === ',') return 240;
      if (prev === '.' || prev === '?') return 300;
      const p = i / s.length;              // 0 → 1 across the question
      const ease = 1 - 0.6 * p * (2 - p);  // ease-out: ~1.0 early → ~0.4 late
      return 34 + 46 * ease;               // ~80ms at the start → ~52ms by the end
    };
    const typeNext = () => {
      const current = phrases[phrase % phrases.length];
      char++;
      setText(current.slice(0, char));
      if (char >= current.length) { timer = setTimeout(vanish, 3000); return; }
      timer = setTimeout(typeNext, charDelay(current, char));
    };
    const vanish = () => { setText(''); blink(0); };        // clear the whole line at once
    const blink = (n: number) => {
      if (n >= 3) {                                         // ~3 toggles, then the next question
        setCursorOn(true);
        phrase++; char = 0;
        timer = setTimeout(typeNext, 260);
        return;
      }
      setCursorOn(c => !c);
      timer = setTimeout(() => blink(n + 1), 420);
    };
    timer = setTimeout(typeNext, 650);
    return () => clearTimeout(timer);
  }, [active, phrases]);
  // Cursor stays solid while typing/holding; the blink state only toggles in the gap between
  // questions. A figure space (U+2007) for the "off" frame keeps the placeholder width steady.
  return active ? text + (cursorOn ? '▏' : ' ') : '';
}

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
  // Enacted laws in force by region — the SAME source the globe shades from, so the "Top Regions"
  // ticker ranks identically to the map (combined national + sub-national enacted).
  const { data: lawsInForce = [] } = useLawsInForce();

  const { scope } = useScope();
  const scopeActive = useScopeActive();

  const { isPro, user, openAuth } = useAuth();
  const gatePro = useProGate();

  // Homepage A/B: variant "b" swaps the bill table for the dot-explorer (client-side bucketing, since
  // the site is a static export). Everything else — ticker, globe, Explore bar — is shared.
  const { variant, ready } = useHomeVariant();

  // Guided-tour capture — the demo-led path (our highest-converting motion for the considered
  // compliance buyer). Opens the shared request-access form, tagged source="home_walkthrough".
  const [walkthroughOpen, setWalkthroughOpen] = useState(false);

  // The unified surface: one adaptive bar. Typing filters the table live (Explorer); submitting a
  // question routes to the grounded, cited research answer over the same corpus (Ask the Atlas).
  const research = useResearch();
  const [query, setQuery] = useState('');
  // "AI Analysis" mode — OFF (default) = classic keyword filtering of the table; ON unlocks asking
  // grounded, cited questions (and reveals the Ask button). Persisted in localStorage: server render
  // OFF, read the stored value on mount to avoid a hydration mismatch (mirrors BetaContext).
  const [aiMode, setAiModeState] = useState(false);
  useEffect(() => {
    try { setAiModeState(localStorage.getItem('ai_analysis_mode') === '1'); } catch { /* ignore */ }
  }, []);
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
  const submitQuery = () => {
    if (!aiMode) return;             // asking is only possible in AI Analysis mode
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

  // Cycle the example questions through the search-box placeholder, typewriter-style — but only before
  // the reader has typed or asked anything, so the animation never fights a real query.
  const typedPlaceholder = useTypedPlaceholder(RESEARCH_EXAMPLES, !research.hasAsked && query === '');

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
          question and is reaching for a second (research.freeAskUsed). A fresh visitor gets the clean
          Explore/Ask surface first; the "start free" pitch only lands once they've engaged and hit the
          limit. Never shown to users who've already converted. */}
      {!user && research.freeAskUsed && (
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

      {/* Map/globe — moved up to sit right below the ticker. Hidden while a question is active. The
          Regions selector that drives it lives in the Explore facets just below. */}
      {!research.active && (
        <section>
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
              height={380}
            />
          ) : insetHighlightIds.length ? (
            <RegionInsetMap
              highlightIds={insetHighlightIds}
              caption={soleRegion === 'EU' ? 'European Union · 27 member states — click a country to drill in' : `${regionLabel(soleRegion)} · national law`}
              count={regionCounts[soleRegion]}
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
      )}

      {/* Explore: one adaptive search/ask bar + facets */}
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

        {/* How it works — sits ABOVE the bar so the bar itself reads as the primary action, and so the
            control row + facets can align directly under the input. */}
        <p className="mb-2 text-xs text-text-muted">
          <b className="text-text-secondary font-medium">Type keywords</b> to filter the bills instantly ·{' '}
          <b className="text-text-secondary font-medium">flip on AI Analysis</b> to ask a full question for a grounded, cited answer over the same corpus.
        </p>

        {/* The search box. Enter submits a question only when AI Analysis is on (submitQuery guards it). */}
        <form onSubmit={e => { e.preventDefault(); submitQuery(); }}>
          <div className="flex items-center gap-2 rounded-xl border-2 border-green-accent/60 bg-bg-secondary px-3 py-2 focus-within:border-green-accent transition-colors">
            <span aria-hidden className="text-text-muted text-lg leading-none">⌕</span>
            <input
              value={query}
              onChange={e => onSearchChange(e.target.value)}
              placeholder={
                aiMode
                  ? (research.hasAsked ? 'Ask a follow-up…' : (typedPlaceholder || 'Ask a question about the corpus…'))
                  : 'Search bills by keyword…'
              }
              aria-label={aiMode ? 'Ask a question' : 'Search bills by keyword'}
              className="flex-1 min-w-0 bg-transparent text-body text-text-primary placeholder-text-muted focus:outline-none"
            />
          </div>
        </form>

        {/* Control row UNDER the bar: AI Analysis toggle + Ask (AI mode only) lead; the facets share the
            same row on desktop and wrap below on mobile (toggle+Ask first, then filters). Kept OUT of the
            <form> so a facet dropdown can never accidentally submit a question. */}
        <div className="mt-3 mb-4 flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-text-primary/15 pb-4">
          <div className="flex items-center gap-3 shrink-0">
            <AiAnalysisToggle on={aiMode} onChange={setAiMode} />
            {/* Ask is ALWAYS visible so the capability is discoverable; it's just disabled until AI
                Analysis is on (and there's a long-enough question). submitQuery no-ops when off. */}
            <button
              type="button"
              onClick={submitQuery}
              disabled={!aiMode || research.busy || query.trim().length < 3}
              title={!aiMode ? 'Turn on AI Analysis to ask a question' : undefined}
              className="shrink-0 rounded-lg bg-green-accent text-bg-primary font-medium text-sm px-5 py-2 hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {research.busy ? 'Thinking…' : research.hasAsked ? 'Ask follow-up' : 'Ask →'}
            </button>
          </div>
          <div className="min-w-0 flex-1">
            <BillFilters filters={billFilters} onChange={setBillFilters} hideSearch showRegion resinOptions={resinOptions} />
          </div>
        </div>

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
      {/* Map/globe moved up — it now renders right below the ticker (see above). */}

      {/* Bill results table. The personalize-scope bar (state/material/product) sits here, just above
          the table, instead of globally under the nav. */}
      <section>
        <div className="mb-3"><ScopeBar /></div>
        {/* Only fires when live AND snapshot/localStorage all came up empty — otherwise
            last-known data shows with a quiet FreshnessNote instead of a scary banner. */}
        {billsError && <AlertBanner variant="red" message="We're having trouble loading bill data right now — please refresh in a moment." className="mb-3" />}
        {billsLoading ? (
          <SkeletonList rows={5} />
        ) : variant === 'b' ? (
          <BillDotExplorer bills={tableBills} />
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

      {/* Guided-tour CTA — a standing home for the demo-led motion, distinct from the free-signup and
          referral CTAs. A 15-min walkthrough is the highest-converting path for the considered
          compliance buyer, so it gets its own band above the newsletter signup. */}
      <section className="border-t border-border-default pt-8">
        <div className="rounded-xl border border-green-accent/30 bg-green-hero px-5 py-4 sm:px-6 sm:py-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="max-w-2xl">
            <h3 className="font-serif text-lg text-text-primary">See Atlas on your own obligations.</h3>
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
