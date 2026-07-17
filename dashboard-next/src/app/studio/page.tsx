'use client';
/**
 * Packaging Studio — a scrolling decision-consequence walkthrough.
 *
 * One page, three full-height scroll-snap sections:
 *
 *   1. Build it       — name/markets/units live in the sticky spec bar; then one
 *                       component at a time: pick a material, see the consequence
 *                       immediately (annual-fee delta vs best-in-family, the
 *                       eco-modulation why, and the obligations it attaches).
 *   2. The punch list — what this package owes, and by when. Plain-language
 *                       action sentences over the guard verdict (the guard.ts
 *                       rules are unchanged — this is presentation only).
 *   3. The Studio     — the full workbench (cost curves, obligations, the
 *                       "for your engineering team" CI export).
 *
 * The progress track is a scrollspy (IntersectionObserver); clicking a track
 * item smooth-scrolls to that section (instant under prefers-reduced-motion).
 * Returning users: if the URL hash already encodes a spec (share link /
 * reload), the page opens scrolled to the Studio. The spec is kept in sync
 * with the hash at all times so any stage is shareable.
 *
 * Law rows behave like bills everywhere else on the site: clicking opens the
 * Bill Explorer's detail modal (BillModal + fetchBill), and each row carries a
 * WatchStar keyed on the pathways feed's numeric bill_id.
 *
 * All quote/guard logic lives in src/lib/studio.ts + src/lib/guard.ts; this
 * file is presentation and stage choreography only.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { BillModal } from '@/components/ui/BillModal';
import { WatchStar } from '@/components/watchlist/WatchStar';
import { SubscribeForm } from '@/components/about/SubscribeForm';
import { useRegion } from '@/components/layout/RegionContext';
import { useAuth } from '@/components/auth/AuthContext';
import { useBeta } from '@/components/settings/BetaContext';
import { fetchBill } from '@/lib/api';
import type { BillSummary } from '@/lib/types';
import { formatDate } from '@/lib/utils';
import {
  FALLBACK_SCHEDULE,
  GITHUB_ACTIONS_SNIPPET,
  MARKETS,
  buildQuote,
  centsPerPackage,
  decodeSpecFromHash,
  encodeSpecToHash,
  familyConsequence,
  feeScheduleFromSchedule,
  fetchFeeSchedule,
  fetchPathwaysForMarkets,
  groupPaletteByFamily,
  makeFmt,
  pruneAttrs,
  ratePerTonne,
  remapComponentsToSchedule,
  specToYaml,
  type FeeSchedule,
  type Fmt,
  type MaterialCategory,
  type PaletteFamily,
  type Quote,
  type QuoteComponent,
  type SpecComponent,
  type StudioSpec,
} from '@/lib/studio';
import { getSchedule, type AttributeInput, type PackageAttributes } from '@/lib/feeSchedule';
import { evaluate, type Finding, type GuardPathway } from '@/lib/guard';
import {
  SavedPackagesPanel,
  useSavedPackages,
  type SavedPackage,
  type SaveState,
} from '@/components/studio/SavedPackages';
import { track } from '@/lib/analytics';

// ---------------------------------------------------------------------------
// Currency-aware formatting — the active schedule's Fmt, supplied via context so
// every sub-component renders in that schedule's currency ($/¢, £/p, ¥…).
//   fmt.money(minorUnits) · rate(perTonne) · amount(major) · compact(major)
// ---------------------------------------------------------------------------
const FmtCtx = createContext<Fmt>(makeFmt('USD'));
const useFmt = () => useContext(FmtCtx);

/** The fee schedules the studio can price against. 'ca' uses the live/bundled CA
 *  fetch; the rest are built from registered engine Schedules (feeSchedule.ts). */
const SCHEDULE_OPTIONS: { id: string; label: string; jurisdiction: string | null }[] = [
  { id: 'ca', label: 'California SB-54', jurisdiction: null },
  { id: 'UK', label: 'UK pEPR', jurisdiction: 'UK' },
  { id: 'JP', label: 'Japan JCPRA', jurisdiction: 'JP' },
];

function daysTo(d: string | null): number | null {
  if (!d) return null;
  return Math.round((new Date(d).getTime() - Date.now()) / 864e5);
}

/** Bar color on the cheapest→dearest rank (0 = cheapest, 1 = dearest). */
function rateColor(rank: number): string {
  if (rank < 0.2) return '#22c55e';
  if (rank < 0.55) return '#f59e0b';
  return '#ef4444';
}

const DEFAULT_COMPONENTS: SpecComponent[] = [
  { key: 'c0', name: 'Bottle', material: 'pet_clear', grams: 22 },
  { key: 'c1', name: 'Cap', material: 'pp_ps', grams: 3 },
  { key: 'c2', name: 'Label', material: 'paperboard', grams: 2 },
];
const DEFAULT_MARKETS = ['CA', 'OR'];

/** The untouched-studio spec, hash-encoded — the auto-load guard compares against this so a
 *  returning user's last saved package only replaces a pristine studio, never their edits. */
const PRISTINE_HASH = encodeSpecToHash({
  product: 'Untitled package',
  components: DEFAULT_COMPONENTS,
  markets: DEFAULT_MARKETS,
  unitsPerYear: null,
  acknowledged: [],
});

/** Studio material family → the subscription flow's material_category slug
 *  (the MATERIAL_CATEGORIES vocabulary in BillFilters / the alerts backend). */
const SUBSCRIBE_MATERIAL: Record<MaterialCategory, string> = {
  plastic_packaging: 'plastic_packaging',
  plastic_film: 'plastic_packaging',
  paper_packaging: 'paper_packaging',
  glass_packaging: 'glass',
  aluminum_packaging: 'metals',
};

// ---------------------------------------------------------------------------
// Stage choreography — three scroll-snap sections + a scrollspy track
// ---------------------------------------------------------------------------
const STAGES = [
  { id: 'build', label: 'Build', title: 'Build it' },
  { id: 'punch-list', label: 'Punch list', title: 'The punch list' },
  { id: 'studio', label: 'Studio', title: 'The Studio' },
] as const;

const PRIMARY_BTN =
  'inline-flex items-center justify-center gap-2 rounded-lg bg-green-accent text-bg-primary px-5 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60';
const SECONDARY_BTN =
  'inline-flex items-center justify-center rounded-lg border border-border-default bg-bg-tertiary px-4 py-2 text-sm text-text-secondary hover:border-green-accent hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60';

/** Page-scoped CSS: consequence reveal (motion-safe) + scroll-snap. Snap is
 *  `proximity`, not `mandatory`, so the page never fights the reader; sections
 *  stay in normal document flow, so tab order and keyboard reachability are
 *  untouched. The <style> unmounts with the page, so the html rule can't leak
 *  into other routes. */
const STUDIO_CSS = `
@keyframes studio-consequence-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: none; }
}
.studio-consequence-in { animation: studio-consequence-in 340ms cubic-bezier(0.22, 1, 0.36, 1); }
@media (prefers-reduced-motion: reduce) {
  .studio-consequence-in { animation: none; }
}
html { scroll-snap-type: y proximity; }
.studio-section { scroll-snap-align: start; scroll-margin-top: 10.5rem; }
@media (max-width: 640px) { .studio-section { scroll-margin-top: 8rem; } }
`;

export default function PackagingStudioPage() {
  // ---- the spec (persists across all stages) ----
  const [product, setProduct] = useState('Untitled package');
  const [components, setComponents] = useState<SpecComponent[]>(DEFAULT_COMPONENTS);
  const [markets, setMarkets] = useState<string[]>(DEFAULT_MARKETS);
  const [units, setUnits] = useState('');
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [ackDraft, setAckDraft] = useState('');
  const uid = useRef(DEFAULT_COMPONENTS.length);
  const hydrated = useRef(false);
  /** True once the hash spec (if any) has been restored — gates spec-dependent
   *  one-shot children like the subscribe form's prefill. */
  const [booted, setBooted] = useState(false);

  // ---- stage state ----
  const [stage, setStage] = useState(0); // scrollspy: which section is in view
  const [activeIdx, setActiveIdx] = useState(0); // Build-stage component cursor
  const sectionRefs = useRef<(HTMLElement | null)[]>([]);

  // ---- data layers ----
  const [schedule, setSchedule] = useState<FeeSchedule>(FALLBACK_SCHEDULE); // the CA fetch
  const [scheduleId, setScheduleId] = useState<string>('ca'); // which fee schedule is active
  const [scheduleReady, setScheduleReady] = useState(false);
  const [pathways, setPathways] = useState<Record<string, GuardPathway[]>>({});
  const [pathwaysLoading, setPathwaysLoading] = useState(false);
  const [copied, setCopied] = useState<'snippet' | 'link' | null>(null);

  // ---- bill detail modal (the Bill Explorer's, reused) ----
  const [detailBill, setDetailBill] = useState<BillSummary | null>(null);
  const [openingBillId, setOpeningBillId] = useState<number | null>(null);

  const { isUsView } = useRegion();
  const { showToast, isPro, isAdmin, user, openAuth } = useAuth();
  const { betaEnabled } = useBeta();
  const saved = useSavedPackages();
  /** True when the URL opened with a spec in it (share link / reload) — that spec always wins
   *  over the auto-loaded last save. */
  const hadHashSpec = useRef(false);
  const autoLoaded = useRef(false);

  // Restore a shared spec from the URL hash. A hash spec means a returning user
  // or a share link — skip the walkthrough and open scrolled to the Studio.
  useEffect(() => {
    const fromHash = decodeSpecFromHash(window.location.hash);
    if (fromHash) {
      hadHashSpec.current = true;
      if (fromHash.product) setProduct(fromHash.product);
      // Restore the schedule BEFORE components so their material ids resolve against the right palette.
      if (fromHash.scheduleId) setScheduleId(fromHash.scheduleId);
      if (fromHash.components.length) {
        setComponents(fromHash.components);
        uid.current = fromHash.components.length;
      }
      setMarkets(fromHash.markets);
      if (fromHash.unitsPerYear) setUnits(String(fromHash.unitsPerYear));
      if (fromHash.acknowledged?.length) setAcknowledged(fromHash.acknowledged);
      setStage(2);
      // Jump (instant, not smooth) straight to the Studio section for share links.
      requestAnimationFrame(() => {
        sectionRefs.current[2]?.scrollIntoView({ behavior: 'auto', block: 'start' });
      });
    }
    hydrated.current = true;
    setBooted(true);
  }, []);

  // Scrollspy: the progress track follows whichever section is in the middle
  // band of the viewport.
  useEffect(() => {
    const els = sectionRefs.current.filter(Boolean) as HTMLElement[];
    if (els.length === 0 || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          const idx = sectionRefs.current.indexOf(e.target as HTMLElement);
          if (idx >= 0) setStage(idx);
        }
      },
      { rootMargin: '-40% 0px -55% 0px' },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  // Live fee schedule (bundled draft table until / unless the endpoint responds).
  useEffect(() => {
    let alive = true;
    fetchFeeSchedule().then((s) => {
      if (!alive) return;
      setSchedule(s);
      setScheduleReady(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  // Live pathways fan-out whenever the market set changes.
  useEffect(() => {
    if (!hydrated.current) return;
    let alive = true;
    setPathwaysLoading(true);
    fetchPathwaysForMarkets(markets).then((byMarket) => {
      if (!alive) return;
      setPathways(byMarket);
      setPathwaysLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [markets]);

  const spec: StudioSpec = useMemo(
    () => ({
      product,
      components,
      markets,
      unitsPerYear: Number(units) > 0 ? Number(units) : null,
      acknowledged,
      scheduleId,
    }),
    [product, components, markets, units, acknowledged, scheduleId],
  );

  // Keep the URL hash in sync so the link reopens this exact package.
  useEffect(() => {
    if (!hydrated.current || typeof window === 'undefined') return;
    const hash = encodeSpecToHash(spec);
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${hash}`);
  }, [spec]);

  // The active fee schedule: 'ca' is the live/bundled CA fetch; any other id is a
  // registered engine Schedule adapted to the studio's UI shape. Falls back to CA if
  // a registry lookup misses (so the studio always prices).
  const activeSchedule: FeeSchedule = useMemo(() => {
    if (scheduleId === 'ca') return schedule;
    const reg = getSchedule(scheduleId);
    return reg ? feeScheduleFromSchedule(reg) : schedule;
  }, [scheduleId, schedule]);

  // Formatter bound to the active schedule's currency — provided to the whole tree.
  const fmt = useMemo(() => makeFmt(activeSchedule.engine.currency), [activeSchedule]);

  // ---- derived: the quote + the punch-list verdict, recomputed live ----
  const quote: Quote = useMemo(
    () => buildQuote(spec, pathways, activeSchedule),
    [spec, pathways, activeSchedule],
  );

  const specMaterials = useMemo(
    () => [...new Set(quote.components.map((c) => c.category))],
    [quote],
  );

  const guardReport = useMemo(
    () =>
      evaluate(
        { product, markets, materials: specMaterials, acknowledged },
        pathways,
      ),
    [product, markets, specMaterials, acknowledged, pathways],
  );

  const families = useMemo(() => groupPaletteByFamily(activeSchedule.palette), [activeSchedule]);

  // Source links for EVERY priceable schedule (not just the active one) — so the claim "we price on
  // the CA SB-54 / UK pEPR / JP JCPRA schedule" is one click from the actual published table.
  const scheduleSources = useMemo(
    () =>
      SCHEDULE_OPTIONS.map((o) => {
        if (o.id === 'ca') {
          return { id: o.id, label: o.label, sourceUrl: schedule.sourceUrl, provenance: schedule.engine.provenance };
        }
        const reg = o.jurisdiction ? getSchedule(o.jurisdiction) : undefined;
        return { id: o.id, label: o.label, sourceUrl: reg?.sourceUrl ?? null, provenance: reg?.provenance ?? null };
      }),
    [schedule],
  );

  // Switch fee schedule, remapping the package's components onto the new palette so
  // the structure survives (a plastic component stays plastic). Weights are kept.
  const switchSchedule = useCallback(
    (id: string) => {
      if (id === scheduleId) return;
      const target = id === 'ca' ? schedule : (() => {
        const reg = getSchedule(id);
        return reg ? feeScheduleFromSchedule(reg) : schedule;
      })();
      setComponents((cs) => remapComponentsToSchedule(cs, activeSchedule.palette, target.palette));
      setScheduleId(id);
      setActiveIdx(0);
      track('studio_schedule_switch', { schedule: id });
    },
    [scheduleId, schedule, activeSchedule],
  );

  // Subscription prefill: the spec's material families, translated to alert slugs.
  const subscribeMaterials = useMemo(
    () => [...new Set(specMaterials.map((c) => SUBSCRIBE_MATERIAL[c] ?? 'plastic_packaging'))],
    [specMaterials],
  );

  // ---- bench handlers ----
  const paletteById = useMemo(() => new Map(activeSchedule.palette.map((m) => [m.id, m])), [activeSchedule]);

  const goTo = useCallback((n: number) => {
    setStage(n);
    const el = sectionRefs.current[n];
    if (!el) return;
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }, []);

  const addComponent = () => {
    const mat = paletteById.get('glass') ?? activeSchedule.palette[0];
    setComponents((cs) => [
      ...cs,
      { key: `c${uid.current++}`, name: 'New component', material: mat.id, grams: mat.default_g },
    ]);
    setActiveIdx(components.length); // walk straight to the new component
  };

  const updateComponent = (key: string, patch: Partial<SpecComponent>) =>
    setComponents((cs) => cs.map((c) => (c.key === key ? { ...c, ...patch } : c)));

  const removeComponent = (key: string) =>
    setComponents((cs) => (cs.length > 1 ? cs.filter((c) => c.key !== key) : cs));

  const setMaterial = (key: string, materialId: string) => {
    const mat = paletteById.get(materialId);
    if (!mat) return;
    updateComponent(key, { material: mat.id, grams: mat.default_g });
  };

  const toggleMarket = (code: string) =>
    setMarkets((ms) => (ms.includes(code) ? ms.filter((m) => m !== code) : [...ms, code]));

  // Load a saved package back into the studio — same restore path as a share-link hash.
  const loadSaved = useCallback(
    (pkg: SavedPackage, opts?: { auto?: boolean }) => {
      const s = decodeSpecFromHash(pkg.hash);
      if (!s) return;
      setProduct(s.product || 'Untitled package');
      setScheduleId(s.scheduleId || 'ca'); // before components, so materials resolve
      if (s.components.length) {
        setComponents(s.components);
        uid.current = s.components.length;
      }
      setMarkets(s.markets);
      setUnits(s.unitsPerYear ? String(s.unitsPerYear) : '');
      setAcknowledged(s.acknowledged ?? []);
      setActiveIdx(0);
      if (opts?.auto) showToast(`Picked up where you left off — loaded “${pkg.name}”.`);
      track('studio_package_load', { auto: Boolean(opts?.auto) });
    },
    [showToast],
  );

  // Returning signed-in user, no spec in the URL: reopen their most recently saved package.
  // Only ever replaces a pristine studio — anything they've already touched stays put.
  useEffect(() => {
    if (!booted || !saved.ready || autoLoaded.current || hadHashSpec.current) return;
    autoLoaded.current = true;
    if (saved.packages.length === 0) return;
    if (encodeSpecToHash(spec) !== PRISTINE_HASH) return;
    const latest = [...saved.packages].sort((a, b) => b.savedAt.localeCompare(a.savedAt))[0];
    loadSaved(latest, { auto: true });
  }, [booted, saved.ready, saved.packages, spec, loadSaved]);

  const addAck = (value: string) => {
    const v = value.trim();
    if (!v) return;
    setAcknowledged((a) => (a.some((x) => x.toLowerCase() === v.toLowerCase()) ? a : [...a, v]));
    setAckDraft('');
  };
  const removeAck = (value: string) => setAcknowledged((a) => a.filter((x) => x !== value));

  // Open a law the way the Bill Explorer does — its detail modal; if the fetch
  // fails, fall back to the explorer's own deep link (/?bill=<id>).
  const openBill = useCallback(async (billId: number) => {
    setOpeningBillId(billId);
    try {
      setDetailBill(await fetchBill(billId));
    } catch {
      window.location.assign(`/?bill=${billId}`);
    } finally {
      setOpeningBillId(null);
    }
  }, []);

  // ---- export for the engineering team ----
  const yaml = useMemo(
    () =>
      specToYaml({
        product,
        markets,
        materials: specMaterials,
        acknowledged,
      }),
    [product, markets, specMaterials, acknowledged],
  );

  const downloadYaml = () => {
    const blob = new Blob([yaml], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'packaging.yaml';
    a.click();
    URL.revokeObjectURL(url);
  };

  const copy = async (what: 'snippet' | 'link') => {
    try {
      await navigator.clipboard.writeText(what === 'snippet' ? GITHUB_ACTIONS_SNIPPET : window.location.href);
      setCopied(what);
      setTimeout(() => setCopied(null), 1600);
    } catch {
      /* clipboard unavailable — the <pre> is selectable */
    }
  };

  // ---- Build-stage cursor, clamped against removals ----
  const safeIdx = components.length ? Math.min(activeIdx, components.length - 1) : 0;
  const activeComp = components[safeIdx] ?? null;
  const activeQuote = activeComp
    ? quote.components.find((qc) => qc.key === activeComp.key) ?? null
    : null;

  const t = quote.totals;
  const ob = quote.obligations;

  // Packaging Studio is a Pro membership feature. Non-members get a lock (all hooks above already ran,
  // so this early return is rules-of-hooks safe).
  if (!isPro && !isAdmin) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <GazetteHeader
          title="Packaging Studio"
          subtitle="Build a package one decision at a time — see what every material pick costs, then get the punch list of what it owes."
        />
        <div className="surface-card p-6 mt-6 space-y-3 text-center">
          <h2 className="font-serif text-xl text-text-primary">A Pro membership feature</h2>
          <p className="text-text-secondary max-w-xl mx-auto">
            The Packaging Studio prices your package against live producer-fee schedules and hands you
            the exact compliance punch list. It&apos;s included with a Pro membership.
          </p>
          <div className="flex justify-center gap-2 pt-1">
            {!user && (
              <button
                type="button"
                onClick={openAuth}
                className="rounded-full border border-border-default px-5 py-2 text-sm text-text-secondary hover:text-text-primary"
              >
                Sign in
              </button>
            )}
            <Link href="/pricing" className="rounded-full bg-green-accent px-5 py-2 text-sm font-medium text-bg-primary hover:opacity-90">
              See memberships
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <FmtCtx.Provider value={fmt}>
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      <style>{STUDIO_CSS}</style>
      <GazetteHeader
        title="Packaging Studio"
        subtitle="Build a package one decision at a time — see what every material pick costs, then get the punch list of what it owes."
      />

      {/* Fee-schedule picker — which jurisdiction's producer-fee table to price against. */}
      <ScheduleSwitcher active={scheduleId} onSwitch={switchSchedule} sources={scheduleSources} />

      {/* Honest scoping when the global region view isn't US — don't block, just say it. */}
      {!isUsView && scheduleId === 'ca' && (
        <AlertBanner
          variant="amber"
          message="Fees here are priced on California's SB-54 schedule, US states only — switch the fee schedule above to price against another jurisdiction."
        />
      )}

      {/* Foreign fee schedule active: the fee table is that jurisdiction's, but the "Sells into"
          markets + punch-list obligations below are US-state-based only. Say so rather than imply a
          US selection means anything under UK/JP pricing. */}
      {scheduleId !== 'ca' && (
        <AlertBanner
          variant="amber"
          message={`Pricing against ${activeSchedule.engine.program}. Obligation tracking (the punch list and "Sells into" markets below) is US-state only today — the ${activeSchedule.engine.program} fee table drives the costs, not the US markets.`}
        />
      )}

      {/* Progress track — a scrollspy; click to scroll to any section */}
      <ProgressTrack stage={stage} onGo={goTo} />

      {/* Sticky spec bar — name the product, pick markets, set volume; repriced live */}
      <SpecBar
        product={product}
        onProduct={setProduct}
        markets={markets}
        onToggleMarket={toggleMarket}
        units={units}
        onUnits={setUnits}
        quote={quote}
        loading={pathwaysLoading}
        onSave={() => saved.save(spec)}
        saveState={saved.saveState}
      />

      {/* ================= Section 1 · Build it ================= */}
      <section
        id="build"
        ref={(el) => {
          sectionRefs.current[0] = el;
        }}
        aria-labelledby="build-heading"
        className="studio-section min-h-[calc(100dvh-12rem)] max-w-3xl mx-auto w-full space-y-4"
      >
        <div>
          <h2 id="build-heading" className="font-serif text-xl text-text-primary">
            {STAGES[0].title}
          </h2>
          <p className="mt-1 text-sm text-text-secondary leading-relaxed">
            Name it in the bar above, then walk the package one component at a time. Pick a material
            and see the consequence immediately — what the choice costs against the best format in
            its family, and what it obligates you to do.
          </p>
        </div>

        {/* First-run coaching — a dismissible three-step walkthrough (remembered per browser). */}
        <BuildCoach />

        {/* The regulatory clock — the anchor every fee below hangs on */}
        <div className="rounded-lg border border-border-default bg-bg-tertiary p-3.5 flex gap-3">
          <span aria-hidden className="text-lg leading-none text-text-muted mt-0.5">◷</span>
          <p className="text-xs text-text-secondary leading-relaxed">
            <b className="text-text-primary">The regulatory clock:</b> every fee in this studio is
            priced on the{' '}
            <b className="text-text-primary">{activeSchedule.engine.program} schedule</b>{' '}
            ({activeSchedule.engine.provenance}), in{' '}
            <b className="text-text-primary">{fmt.currency}</b> — the best published basis today, not
            an invoice.
          </p>
        </div>

        {/* component cursor strip — every chip removable, add clearly labeled */}
        <div className="flex flex-wrap items-center gap-1.5">
          {components.map((c, i) => {
            const qc = quote.components.find((q) => q.key === c.key);
            const on = i === safeIdx;
            return (
              <span
                key={c.key}
                className={`inline-flex items-center gap-0.5 rounded-full border pl-3 pr-1 py-1 text-xs transition-colors ${
                  on
                    ? 'border-green-accent bg-green-dark/40 text-text-primary font-medium'
                    : 'border-border-default bg-bg-tertiary text-text-secondary'
                }`}
              >
                <button
                  type="button"
                  onClick={() => setActiveIdx(i)}
                  aria-pressed={on}
                  className="inline-flex items-baseline gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 rounded-full"
                >
                  {c.name || 'Component'}
                  {qc && <span className="font-mono text-meta text-text-muted">{fmt.money(qc.cents_per_package)}</span>}
                </button>
                {components.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeComponent(c.key)}
                    aria-label={`Remove ${c.name || 'component'}`}
                    title={`Remove ${c.name || 'component'}`}
                    className="rounded-full px-1.5 py-0.5 leading-none text-text-muted hover:text-urgency-high transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
                  >
                    ×
                  </button>
                )}
              </span>
            );
          })}
          <button
            type="button"
            onClick={addComponent}
            className="rounded-full border border-dashed border-border-default px-3 py-1 text-xs text-text-secondary hover:border-green-accent hover:text-green-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
          >
            ＋ Add component
          </button>
        </div>

        {activeComp ? (
          <>
            <div className="rounded-panel border border-border-default bg-bg-secondary p-4 space-y-4">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <span className="text-meta uppercase tracking-wider text-text-muted">
                  Component {safeIdx + 1} of {components.length}
                </span>
                <input
                  type="text"
                  value={activeComp.name}
                  onChange={(e) => updateComponent(activeComp.key, { name: e.target.value })}
                  className="flex-1 min-w-[10rem] rounded-md border border-border-default bg-bg-primary px-2.5 py-1.5 text-sm font-semibold text-text-primary focus:outline-none focus:ring-2 focus:ring-green-accent/50"
                  aria-label="Component name"
                />
                <label className="flex items-center gap-2 text-xs text-text-secondary" htmlFor={`bg-${activeComp.key}`}>
                  weight
                  <input
                    id={`bg-${activeComp.key}`}
                    type="number"
                    min={0}
                    step={1}
                    value={activeComp.grams}
                    onChange={(e) => updateComponent(activeComp.key, { grams: Number(e.target.value) || 0 })}
                    className="w-20 rounded-md border border-border-default bg-bg-primary px-2 py-1 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-green-accent/50"
                  />
                  g / unit
                </label>
              </div>

              <MaterialPicker
                families={families}
                schedule={activeSchedule}
                currentId={activeComp.material}
                onPick={(id) => setMaterial(activeComp.key, id)}
              />

              <AttributeControls
                inputs={activeSchedule.engine.inputs ?? []}
                attrs={activeComp.attrs}
                onChange={(patch) =>
                  updateComponent(activeComp.key, { attrs: pruneAttrs({ ...activeComp.attrs, ...patch }) })
                }
              />
            </div>

            {/* THE CONSEQUENCE — re-mounts (and re-animates) on every pick */}
            {activeQuote && (
              <ConsequenceReveal
                key={`${activeComp.key}:${activeComp.material}`}
                qc={activeQuote}
                unitsPerYear={spec.unitsPerYear ?? null}
                markets={markets}
                programName={activeSchedule.engine.program}
                onOpenBill={openBill}
                openingBillId={openingBillId}
              />
            )}

            <div className="flex items-center justify-between gap-3">
              {safeIdx > 0 ? (
                <button type="button" className={SECONDARY_BTN} onClick={() => setActiveIdx(safeIdx - 1)}>
                  ← Previous component
                </button>
              ) : (
                <span />
              )}
              {safeIdx < components.length - 1 ? (
                <button type="button" className={PRIMARY_BTN} onClick={() => setActiveIdx(safeIdx + 1)}>
                  Next component →
                </button>
              ) : (
                <button type="button" className={PRIMARY_BTN} onClick={() => goTo(1)}>
                  To the punch list →
                </button>
              )}
            </div>
          </>
        ) : (
          <p className="text-text-muted italic text-sm">Add a component to price its EPR exposure.</p>
        )}
      </section>

      {/* ================= Section 2 · The punch list ================= */}
      <section
        id="punch-list"
        ref={(el) => {
          sectionRefs.current[1] = el;
        }}
        aria-labelledby="punch-heading"
        className="studio-section min-h-[calc(100dvh-12rem)] max-w-3xl mx-auto w-full space-y-4"
      >
        <div>
          <h2 id="punch-heading" className="font-serif text-xl text-text-primary">
            {STAGES[1].title}
          </h2>
          <p className="mt-1 text-sm text-text-secondary leading-relaxed">
            What this package owes, and by when — based on the markets you picked.
          </p>
        </div>

        <PunchList
          report={guardReport}
          loading={pathwaysLoading}
          defaultOpen
          onMarkHandled={(f) => addAck(`${f.market}:${f.billNumber}`)}
          onOpenBill={openBill}
          openingBillId={openingBillId}
          onFixInBuild={() => goTo(0)}
        />

        <div className="flex items-center justify-between gap-3">
          <button type="button" className={SECONDARY_BTN} onClick={() => goTo(0)}>
            ← Back to the build
          </button>
          <button type="button" className={PRIMARY_BTN} onClick={() => goTo(2)}>
            Open the studio →
          </button>
        </div>
      </section>

      {/* ================= Section 3 · The Studio (full workbench) ================= */}
      <section
        id="studio"
        ref={(el) => {
          sectionRefs.current[2] = el;
        }}
        aria-labelledby="studio-heading"
        className="studio-section min-h-[calc(100dvh-12rem)] space-y-4"
      >
        <h2 id="studio-heading" className="font-serif text-xl text-text-primary">
          {STAGES[2].title}
        </h2>

        <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
          {/* ---- LEFT: the bench ---- */}
          {/* min-w-0: without it the CI snippet's <pre> sets the track's intrinsic
              width and the whole page overflows horizontally on phones. */}
          <div className="space-y-6 min-w-0">
            <section className="rounded-panel border border-border-default bg-bg-secondary p-4">
              <p className="text-meta uppercase tracking-wider text-text-muted mb-1.5">The package</p>
              <div className="space-y-2.5">
                {components.map((c) => (
                  <div key={c.key} className="rounded-lg border border-border-default bg-bg-tertiary p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <input
                        type="text"
                        value={c.name}
                        onChange={(e) => updateComponent(c.key, { name: e.target.value })}
                        className="flex-1 min-w-0 bg-transparent text-sm font-semibold text-text-primary focus:outline-none"
                        aria-label="Component name"
                      />
                      {components.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeComponent(c.key)}
                          className="shrink-0 text-text-muted hover:text-urgency-high text-base leading-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 rounded"
                          aria-label={`Remove ${c.name}`}
                          title="Remove component"
                        >
                          ×
                        </button>
                      )}
                    </div>
                    <select
                      value={c.material}
                      onChange={(e) => setMaterial(c.key, e.target.value)}
                      className="w-full rounded-md border border-border-default bg-bg-primary px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-green-accent/50"
                      aria-label="Material format"
                    >
                      {families.map((g) => (
                        <optgroup key={g.category} label={g.label}>
                          {g.options.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.label}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                    <div className="mt-2 flex items-center gap-2 text-xs text-text-secondary">
                      <label htmlFor={`g-${c.key}`}>weight</label>
                      <input
                        id={`g-${c.key}`}
                        type="number"
                        min={0}
                        step={1}
                        value={c.grams}
                        onChange={(e) => updateComponent(c.key, { grams: Number(e.target.value) || 0 })}
                        className="w-20 rounded-md border border-border-default bg-bg-primary px-2 py-1 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-green-accent/50"
                      />
                      <span>g / unit</span>
                    </div>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={addComponent}
                className="mt-2.5 w-full rounded-lg border border-dashed border-border-default px-3 py-2 text-xs text-text-secondary hover:border-green-accent hover:text-green-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
              >
                ＋ Add component
              </button>
              <p className="text-meta text-text-muted mt-2.5">
                Product name, markets and annual units live in the bar at the top of the page.
              </p>
            </section>

            {/* Handled list — the punch list's state, managed here */}
            <section className="rounded-panel border border-border-default bg-bg-secondary p-4">
              <p className="text-meta uppercase tracking-wider text-text-muted mb-1">Handled obligations</p>
              <p className="text-xs text-text-secondary leading-relaxed mb-2.5">
                Everything you&rsquo;ve marked handled. Remove an entry and the obligation returns to
                the punch list. Match by entity name, bill number, or a market-scoped{' '}
                <code className="font-mono text-meta bg-bg-tertiary px-1 rounded">CA:SB-54</code>.
              </p>
              {acknowledged.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2.5">
                  {acknowledged.map((a) => (
                    <span
                      key={a}
                      className="inline-flex items-center gap-1.5 rounded-full border border-border-default bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary"
                    >
                      {a}
                      <button
                        type="button"
                        onClick={() => removeAck(a)}
                        className="text-text-muted hover:text-urgency-high leading-none"
                        aria-label={`Un-handle ${a}`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  addAck(ackDraft);
                }}
                className="flex gap-2"
              >
                <input
                  type="text"
                  value={ackDraft}
                  onChange={(e) => setAckDraft(e.target.value)}
                  placeholder="e.g. Circular Action Alliance"
                  className="flex-1 min-w-0 rounded-md border border-border-default bg-bg-primary px-2.5 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-green-accent/50"
                  aria-label="Mark an obligation handled"
                />
                <button
                  type="submit"
                  className="shrink-0 rounded-md border border-border-default bg-bg-tertiary px-3 py-1.5 text-xs text-text-secondary hover:border-green-accent hover:text-text-primary transition-colors"
                >
                  Add
                </button>
              </form>
            </section>

            {/* Saved packages — the account's, synced like the scope and watch list */}
            <SavedPackagesPanel
              signedIn={saved.signedIn}
              ready={saved.ready}
              packages={saved.packages}
              onLoad={loadSaved}
              onDelete={saved.remove}
              onSignIn={saved.openAuth}
            />

            {/* CI export — a Beta feature, gated on the /account opt-in (off for new users). */}
            {betaEnabled && (
            <section className="rounded-panel border border-border-default bg-bg-secondary p-4 space-y-3">
              <p className="flex items-center gap-2 text-meta uppercase tracking-wider text-text-muted">
                For your engineering team
                <span className="rounded-full border border-green-accent/40 px-1.5 py-px text-[0.6rem] tracking-wider text-green-accent">
                  Beta
                </span>
              </p>
              <p className="text-xs text-text-secondary leading-relaxed">
                Export this spec as{' '}
                <code className="font-mono text-meta bg-bg-tertiary px-1 rounded">packaging.yaml</code> — a
                robot check that re-runs on every code change and flags the build when a new law makes
                this spec non-compliant.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={downloadYaml}
                  className="rounded-md bg-green-accent px-3 py-1.5 text-xs font-medium text-bg-primary hover:opacity-90 transition-opacity"
                >
                  ↓ Download packaging.yaml
                </button>
                <button
                  type="button"
                  onClick={() => copy('link')}
                  className="rounded-md border border-border-default bg-bg-tertiary px-3 py-1.5 text-xs text-text-secondary hover:border-green-accent hover:text-text-primary transition-colors"
                >
                  {copied === 'link' ? 'Link copied ✓' : 'Copy studio link'}
                </button>
              </div>
              <div className="relative">
                <pre className="rounded-lg border border-border-default bg-bg-tertiary p-3 pr-16 text-[11px] leading-relaxed text-text-secondary overflow-x-auto font-mono">
                  {GITHUB_ACTIONS_SNIPPET}
                </pre>
                <button
                  type="button"
                  onClick={() => copy('snippet')}
                  className="absolute top-2 right-2 rounded-md border border-border-default bg-bg-secondary px-2 py-1 text-meta text-text-secondary hover:border-green-accent hover:text-text-primary transition-colors"
                >
                  {copied === 'snippet' ? 'Copied ✓' : 'Copy'}
                </button>
              </div>
              <p className="text-meta text-text-muted leading-relaxed">
                One step: <code className="font-mono">npx spec-sheet-guard --spec packaging.yaml --github</code> —
                findings appear as inline pull-request annotations.
              </p>
            </section>
            )}
          </div>

          {/* ---- RIGHT: the stage ---- */}
          <div className="space-y-4 min-w-0">
            {quote.components.length === 0 ? (
              <p className="text-text-muted italic text-sm">Add a component to price its EPR exposure.</p>
            ) : (
              <>
                {/* Redesign headroom — the fee/package and $/yr already live in the sticky bar and the
                    laws-to-act-on in the rollup below, so this panel keeps only what those don't show:
                    the best-format floor and how much redesign can save. */}
                <div className="rounded-panel border border-border-default bg-bg-secondary p-4">
                  <div className="flex flex-wrap gap-x-8 gap-y-3">
                    <Metric value={fmt.money(t.best_case_cents_per_package)} label="best-format floor" tone="good" />
                  </div>
                  {t.redesign_headroom_cents > 0.05 && (
                    <p className="mt-3 pt-3 border-t border-border-default text-sm text-text-secondary">
                      ↓ Redesigning each component to its best published format cuts the fee by{' '}
                      <b className="text-text-primary">
                        {fmt.money(t.redesign_headroom_cents)}/package (
                        {Math.round((100 * t.redesign_headroom_cents) / t.cents_per_package)}%)
                      </b>
                      {t.annual_fee_usd != null && t.annual_best_case_usd != null && (
                        <>
                          {' '}— <b className="text-text-primary">{fmt.amount(t.annual_fee_usd - t.annual_best_case_usd)}/yr</b>
                        </>
                      )}
                      . The cost curves below show every swap.
                    </p>
                  )}
                </div>

                {/* The punch list, compact */}
                <PunchList
                  report={guardReport}
                  loading={pathwaysLoading}
                  onMarkHandled={(f) => addAck(`${f.market}:${f.billNumber}`)}
                  onOpenBill={openBill}
                  openingBillId={openingBillId}
                />

                {/* live obligations rollup */}
                <div className="rounded-panel border border-border-default bg-bg-secondary p-4">
                  <div className="flex flex-wrap gap-x-8 gap-y-3">
                    <Metric small value={String(ob.action_law_count)} label="laws to act on" />
                    <Metric small value={String(ob.pros.length)} label={`PRO${ob.pros.length === 1 ? '' : 's'} to join`} />
                    <Metric small value={String(ob.monitor_count)} label="watch-only" muted />
                    <Metric small value={ob.nearest_deadline ?? '—'} label="nearest deadline" />
                  </div>
                  {ob.pros.length > 0 && (
                    <p className="mt-2.5 text-xs text-text-secondary">Register with: {ob.pros.join(' · ')}</p>
                  )}
                </div>

                {/* per-component cost curves */}
                {quote.components.map((c) => (
                  <ComponentCard
                    key={c.key}
                    c={c}
                    onSwap={(matId) => setMaterial(c.key, matId)}
                    onOpenBill={openBill}
                    openingBillId={openingBillId}
                  />
                ))}
              </>
            )}
          </div>
        </div>
      </section>

      {/* ================= Subscribe — keep watching this package's laws ================= */}
      <section
        aria-labelledby="watch-laws-heading"
        className="max-w-3xl mx-auto w-full rounded-panel border border-border-default bg-bg-secondary p-5"
      >
        <h2 id="watch-laws-heading" className="font-serif text-xl text-text-primary">
          Watch the laws shaping this package
        </h2>
        <p className="mt-1 mb-5 text-sm text-text-secondary leading-relaxed">
          Free email alerts when legislation touching the materials in this spec moves in the markets
          you picked — introduced, advancing, or hitting a deadline. Pre-scoped to this package below;
          adjust anything.
        </p>
        {booted && (
          <SubscribeForm prefill={{ usStates: markets, materials: subscribeMaterials }} />
        )}
      </section>

      {/* The honesty footer — trimmed to the fee basis + rates-source chip */}
      <ProvenanceFooter schedule={activeSchedule} scheduleReady={scheduleReady} isCa={scheduleId === 'ca'} />

      {/* The Bill Explorer's detail modal, reused verbatim */}
      <BillModal bill={detailBill} onClose={() => setDetailBill(null)} />
    </div>
    </FmtCtx.Provider>
  );
}

/** Fee-schedule picker — a compact button group over the supported jurisdictions, with a source
 *  link per schedule so every fee table we price against is one click from its published basis. */
function ScheduleSwitcher({
  active,
  onSwitch,
  sources,
}: {
  active: string;
  onSwitch: (id: string) => void;
  sources: { id: string; label: string; sourceUrl: string | null; provenance: string | null }[];
}) {
  const sourceById = new Map(sources.map((s) => [s.id, s]));
  return (
    <div className="space-y-1.5 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-meta uppercase tracking-wider text-text-muted">Fee schedule</span>
        {SCHEDULE_OPTIONS.map((o) => {
          const on = o.id === active;
          return (
            <button
              key={o.id}
              type="button"
              onClick={() => onSwitch(o.id)}
              aria-pressed={on}
              className={`rounded-full border px-3 py-1 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 ${
                on
                  ? 'border-green-accent bg-green-dark/40 text-text-primary font-medium'
                  : 'border-border-default bg-bg-tertiary text-text-secondary hover:border-green-accent/60'
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
      {/* Trust line — link out to each schedule's published fee table. */}
      <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-meta text-text-muted">
        <span>Sources:</span>
        {SCHEDULE_OPTIONS.map((o, i) => {
          const s = sourceById.get(o.id);
          return (
            <span key={o.id} className="inline-flex items-center">
              {i > 0 && <span aria-hidden className="mr-2 text-text-muted/50">·</span>}
              {s?.sourceUrl ? (
                <a
                  href={s.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={s.provenance ?? undefined}
                  className="text-green-accent hover:underline"
                >
                  {o.label} ↗
                </a>
              ) : (
                <span>{o.label}</span>
              )}
            </span>
          );
        })}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage chrome
// ---------------------------------------------------------------------------

const COACH_KEY = 'studio_coach_dismissed';

/** First-run walkthrough for the Build stage — a compact, dismissible three-step coach. Starts hidden
 *  to match SSR (no localStorage on the server), then reveals for anyone who hasn't dismissed it, so
 *  it never causes a hydration mismatch. */
function BuildCoach() {
  const [dismissed, setDismissed] = useState(true);
  useEffect(() => {
    setDismissed(localStorage.getItem(COACH_KEY) === '1');
  }, []);
  if (dismissed) return null;
  const close = () => {
    try { localStorage.setItem(COACH_KEY, '1'); } catch { /* private mode — just hide for the session */ }
    setDismissed(true);
    track('studio_coach_dismiss');
  };
  return (
    <div className="rounded-panel border border-green-accent/40 bg-green-dark/15 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">New here? Build a package in three moves.</p>
          <ol className="mt-2 space-y-1.5 text-xs text-text-secondary leading-relaxed">
            <li><b className="text-text-primary">1 ·</b> In the bar above, name your product and toggle the markets you sell into.</li>
            <li><b className="text-text-primary">2 ·</b> For each component chip, pick a material — every tile shows its fee and whether it&rsquo;s recyclable.</li>
            <li><b className="text-text-primary">3 ·</b> Read <b className="text-text-primary">The consequence</b> under each pick: what it costs against the best format in its family, and what it obligates.</li>
          </ol>
        </div>
        <button
          type="button"
          onClick={close}
          aria-label="Dismiss walkthrough"
          className="shrink-0 -mr-1 rounded p-1 text-lg leading-none text-text-muted hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

function ProgressTrack({ stage, onGo }: { stage: number; onGo: (n: number) => void }) {
  return (
    <nav aria-label="Studio sections" className="flex flex-wrap items-center gap-1 sm:gap-1.5">
      {STAGES.map((s, i) => {
        const current = i === stage;
        return (
          <span key={s.label} className="flex items-center gap-1 sm:gap-1.5">
            {i > 0 && (
              <span aria-hidden className="text-text-muted text-xs">
                →
              </span>
            )}
            <button
              type="button"
              onClick={() => onGo(i)}
              aria-current={current ? 'true' : undefined}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 ${
                current
                  ? 'border-green-accent bg-green-dark/40 text-text-primary font-medium'
                  : 'border-border-default bg-bg-tertiary text-text-secondary hover:border-green-accent/60'
              }`}
            >
              <span className={`font-mono ${i < stage ? 'text-green-accent' : ''}`} aria-hidden>
                {i < stage ? '✓' : i + 1}
              </span>
              {s.label}
            </button>
          </span>
        );
      })}
    </nav>
  );
}

/** The sticky spec bar — the whole brief, compact and editable in place, plus
 *  the running fee score. Pinned under the top nav for all three sections. */
function SpecBar({
  product,
  onProduct,
  markets,
  onToggleMarket,
  units,
  onUnits,
  quote,
  loading,
  onSave,
  saveState,
}: {
  product: string;
  onProduct: (v: string) => void;
  markets: string[];
  onToggleMarket: (code: string) => void;
  units: string;
  onUnits: (v: string) => void;
  quote: Quote;
  loading: boolean;
  onSave: () => void;
  saveState: SaveState;
}) {
  const fmt = useFmt();
  const t = quote.totals;
  return (
    <div className="sticky top-[3.25rem] sm:top-[5.5rem] z-30 rounded-lg border border-border-default bg-bg-secondary/95 backdrop-blur px-3.5 py-2.5 space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <label htmlFor="spec-product" className="sr-only">
          Product name
        </label>
        <input
          id="spec-product"
          type="text"
          value={product}
          onChange={(e) => onProduct(e.target.value)}
          placeholder="Name your product — e.g. 500ml Sparkling Water"
          className="flex-1 min-w-[11rem] rounded-md border border-border-default bg-bg-primary px-3 py-1.5 text-sm font-semibold text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-green-accent/50"
        />
        <label className="flex items-center gap-1.5 text-xs text-text-secondary" htmlFor="spec-units">
          <span className="hidden sm:inline">units/yr</span>
          <input
            id="spec-units"
            type="number"
            min={0}
            max={999999999}
            step={100000}
            value={units}
            onChange={(e) => onUnits(e.target.value)}
            placeholder="units/yr"
            title="Annual units sold (optional) — unlocks the $/yr cost estimate. Max ~1B."
            className="w-28 rounded-md border border-border-default bg-bg-primary px-2 py-1.5 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-green-accent/50"
          />
        </label>
        {loading && <span className="text-meta italic text-text-muted">refreshing…</span>}
        <span className="ml-auto font-mono text-sm text-text-primary">
          <b>{fmt.money(t.cents_per_package)}</b>
          <span className="text-text-muted font-normal">/pkg</span>
        </span>
        {t.annual_fee_usd != null ? (
          <span className="font-mono text-sm font-bold text-urgency-medium">
            {fmt.amount(t.annual_fee_usd)}
            <span className="font-normal text-text-muted">/yr</span>
          </span>
        ) : (
          <span className="text-meta text-text-muted italic hidden sm:inline">add units for $/yr</span>
        )}
        <button
          type="button"
          onClick={onSave}
          disabled={saveState === 'saving'}
          title="Save this package to your account — it syncs across devices. Sign in if you haven't."
          className="shrink-0 rounded-md border border-border-default bg-bg-tertiary px-2.5 py-1 text-xs text-text-secondary hover:border-green-accent hover:text-text-primary transition-colors disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
        >
          {saveState === 'saved' ? 'Saved ✓' : saveState === 'saving' ? 'Saving…' : 'Save'}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-meta uppercase tracking-wider text-text-muted mr-1">Sells into</span>
        {MARKETS.map((m) => {
          const on = markets.includes(m.code);
          return (
            <button
              key={m.code}
              type="button"
              title={m.label}
              onClick={() => onToggleMarket(m.code)}
              className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 ${
                on
                  ? 'border-green-accent bg-green-dark/40 text-text-primary font-medium'
                  : 'border-border-default bg-bg-tertiary text-text-secondary hover:border-green-accent/60'
              }`}
              aria-pressed={on}
            >
              {m.code}
            </button>
          );
        })}
        {markets.length === 0 && (
          <span className="text-meta italic text-urgency-medium">pick at least one market</span>
        )}
      </div>
    </div>
  );
}

function ProvenanceFooter({
  schedule,
  scheduleReady,
  isCa,
}: {
  schedule: FeeSchedule;
  scheduleReady: boolean;
  isCa: boolean;
}) {
  return (
    <footer className="border-t border-border-default pt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-meta text-text-muted">
      <span>
        Fee basis:{' '}
        <a
          href={schedule.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-green-accent hover:underline"
        >
          {schedule.engine.provenance}
        </a>{' '}
        ({schedule.engine.program}, {schedule.engine.currency})
      </span>
      {/* The live/bundled status only describes the CA API fetch; other jurisdictions
          are bundled reference tables. */}
      {!isCa ? (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border-default bg-bg-tertiary px-2 py-0.5">
          bundled reference table
        </span>
      ) : scheduleReady ? (
        schedule.source === 'live' ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-risk-low/50 bg-risk-low/10 px-2 py-0.5 text-risk-low">
            ● live fee schedule
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-urgency-medium/50 bg-urgency-medium/10 px-2 py-0.5 text-urgency-medium">
            ⚠ bundled draft rates — live fee schedule unavailable
          </span>
        )
      ) : (
        <span className="italic">checking live fee schedule…</span>
      )}
    </footer>
  );
}

// ---------------------------------------------------------------------------
// Shared law-row bits — a bill link that opens the explorer's modal + the star
// ---------------------------------------------------------------------------

function BillLink({
  billId,
  billNumber,
  market,
  onOpen,
  openingBillId,
}: {
  billId: number;
  billNumber: string;
  market: string;
  onOpen: (billId: number) => void;
  openingBillId: number | null;
}) {
  const busy = openingBillId === billId;
  return (
    <button
      type="button"
      onClick={() => onOpen(billId)}
      disabled={busy}
      title={`Open ${market} ${billNumber || `bill #${billId}`}`}
      className="font-mono font-bold text-green-accent hover:underline disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 rounded"
    >
      {busy ? 'opening…' : billNumber || `bill #${billId}`}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Build-section pieces — the material picker and the consequence reveal
// ---------------------------------------------------------------------------

function MaterialPicker({
  families,
  schedule,
  currentId,
  onPick,
}: {
  families: PaletteFamily[];
  schedule: FeeSchedule;
  currentId: string;
  onPick: (materialId: string) => void;
}) {
  const fmt = useFmt();
  return (
    <div className="space-y-4">
      {families.map((fam, famIdx) => (
        <div key={fam.category} className={famIdx > 0 ? 'pt-3 border-t border-border-default' : ''}>
          <p className="text-xs font-semibold text-text-secondary mb-1.5">{fam.label}</p>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {fam.options.map((m) => {
              const rate = ratePerTonne(schedule, m.category, m.cents);
              const pkg = Math.round(centsPerPackage(rate, m.default_g) * 100) / 100;
              const on = m.id === currentId;
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => onPick(m.id)}
                  aria-pressed={on}
                  className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 ${
                    on
                      ? 'border-green-accent bg-green-dark/40'
                      : 'border-border-default bg-bg-tertiary hover:border-green-accent/60'
                  }`}
                >
                  <span className="block leading-tight">
                    <span className={on ? 'font-semibold text-text-primary' : 'text-text-secondary'}>{m.label}</span>
                  </span>
                  <span className="mt-0.5 flex items-center gap-1.5 text-meta text-text-muted">
                    <span className={m.recyclable ? 'text-risk-low' : 'text-urgency-medium'}>
                      {m.recyclable ? '♻ recyclable' : '⚠ hard to recycle'}
                    </span>
                    <span aria-hidden>·</span>
                    {m.tag} · {fmt.rate(rate)} · {fmt.money(pkg)}/pkg at {m.default_g}g
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Schedule-driven design-attribute controls — only rendered for schedules that
 *  actually modulate on attributes (UK RAM grade today; none for CA/JP). Changing a
 *  value reprices the component live via the active schedule's modulation rules. */
function AttributeControls({
  inputs,
  attrs,
  onChange,
}: {
  inputs: AttributeInput[];
  attrs: PackageAttributes | undefined;
  onChange: (patch: PackageAttributes) => void;
}) {
  if (!inputs.length) return null;
  return (
    <div className="pt-3 border-t border-border-default space-y-2">
      <p className="text-xs font-semibold text-text-secondary">
        Design attributes <span className="font-normal text-text-muted">— these modulate the fee</span>
      </p>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {inputs.map((input) => (
          <AttributeField key={input.attr} input={input} attrs={attrs} onChange={onChange} />
        ))}
      </div>
    </div>
  );
}

function AttributeField({
  input,
  attrs,
  onChange,
}: {
  input: AttributeInput;
  attrs: PackageAttributes | undefined;
  onChange: (patch: PackageAttributes) => void;
}) {
  const id = `attr-${input.attr}`;
  const fieldCls =
    'w-full rounded-md border border-border-default bg-bg-primary px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-green-accent/50';

  if (input.kind === 'toggle') {
    return (
      <label htmlFor={id} className="flex items-center gap-2 text-xs text-text-secondary" title={input.help}>
        <input
          id={id}
          type="checkbox"
          checked={Boolean(attrs?.[input.attr])}
          onChange={(e) => onChange({ [input.attr]: e.target.checked } as PackageAttributes)}
          className="accent-green-accent"
        />
        {input.label}
      </label>
    );
  }

  if (input.kind === 'number') {
    return (
      <label htmlFor={id} className="block text-xs text-text-secondary" title={input.help}>
        <span className="block mb-1">{input.label}</span>
        <span className="flex items-center gap-1.5">
          <input
            id={id}
            type="number"
            min={0}
            max={100}
            value={attrs?.pcrPercent ?? ''}
            onChange={(e) => onChange({ [input.attr]: Number(e.target.value) || 0 } as PackageAttributes)}
            className={`${fieldCls} w-24`}
          />
          {input.suffix && <span className="text-text-muted">{input.suffix}</span>}
        </span>
      </label>
    );
  }

  // select
  const cur = (attrs?.[input.attr] as string | undefined) ?? input.options?.[0]?.value ?? '';
  return (
    <label htmlFor={id} className="block text-xs text-text-secondary" title={input.help}>
      <span className="block mb-1">{input.label}</span>
      <select
        id={id}
        value={cur}
        onChange={(e) => onChange({ [input.attr]: e.target.value } as PackageAttributes)}
        className={fieldCls}
      >
        {input.options?.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** The moment the redesign exists for: pick a material, see what it costs you
 *  against the best format in its family — and what it obligates you to do. */
function ConsequenceReveal({
  qc,
  unitsPerYear,
  markets,
  programName,
  onOpenBill,
  openingBillId,
}: {
  qc: QuoteComponent;
  unitsPerYear: number | null;
  markets: string[];
  programName: string;
  onOpenBill: (billId: number) => void;
  openingBillId: number | null;
}) {
  const fmt = useFmt();
  const con = familyConsequence(qc, unitsPerYear);
  const fam = qc.category_label.toLowerCase();
  const bestShort = con.best ? con.best.label.split(' — ')[0] : null;

  return (
    <div className="studio-consequence-in rounded-panel border border-border-default bg-bg-secondary p-4 space-y-3">
      <div>
        <p className="text-meta uppercase tracking-wider text-text-muted mb-1">
          The consequence · {qc.name}
        </p>
        {con.is_best_in_family ? (
          <>
            <p className="font-mono text-3xl font-bold text-risk-low">✓ best in family</p>
            <p className="mt-1 text-sm text-text-secondary leading-relaxed">
              {qc.material_label} is the cheapest published {fam} format — nothing left on the table
              vs best-in-family.
            </p>
          </>
        ) : (
          <>
            <p className="font-mono text-3xl font-bold text-urgency-high">
              ▲ +
              {con.delta_annual_usd != null
                ? `${fmt.compact(con.delta_annual_usd)}/yr`
                : `${fmt.money(con.delta_cents_per_package)}/pkg`}
              {bestShort && (
                <span className="ml-2 align-middle font-sans text-sm font-normal text-text-secondary">
                  vs {bestShort}
                </span>
              )}
            </p>
            <p className="mt-1 text-sm text-text-secondary leading-relaxed">
              Money left on the table vs best-in-family
              {con.best && (
                <>
                  : the cheapest {fam} format is <b className="text-text-primary">{con.best.label}</b> at{' '}
                  {fmt.rate(con.best.rate_per_tonne)}
                </>
              )}
              .{con.delta_annual_usd != null && unitsPerYear != null && (
                <span className="text-text-muted"> At {unitsPerYear.toLocaleString()} units/yr.</span>
              )}
              {con.delta_annual_usd == null && ' Set annual units in the bar above to see this as $/yr.'}
            </p>
          </>
        )}
      </div>

      {/* why: the fee-tier logic, in plain words */}
      <p className="border-t border-border-default pt-3 text-xs text-text-secondary leading-relaxed">
        <b className="text-text-primary">Why this costs more:</b> {programName} charges different fees
        for different {fam} formats — from {fmt.rate(qc.best_per_tonne)} (easiest to recycle) up to{' '}
        {fmt.rate(qc.worst_per_tonne)} (hardest). This pick lands at {fmt.rate(qc.rate_per_tonne)}.
        {qc.headroom_to_best_per_tonne > 0 ? (
          <>
            {' '}Switching to the best format in this family would save{' '}
            <b className="text-text-primary">{fmt.rate(qc.headroom_to_best_per_tonne)}</b> per tonne —
            that&rsquo;s your redesign headroom.
          </>
        ) : (
          <> You&rsquo;re already at the lowest fee in this family.</>
        )}
      </p>

      {/* what it obligates */}
      <div className="border-t border-border-default pt-3">
        <p className="text-meta uppercase tracking-wider text-text-muted mb-1.5">
          What {fam} obligates in {markets.length ? markets.join(' · ') : 'your markets'}
        </p>
        {qc.obligations.length > 0 ? (
          <div className="space-y-1">
            {qc.obligations.slice(0, 4).map((o, i) => {
              const dd = daysTo(o.next_deadline_date);
              const over = dd !== null && dd < 0;
              return (
                <div
                  key={`${o.market}-${o.bill_number}-${i}`}
                  className="flex items-baseline gap-2 text-xs text-text-secondary"
                >
                  <span className="w-8 shrink-0 font-mono text-meta text-green-accent">{o.market}</span>
                  <span className="min-w-0">
                    <BillLink
                      billId={o.bill_id}
                      billNumber={o.bill_number}
                      market={o.market}
                      onOpen={onOpenBill}
                      openingBillId={openingBillId}
                    />
                    {' — '}
                    {o.action_summary || o.bill_title}
                    {o.entity && <span className="text-text-muted"> · {o.entity}</span>}
                  </span>
                  <WatchStar billId={o.bill_id} className="shrink-0 self-center -my-1" />
                  <span
                    className={`shrink-0 whitespace-nowrap font-mono text-meta ${
                      over ? 'text-urgency-high' : 'text-urgency-medium'
                    }`}
                  >
                    {o.next_deadline_date ? (over ? `overdue ${-dd!}d` : `${dd}d`) : 'no fixed date'}
                  </span>
                </div>
              );
            })}
            {qc.obligations.length > 4 && (
              <p className="text-meta italic text-text-muted">
                + {qc.obligations.length - 4} more law
                {qc.obligations.length - 4 === 1 ? '' : 's'} to act on — full list in the studio
              </p>
            )}
          </div>
        ) : (
          <p className="text-xs italic text-text-muted">
            Nothing to act on for {fam} in the selected markets.
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Presentational bits
// ---------------------------------------------------------------------------

function Metric({
  value,
  label,
  tone,
  small,
  muted,
}: {
  value: string;
  label: string;
  tone?: 'good' | 'mid' | 'bad';
  small?: boolean;
  muted?: boolean;
}) {
  const toneClass =
    tone === 'good' ? 'text-risk-low' : tone === 'bad' ? 'text-urgency-high' : tone === 'mid' ? 'text-urgency-medium' : muted ? 'text-text-muted' : 'text-text-primary';
  return (
    <div>
      <div className={`font-mono font-bold ${small ? 'text-xl' : 'text-2xl'} ${toneClass}`}>{value}</div>
      <div className="text-meta uppercase tracking-wider text-text-muted">{label}</div>
    </div>
  );
}

/** Plain-words action sentence for an unmet obligation — zero engineering jargon. */
function actionSentence(f: Finding): string {
  const entity = f.entityName;
  switch ((f.actionType || '').toLowerCase()) {
    case 'join_pro':
      return `Join ${entity ?? 'the producer responsibility organization'} and report your packaging`;
    case 'register_with_state':
      return entity ? `Register with ${entity}` : 'Register with the state program';
    case 'report_to_program':
    case 'report':
      return `Report your packaging data${entity ? ` to ${entity}` : ''}`;
    case 'file_individual_plan':
      return 'File an individual compliance plan with the state';
    case 'arrange_collection':
      return 'Arrange collection / take-back for this packaging';
    case 'pay_fee':
      return `Pay the program fee${entity ? ` to ${entity}` : ''}`;
    default:
      return f.actionSummary || f.billTitle || 'Meet this law’s requirements';
  }
}

/**
 * The punch list — the guard verdict in plain words. Same evaluate() output,
 * same acknowledged-list mechanics; only the presentation changed:
 * error/warning → "to handle", acknowledged → "handled", note → "watch-only".
 */
function PunchList({
  report,
  loading,
  onMarkHandled,
  onOpenBill,
  openingBillId,
  onFixInBuild,
  defaultOpen = false,
}: {
  report: ReturnType<typeof evaluate>;
  loading: boolean;
  onMarkHandled: (f: Finding) => void;
  onOpenBill: (billId: number) => void;
  openingBillId: number | null;
  onFixInBuild?: () => void;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const { findings } = report;

  const toHandle = findings.filter((f) => f.severity !== 'note');
  const handled = findings.filter((f) => f.acknowledged);
  const watchOnly = findings.filter((f) => f.severity === 'note' && !f.acknowledged);
  const allClear = toHandle.length === 0;

  const shownToHandle = open ? toHandle : toHandle.slice(0, 4);
  const hiddenBeyondPreview = findings.length - shownToHandle.length;

  return (
    <div
      className={`rounded-panel border bg-bg-secondary p-4 ${
        allClear ? 'border-risk-low/50' : 'border-urgency-high/50'
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            allClear ? 'bg-risk-low/15 text-risk-low' : 'bg-urgency-high/15 text-urgency-high'
          }`}
        >
          {allClear ? '✓ Nothing left to handle' : `${toHandle.length} to handle`}
        </span>
        <span className="text-xs text-text-secondary">
          <b className={toHandle.length ? 'text-urgency-high' : 'text-text-muted'}>
            {toHandle.length} to handle
          </b>
          {' · '}
          <b className={handled.length ? 'text-risk-low' : 'text-text-muted'}>{handled.length} handled</b>
          {' · '}
          <b className="text-text-muted">{watchOnly.length} watch-only</b>
        </span>
        {loading && <span className="text-meta italic text-text-muted">refreshing…</span>}
        {findings.length > shownToHandle.length && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="ml-auto text-xs text-green-accent hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 rounded"
          >
            {open ? 'Collapse' : `Show everything (${findings.length})`}
          </button>
        )}
      </div>
      <p className="text-meta text-text-muted mt-1.5">
        Already joined or registered? Mark it handled and it drops off the list — it comes back if the
        law changes.
      </p>

      {/* To handle — one action sentence per unmet obligation */}
      {shownToHandle.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {shownToHandle.map((f, i) => {
            const dd = f.daysToDeadline;
            return (
              <li
                key={`${f.market}-${f.billNumber}-${i}`}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-lg border border-border-default bg-bg-tertiary px-3 py-2"
              >
                <span className="min-w-[min(14rem,100%)] flex-1 text-xs sm:text-sm text-text-secondary leading-relaxed">
                  <b className="text-text-primary">{actionSentence(f)}</b>
                  {f.deadline ? (
                    <>
                      {' — due '}
                      <b className={dd !== null && dd < 0 ? 'text-urgency-high' : 'text-text-primary'}>
                        {formatDate(f.deadline)}
                      </b>
                      {dd !== null && (
                        <span className={`text-meta ${dd < 0 ? 'text-urgency-high' : 'text-text-muted'}`}>
                          {' '}
                          ({dd < 0 ? `overdue ${-dd} days` : `in ${dd} days`})
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="text-text-muted"> — no fixed date yet</span>
                  )}{' '}
                  (
                  <BillLink
                    billId={f.billId}
                    billNumber={`${f.market} ${f.billNumber}`.trim()}
                    market={f.market}
                    onOpen={onOpenBill}
                    openingBillId={openingBillId}
                  />
                  )
                </span>
                <span className="flex items-center gap-1.5 shrink-0 ml-auto">
                  <WatchStar billId={f.billId} />
                  {onFixInBuild && (
                    <button
                      type="button"
                      onClick={onFixInBuild}
                      className="rounded-md border border-border-default px-2 py-0.5 text-meta text-text-muted hover:border-green-accent hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
                      title="Go back to Build to change this component's material"
                    >
                      ↑ Fix in Build
                    </button>
                  )}
                  {f.registrationUrl && (
                    <a
                      href={f.registrationUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded-md border border-border-default px-2 py-0.5 text-meta text-text-secondary hover:border-green-accent hover:text-text-primary transition-colors"
                    >
                      Registration →
                    </a>
                  )}
                  <button
                    type="button"
                    onClick={() => onMarkHandled(f)}
                    className="rounded-md border border-border-default px-2 py-0.5 text-meta text-text-secondary hover:border-green-accent hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
                    title="Already joined or registered? Mark it handled."
                  >
                    Mark handled ✓
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {allClear && !loading && findings.length === 0 && (
        <p className="mt-3 text-xs italic text-text-muted">
          No obligations found for these materials in the selected markets.
        </p>
      )}

      {open && (
        <>
          {/* Handled — kept visible so "done" stays legible */}
          {handled.length > 0 && (
            <div className="mt-4">
              <p className="text-meta uppercase tracking-wider text-text-muted mb-1.5">Handled</p>
              <ul className="space-y-1">
                {handled.map((f, i) => (
                  <li
                    key={`${f.market}-${f.billNumber}-h${i}`}
                    className="flex items-baseline gap-2 text-xs text-text-muted"
                  >
                    <span className="text-risk-low" aria-hidden>
                      ✓
                    </span>
                    <span className="min-w-0">
                      {actionSentence(f)} (
                      <BillLink
                        billId={f.billId}
                        billNumber={`${f.market} ${f.billNumber}`.trim()}
                        market={f.market}
                        onOpen={onOpenBill}
                        openingBillId={openingBillId}
                      />
                      ) — handled. Un-handle it from the Studio&rsquo;s list.
                    </span>
                    <WatchStar billId={f.billId} className="shrink-0 self-center -my-1" />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Watch-only — nothing to file today */}
          {watchOnly.length > 0 && (
            <div className="mt-4">
              <p className="text-meta uppercase tracking-wider text-text-muted mb-1.5">
                Watch-only — nothing to file today
              </p>
              <ul className="space-y-1">
                {watchOnly.map((f, i) => (
                  <li
                    key={`${f.market}-${f.billNumber}-w${i}`}
                    className="flex items-baseline gap-2 text-xs text-text-secondary"
                  >
                    <span className="w-8 shrink-0 font-mono text-meta text-green-accent">{f.market}</span>
                    <span className="min-w-0">
                      <BillLink
                        billId={f.billId}
                        billNumber={f.billNumber}
                        market={f.market}
                        onOpen={onOpenBill}
                        openingBillId={openingBillId}
                      />
                      {' — '}
                      {f.actionSummary || f.billTitle}
                    </span>
                    <WatchStar billId={f.billId} className="shrink-0 self-center -my-1" />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {!open && hiddenBeyondPreview > 0 && (
        <p className="mt-2 text-meta text-text-muted italic">
          + {hiddenBeyondPreview} more item{hiddenBeyondPreview === 1 ? '' : 's'} (handled and
          watch-only included)
        </p>
      )}
    </div>
  );
}

function ComponentCard({
  c,
  onSwap,
  onOpenBill,
  openingBillId,
}: {
  c: QuoteComponent;
  onSwap: (materialId: string) => void;
  onOpenBill: (billId: number) => void;
  openingBillId: number | null;
}) {
  const fmt = useFmt();
  const rates = c.cost_curve.map((x) => x.rate_per_tonne);
  const max = Math.max(...rates, 1);
  const min = rates[0] ?? 0;
  const span = (rates[rates.length - 1] ?? 0) - min || 1;

  return (
    <div className="rounded-panel border border-border-default bg-bg-secondary p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-serif text-base text-text-primary">
          {c.name}{' '}
          <span className="align-middle text-meta rounded-full border border-border-default bg-bg-tertiary px-2 py-0.5 text-text-muted font-sans">
            {c.category_label}
          </span>
        </h3>
        <span className="font-mono text-xs text-text-secondary">
          {c.grams} g · {fmt.rate(c.rate_per_tonne)} · {fmt.money(c.cents_per_package)}/pkg
        </span>
      </div>
      <p className="text-meta text-text-muted mt-0.5 mb-3">
        Currently: {c.material_label}
        {!c.recyclable && ' · ⚠ hard to recycle'}
        {c.obligation_count > 0 && ` · ${c.obligation_count} law${c.obligation_count === 1 ? '' : 's'} to act on`}
        {c.monitor_count > 0 && ` · ${c.monitor_count} watch-only`}
      </p>

      {/* the cost curve — click a bar to swap */}
      <div className="space-y-0.5">
        {c.cost_curve.map((alt) => {
          const widthPct = (alt.rate_per_tonne / max) * 100;
          const rank = (alt.rate_per_tonne - min) / span;
          const dl = alt.delta_per_tonne;
          const dtxt = alt.is_current ? 'current' : dl === 0 ? '=' : dl < 0 ? `−${fmt.rate(-dl).slice(1)}` : `+${fmt.rate(dl).slice(1)}`;
          return (
            <button
              key={alt.material_id}
              type="button"
              onClick={() => onSwap(alt.material_id)}
              className={`grid w-full grid-cols-[minmax(0,7.5rem)_1fr_4.75rem] items-center gap-2.5 rounded-md px-1 py-0.5 text-left transition-colors sm:grid-cols-[190px_1fr_96px] ${
                alt.is_current ? 'bg-green-dark/40' : 'hover:bg-bg-tertiary'
              }`}
              title={alt.is_current ? 'Current material' : `Swap to ${alt.label}`}
            >
              <span className="min-w-0 truncate text-xs leading-tight">
                <span className={alt.is_current ? 'font-semibold text-text-primary' : 'text-text-secondary'}>
                  {alt.label}
                </span>
                <br />
                <span className="text-meta text-text-muted">
                  <span
                    className={alt.recyclable ? 'text-risk-low' : 'text-urgency-medium'}
                    title={alt.recyclable ? 'Recyclable' : 'Hard to recycle'}
                  >
                    {alt.recyclable ? '♻' : '⚠'}
                  </span>
                  {' '}{alt.category_label} · {alt.tag}
                </span>
              </span>
              <span className="relative block h-4 overflow-hidden rounded bg-bg-tertiary">
                <span
                  className="absolute inset-y-0 left-0 rounded"
                  style={{ width: `${widthPct}%`, background: rateColor(rank) }}
                />
              </span>
              <span className={`text-right font-mono text-xs leading-tight ${alt.is_current ? 'text-text-primary' : 'text-text-secondary'}`}>
                {fmt.rate(alt.rate_per_tonne)}
                <br />
                <span
                  className="text-meta"
                  style={{ color: dl < 0 ? '#22c55e' : dl > 0 ? '#ef4444' : undefined }}
                >
                  {dtxt}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {/* fee-gap footer in plain words */}
      <p className="mt-3 border-t border-border-default pt-3 text-xs text-text-secondary">
        Fee gap between the best and worst {c.category_label.toLowerCase()} format:{' '}
        {fmt.rate(c.best_per_tonne)} (easiest to recycle) ↔ {fmt.rate(c.worst_per_tonne)} (hardest) —{' '}
        <b className="text-text-primary">{fmt.rate(c.eco_mod_swing_per_tonne)} of redesign headroom</b>
        {c.headroom_to_best_per_tonne > 0 && (
          <>
            , {fmt.rate(c.headroom_to_best_per_tonne)} of it above your current format
          </>
        )}
        .
        {c.cheapest_same_family && (
          <>
            {' '}Cheapest swap in this family: <b className="text-text-primary">{c.cheapest_same_family.label}</b> —{' '}
            {fmt.rate(c.cheapest_same_family.rate_per_tonne)} vs {fmt.rate(c.rate_per_tonne)}
            {c.cents_per_package - c.cheapest_same_family.cents_per_package > 0.01 && (
              <>
                , saving{' '}
                <b className="text-risk-low">
                  {fmt.money(c.cents_per_package - c.cheapest_same_family.cents_per_package)}/package
                </b>
              </>
            )}
            . Click any bar above to swap.
          </>
        )}
      </p>

      {/* obligations this component triggers */}
      {c.obligations.length > 0 ? (
        <div className="mt-2.5 space-y-1">
          {c.obligations.slice(0, 5).map((o, i) => {
            const dd = daysTo(o.next_deadline_date);
            const over = dd !== null && dd < 0;
            return (
              <div key={`${o.market}-${o.bill_number}-${i}`} className="flex items-baseline gap-2 text-xs text-text-secondary">
                <span className="w-8 shrink-0 font-mono text-meta text-green-accent">{o.market}</span>
                <span className="min-w-0">
                  <BillLink
                    billId={o.bill_id}
                    billNumber={o.bill_number}
                    market={o.market}
                    onOpen={onOpenBill}
                    openingBillId={openingBillId}
                  />
                  {' — '}
                  {o.action_summary || o.bill_title}
                  {o.entity && <span className="text-text-muted"> · {o.entity}</span>}
                </span>
                <WatchStar billId={o.bill_id} className="shrink-0 self-center -my-1" />
                <span className={`shrink-0 whitespace-nowrap font-mono text-meta ${over ? 'text-urgency-high' : 'text-urgency-medium'}`}>
                  {o.next_deadline_date ? (over ? `overdue ${-dd!}d` : `${dd}d`) : 'no fixed date'}
                </span>
              </div>
            );
          })}
          {c.obligations.length > 5 && (
            <p className="text-meta italic text-text-muted">
              + {c.obligations.length - 5} more law{c.obligations.length - 5 === 1 ? '' : 's'} to act on
            </p>
          )}
        </div>
      ) : (
        <p className="mt-2.5 text-meta italic text-text-muted">
          Nothing to act on for {c.category_label.toLowerCase()} in the selected markets.
        </p>
      )}
    </div>
  );
}
