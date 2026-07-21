'use client';
/**
 * Packaging Studio — one workbench, not a three-act walkthrough.
 *
 *   LEFT  · The package. Each component drawn as the form it actually is (bottle,
 *           pouch, carton, can …), editable in place: name, material, weight, and a
 *           form picker. The drawing is the representation the old studio never had.
 *   RIGHT · What it costs, and what you owe. One headline number, the single cheapest
 *           honest swap (not a rainbow of every format), and the compliance punch list.
 *
 * The quote + guard engine (lib/studio.ts + lib/guard.ts) is untouched — it was never
 * the problem. All spec state is kept in sync with the URL hash so any package is a
 * shareable link; law rows open the Bill Explorer's detail modal.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { BillModal } from '@/components/ui/BillModal';
import { WatchStar } from '@/components/watchlist/WatchStar';
import { SubscribeForm } from '@/components/about/SubscribeForm';
import { GuidesTabs } from '@/components/guides/GuidesTabs';
import { PackageGlyph, PACKAGE_FORMS, formForCategory } from '@/components/studio/PackageForm';
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
  decodeSpecFromHash,
  encodeSpecToHash,
  feeScheduleFromSchedule,
  fetchFeeSchedule,
  fetchPathwaysForMarkets,
  groupPaletteByFamily,
  makeFmt,
  pruneAttrs,
  remapComponentsToSchedule,
  specToYaml,
  type CurvePoint,
  type FeeSchedule,
  type Fmt,
  type PaletteFamily,
  type Quote,
  type QuoteComponent,
  type SpecComponent,
  type StudioSpec,
} from '@/lib/studio';
import { getSchedule, type AttributeInput, type PackageAttributes } from '@/lib/feeSchedule';
import { evaluate, type Finding } from '@/lib/guard';
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

const DEFAULT_COMPONENTS: SpecComponent[] = [
  { key: 'c0', name: 'Bottle', material: 'pet_clear', grams: 22, form: 'bottle' },
  { key: 'c1', name: 'Cap', material: 'pp_ps', grams: 3, form: 'cap' },
  { key: 'c2', name: 'Label', material: 'paperboard', grams: 2, form: 'film' },
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

/** Studio material family → the subscription flow's material_category slug. */
const SUBSCRIBE_MATERIAL: Record<string, string> = {
  plastic_packaging: 'plastic_packaging',
  plastic_film: 'plastic_packaging',
  paper_packaging: 'paper_packaging',
  glass_packaging: 'glass',
  aluminum_packaging: 'metals',
};

const PRIMARY_BTN =
  'inline-flex items-center justify-center gap-2 rounded-lg bg-green-accent text-bg-primary px-4 py-2 font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60';

const LBL = 'text-meta uppercase tracking-wider text-text-muted';

export default function PackagingStudioPage() {
  // ---- the spec ----
  const [product, setProduct] = useState('Untitled package');
  const [components, setComponents] = useState<SpecComponent[]>(DEFAULT_COMPONENTS);
  const [markets, setMarkets] = useState<string[]>(DEFAULT_MARKETS);
  const [units, setUnits] = useState('');
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [ackDraft, setAckDraft] = useState('');
  const uid = useRef(DEFAULT_COMPONENTS.length);
  const hydrated = useRef(false);
  const [booted, setBooted] = useState(false);

  // ---- data layers ----
  const [schedule, setSchedule] = useState<FeeSchedule>(FALLBACK_SCHEDULE); // the CA fetch
  const [scheduleId, setScheduleId] = useState<string>('ca');
  const [scheduleReady, setScheduleReady] = useState(false);
  const [pathways, setPathways] = useState<Record<string, Awaited<ReturnType<typeof fetchPathwaysForMarkets>>[string]>>({});
  const [pathwaysLoading, setPathwaysLoading] = useState(false);
  const [copied, setCopied] = useState<'snippet' | 'link' | null>(null);

  // ---- bill detail modal (the Bill Explorer's, reused) ----
  const [detailBill, setDetailBill] = useState<BillSummary | null>(null);
  const [openingBillId, setOpeningBillId] = useState<number | null>(null);

  const { isUsView } = useRegion();
  const { showToast, isPro, isAdmin, user, openAuth } = useAuth();
  const { betaEnabled } = useBeta();
  const saved = useSavedPackages();
  const hadHashSpec = useRef(false);
  const autoLoaded = useRef(false);

  // Restore a shared/returning spec from the URL hash.
  useEffect(() => {
    const fromHash = decodeSpecFromHash(window.location.hash);
    if (fromHash) {
      hadHashSpec.current = true;
      if (fromHash.product) setProduct(fromHash.product);
      if (fromHash.scheduleId) setScheduleId(fromHash.scheduleId); // before components, so materials resolve
      if (fromHash.components.length) {
        setComponents(fromHash.components);
        uid.current = fromHash.components.length;
      }
      setMarkets(fromHash.markets);
      if (fromHash.unitsPerYear) setUnits(String(fromHash.unitsPerYear));
      if (fromHash.acknowledged?.length) setAcknowledged(fromHash.acknowledged);
    }
    hydrated.current = true;
    setBooted(true);
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
  // registered engine Schedule adapted to the studio's UI shape.
  const activeSchedule: FeeSchedule = useMemo(() => {
    if (scheduleId === 'ca') return schedule;
    const reg = getSchedule(scheduleId);
    return reg ? feeScheduleFromSchedule(reg) : schedule;
  }, [scheduleId, schedule]);

  const fmt = useMemo(() => makeFmt(activeSchedule.engine.currency), [activeSchedule]);

  const quote: Quote = useMemo(
    () => buildQuote(spec, pathways, activeSchedule),
    [spec, pathways, activeSchedule],
  );

  const specMaterials = useMemo(
    () => [...new Set(quote.components.map((c) => c.category))],
    [quote],
  );

  const guardReport = useMemo(
    () => evaluate({ product, markets, materials: specMaterials, acknowledged }, pathways),
    [product, markets, specMaterials, acknowledged, pathways],
  );

  const families = useMemo(() => groupPaletteByFamily(activeSchedule.palette), [activeSchedule]);

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

  const switchSchedule = useCallback(
    (id: string) => {
      if (id === scheduleId) return;
      const target = id === 'ca' ? schedule : (() => {
        const reg = getSchedule(id);
        return reg ? feeScheduleFromSchedule(reg) : schedule;
      })();
      setComponents((cs) => remapComponentsToSchedule(cs, activeSchedule.palette, target.palette));
      setScheduleId(id);
      track('studio_schedule_switch', { schedule: id });
    },
    [scheduleId, schedule, activeSchedule],
  );

  const subscribeMaterials = useMemo(
    () => [...new Set(specMaterials.map((c) => SUBSCRIBE_MATERIAL[c] ?? 'plastic_packaging'))],
    [specMaterials],
  );

  const paletteById = useMemo(() => new Map(activeSchedule.palette.map((m) => [m.id, m])), [activeSchedule]);

  // ---- bench handlers ----
  const addComponent = () => {
    const mat = paletteById.get('glass') ?? activeSchedule.palette[0];
    setComponents((cs) => [
      ...cs,
      { key: `c${uid.current++}`, name: 'New component', material: mat.id, grams: mat.default_g },
    ]);
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

  const setForm = (key: string, form: string) => updateComponent(key, { form });

  const toggleMarket = (code: string) =>
    setMarkets((ms) => (ms.includes(code) ? ms.filter((m) => m !== code) : [...ms, code]));

  // Load a saved package back into the studio — same restore path as a share-link hash.
  const loadSaved = useCallback(
    (pkg: SavedPackage, opts?: { auto?: boolean }) => {
      const s = decodeSpecFromHash(pkg.hash);
      if (!s) return;
      setProduct(s.product || 'Untitled package');
      setScheduleId(s.scheduleId || 'ca');
      if (s.components.length) {
        setComponents(s.components);
        uid.current = s.components.length;
      }
      setMarkets(s.markets);
      setUnits(s.unitsPerYear ? String(s.unitsPerYear) : '');
      setAcknowledged(s.acknowledged ?? []);
      if (opts?.auto) showToast(`Picked up where you left off — loaded “${pkg.name}”.`);
      track('studio_package_load', { auto: Boolean(opts?.auto) });
    },
    [showToast],
  );

  // Returning signed-in user, no spec in the URL: reopen their most recently saved package.
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

  // ---- export for the engineering team (demoted to a disclosure) ----
  const yaml = useMemo(
    () => specToYaml({ product, markets, materials: specMaterials, acknowledged }),
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

  const t = quote.totals;
  const totalGrams = components.reduce((s, c) => s + (Number(c.grams) || 0), 0);
  const hasUnits = t.annual_fee_usd != null;

  // The single cheapest honest swap across the whole package — the biggest same-family saving.
  const bestSwap = useMemo(() => {
    let top: { key: string; name: string; to: CurvePoint; savePkg: number } | null = null;
    for (const c of quote.components) {
      const cheaper = c.cheapest_same_family;
      if (!cheaper) continue;
      const savePkg = Math.round((c.cents_per_package - cheaper.cents_per_package) * 100) / 100;
      if (savePkg <= 0.01) continue;
      if (!top || savePkg > top.savePkg) top = { key: c.key, name: c.name, to: cheaper, savePkg };
    }
    return top;
  }, [quote]);
  const swapAnnual =
    bestSwap && hasUnits && t.cents_per_package > 0
      ? Math.round((t.annual_fee_usd as number) * (bestSwap.savePkg / t.cents_per_package))
      : null;

  // Packaging Studio is a Pro membership feature (admins see it too). All hooks above already ran.
  if (!isPro && !isAdmin) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <GazetteHeader
          title="Guides"
          subtitle="Build a package one decision at a time — see what every material pick costs, then get the punch list of what it owes."
        />
        <div className="mt-6">
          <GuidesTabs />
        </div>
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
      <div className="p-6 space-y-5 max-w-6xl mx-auto">
        <GazetteHeader
          title="Guides"
          subtitle="Build a package. See what EPR law charges it — and the one thing to do about it."
        />
        <GuidesTabs />

        <ScheduleSwitcher active={scheduleId} onSwitch={switchSchedule} sources={scheduleSources} />

        {/* Honest, non-blocking scope note when a non-CA schedule is active — one line, not a banner stack. */}
        {scheduleId !== 'ca' && (
          <p className="text-meta text-text-muted">
            Pricing against {activeSchedule.engine.program}. Obligation tracking (the punch list and
            markets below) is US-state only today.
          </p>
        )}

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

        <div className="grid gap-5 lg:grid-cols-2 items-start">
          {/* ================= LEFT · The package ================= */}
          <section className="rounded-panel border border-border-default bg-bg-secondary p-4 space-y-4">
            <div className="flex items-baseline justify-between">
              <span className={LBL}>The package</span>
              <span className="font-mono text-meta text-text-muted">{totalGrams} g total</span>
            </div>

            {/* The package, drawn as the forms it's made of */}
            <PackageShelf components={components} quote={quote} />

            {/* Component editors — name, material, weight, and the form picker */}
            <div className="space-y-3">
              {components.map((c) => {
                const qc = quote.components.find((q) => q.key === c.key);
                const form = c.form ?? formForCategory(qc?.category);
                return (
                  <div key={c.key} className="rounded-lg border border-border-default bg-bg-tertiary p-3 space-y-2.5">
                    <div className="flex items-center gap-2">
                      <PackageGlyph
                        form={form}
                        className={`w-6 h-6 shrink-0 ${qc && !qc.recyclable ? 'text-urgency-medium' : 'text-text-secondary'}`}
                      />
                      <input
                        type="text"
                        value={c.name}
                        onChange={(e) => updateComponent(c.key, { name: e.target.value })}
                        className="flex-1 min-w-0 bg-transparent text-sm font-semibold text-text-primary focus:outline-none"
                        aria-label="Component name"
                      />
                      {qc && (
                        <span className="shrink-0 font-mono text-meta text-text-muted">
                          {fmt.money(qc.cents_per_package)}/pkg
                        </span>
                      )}
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

                    <div className="grid grid-cols-[1fr_auto] gap-2">
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
                      <label className="flex items-center gap-1.5 text-xs text-text-secondary" htmlFor={`g-${c.key}`}>
                        <input
                          id={`g-${c.key}`}
                          type="number"
                          min={0}
                          step={1}
                          value={c.grams}
                          onChange={(e) => updateComponent(c.key, { grams: Number(e.target.value) || 0 })}
                          className="w-16 rounded-md border border-border-default bg-bg-primary px-2 py-1 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-green-accent/50"
                        />
                        g
                      </label>
                    </div>

                    {/* Form picker — a bit of agency: draw this part as what it really is */}
                    <FormPicker value={form} onPick={(f) => setForm(c.key, f)} />

                    {qc && (
                      <p className="text-meta text-text-muted">
                        <span className={qc.recyclable ? 'text-risk-low' : 'text-urgency-medium'}>
                          {qc.recyclable ? '♻ recyclable' : '⚠ hard to recycle'}
                        </span>
                        {qc.obligation_count > 0 && ` · ${qc.obligation_count} law${qc.obligation_count === 1 ? '' : 's'} to act on`}
                      </p>
                    )}

                    {/* Compare formats — the full curve, opt-in, single-hue (no rainbow) */}
                    {qc && qc.cost_curve.some((x) => x.same_family) && (
                      <details className="group">
                        <summary className="cursor-pointer text-meta text-green-accent hover:opacity-80 list-none">
                          Compare {qc.category_label.toLowerCase()} formats →
                        </summary>
                        <div className="mt-2">
                          <CostCurve c={qc} onSwap={(id) => setMaterial(c.key, id)} />
                        </div>
                      </details>
                    )}

                    {/* Design attributes — only for schedules that modulate on them (UK today) */}
                    <AttributeControls
                      inputs={activeSchedule.engine.inputs ?? []}
                      attrs={c.attrs}
                      onChange={(patch) =>
                        updateComponent(c.key, { attrs: pruneAttrs({ ...c.attrs, ...patch }) })
                      }
                    />
                  </div>
                );
              })}
            </div>

            <button
              type="button"
              onClick={addComponent}
              className="w-full rounded-lg border border-dashed border-border-default px-3 py-2 text-xs text-text-secondary hover:border-green-accent hover:text-green-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
            >
              ＋ Add component
            </button>

            {/* Saved packages — the account's, synced like the scope and watch list */}
            <SavedPackagesPanel
              signedIn={saved.signedIn}
              ready={saved.ready}
              packages={saved.packages}
              onLoad={loadSaved}
              onDelete={saved.remove}
              onSignIn={saved.openAuth}
            />

            {/* CI export — a Beta power feature, demoted behind a disclosure and the /account opt-in */}
            {betaEnabled && (
              <details className="rounded-lg border border-border-default bg-bg-tertiary p-3">
                <summary className="cursor-pointer text-xs text-text-secondary">
                  Export spec for engineering (packaging.yaml)
                </summary>
                <div className="mt-3 space-y-3">
                  <p className="text-xs text-text-secondary leading-relaxed">
                    A robot check that re-runs on every code change and flags the build when a new law
                    makes this spec non-compliant.
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
                      className="rounded-md border border-border-default bg-bg-secondary px-3 py-1.5 text-xs text-text-secondary hover:border-green-accent hover:text-text-primary transition-colors"
                    >
                      {copied === 'link' ? 'Link copied ✓' : 'Copy studio link'}
                    </button>
                  </div>
                  <div className="relative">
                    <pre className="rounded-lg border border-border-default bg-bg-primary p-3 pr-16 text-[11px] leading-relaxed text-text-secondary overflow-x-auto font-mono">
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
                </div>
              </details>
            )}
          </section>

          {/* ================= RIGHT · What it costs & what you owe ================= */}
          <section className="space-y-4">
            {/* One number */}
            <div className="rounded-panel border border-border-default bg-bg-secondary p-5">
              <p className={LBL}>What it costs</p>
              <div className="mt-1 font-mono text-4xl font-bold text-text-primary leading-none">
                {hasUnits ? fmt.amount(t.annual_fee_usd as number) : fmt.money(t.cents_per_package)}
                <span className="text-xl text-text-secondary font-normal">{hasUnits ? '/yr' : '/pkg'}</span>
                {pathwaysLoading && <span className="ml-2 align-middle text-meta italic text-text-muted">refreshing…</span>}
              </div>
              <p className="mt-2 text-xs text-text-secondary">
                {hasUnits ? (
                  <>
                    {fmt.money(t.cents_per_package)}/pkg · {t.units_per_year?.toLocaleString()} units/yr ·
                    priced on {activeSchedule.engine.program}
                  </>
                ) : (
                  <>Add annual units in the bar above for the $/yr figure · priced on {activeSchedule.engine.program}</>
                )}
              </p>
            </div>

            {/* The single cheapest honest swap — one move, not a rainbow */}
            {bestSwap && (
              <div className="rounded-panel border border-risk-low/40 bg-risk-low/10 p-4 flex items-center justify-between gap-3">
                <p className="text-sm text-text-secondary leading-relaxed">
                  Switch the <b className="text-text-primary">{bestSwap.name}</b> to{' '}
                  <b className="text-text-primary">{bestSwap.to.label.split(' — ')[0]}</b>
                  {bestSwap.to.recyclable && ' (recyclable)'} and save{' '}
                  <b className="text-risk-low">
                    {swapAnnual != null ? `${fmt.amount(swapAnnual)}/yr` : `${fmt.money(bestSwap.savePkg)}/pkg`}
                  </b>
                  .
                </p>
                <button
                  type="button"
                  onClick={() => setMaterial(bestSwap.key, bestSwap.to.material_id)}
                  className="shrink-0 rounded-md border border-risk-low px-3 py-1.5 text-xs font-medium text-risk-low hover:bg-risk-low/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
                >
                  Apply
                </button>
              </div>
            )}

            {/* The punch list — what you must do, by when */}
            <div>
              <p className={`${LBL} mb-2`}>What you owe{markets.length ? ` in ${markets.join(' · ')}` : ''}</p>
              <PunchList
                report={guardReport}
                loading={pathwaysLoading}
                defaultOpen
                onMarkHandled={(f) => addAck(`${f.market}:${f.billNumber}`)}
                onOpenBill={openBill}
                openingBillId={openingBillId}
              />
            </div>

            {/* Handled obligations — power control, tucked into a disclosure */}
            {acknowledged.length > 0 && (
              <details className="rounded-lg border border-border-default bg-bg-secondary p-3">
                <summary className="cursor-pointer text-xs text-text-secondary">
                  Handled obligations ({acknowledged.length})
                </summary>
                <div className="mt-2.5 space-y-2.5">
                  <div className="flex flex-wrap gap-1.5">
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
                </div>
              </details>
            )}

            <ProvenanceFooter schedule={activeSchedule} scheduleReady={scheduleReady} isCa={scheduleId === 'ca'} />
          </section>
        </div>

        {/* ================= Subscribe — keep watching this package's laws ================= */}
        <section
          aria-labelledby="watch-laws-heading"
          className="max-w-3xl rounded-panel border border-border-default bg-bg-secondary p-5"
        >
          <h2 id="watch-laws-heading" className="font-serif text-xl text-text-primary">
            Watch the laws shaping this package
          </h2>
          <p className="mt-1 mb-5 text-sm text-text-secondary leading-relaxed">
            Free email alerts when legislation touching the materials in this spec moves in the markets
            you picked. Pre-scoped to this package below; adjust anything.
          </p>
          {booted && <SubscribeForm prefill={{ usStates: markets, materials: subscribeMaterials }} />}
        </section>

        {/* Honest scope note kept quiet at the foot when the region view isn't US. */}
        {!isUsView && scheduleId === 'ca' && (
          <p className="text-meta text-text-muted">
            Fees are priced on California&apos;s SB-54 schedule (US states); switch the fee schedule
            above to price against another jurisdiction.
          </p>
        )}

        <BillModal bill={detailBill} onClose={() => setDetailBill(null)} />
      </div>
    </FmtCtx.Provider>
  );
}

// ---------------------------------------------------------------------------
// The drawn package — each component as the form it actually is
// ---------------------------------------------------------------------------
function PackageShelf({ components, quote }: { components: SpecComponent[]; quote: Quote }) {
  if (!components.length) {
    return <p className="text-text-muted italic text-sm">Add a component to draw the package.</p>;
  }
  return (
    <div className="flex flex-wrap items-end justify-center gap-5 rounded-lg border border-border-default bg-bg-tertiary/60 px-4 py-5">
      {components.map((c) => {
        const qc = quote.components.find((q) => q.key === c.key);
        const form = c.form ?? formForCategory(qc?.category);
        const recyclable = qc?.recyclable ?? true;
        return (
          <div key={c.key} className="flex w-16 flex-col items-center gap-1.5">
            <PackageGlyph
              form={form}
              className={`h-14 w-11 ${recyclable ? 'text-text-secondary' : 'text-urgency-medium'}`}
            />
            <span className="w-full truncate text-center text-meta text-text-muted" title={c.name}>
              {c.name || 'Part'}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** The form picker — a compact strip of the packaging archetypes. */
function FormPicker({ value, onPick }: { value: string; onPick: (form: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1">
      {PACKAGE_FORMS.map((f) => {
        const on = f.id === value;
        return (
          <button
            key={f.id}
            type="button"
            onClick={() => onPick(f.id)}
            aria-pressed={on}
            title={f.label}
            className={`rounded-md border p-1 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 ${
              on
                ? 'border-green-accent bg-green-dark/40 text-green-accent'
                : 'border-border-default bg-bg-primary text-text-muted hover:border-green-accent/60 hover:text-text-secondary'
            }`}
          >
            <PackageGlyph form={f.id} className="h-5 w-5" />
          </button>
        );
      })}
    </div>
  );
}

/** The same-family cost curve, single-hue (accent), current pick highlighted — the
 *  opt-in detail behind "Compare formats". No green→amber→red ramp; the bar is one color. */
function CostCurve({ c, onSwap }: { c: QuoteComponent; onSwap: (materialId: string) => void }) {
  const fmt = useFmt();
  const opts = c.cost_curve.filter((x) => x.same_family);
  const max = Math.max(...opts.map((o) => o.rate_per_tonne), 1);
  return (
    <div className="space-y-0.5">
      {opts.map((alt) => {
        const dl = alt.delta_per_tonne;
        const dtxt = alt.is_current ? 'current' : dl === 0 ? '=' : dl < 0 ? `−${fmt.rate(-dl).slice(1)}` : `+${fmt.rate(dl).slice(1)}`;
        return (
          <button
            key={alt.material_id}
            type="button"
            onClick={() => onSwap(alt.material_id)}
            disabled={alt.is_current}
            title={alt.is_current ? 'Current material' : `Swap to ${alt.label}`}
            className={`grid w-full grid-cols-[minmax(0,1fr)_5rem_4.5rem] items-center gap-2 rounded px-1 py-1 text-left transition-colors ${
              alt.is_current ? 'bg-green-dark/40' : 'hover:bg-bg-secondary'
            }`}
          >
            <span className="min-w-0 truncate text-xs">
              <span className={alt.is_current ? 'font-semibold text-text-primary' : 'text-text-secondary'}>{alt.label}</span>
            </span>
            <span className="relative block h-2 overflow-hidden rounded bg-bg-primary">
              <span
                className={`absolute inset-y-0 left-0 rounded ${alt.is_current ? 'bg-green-accent' : 'bg-green-accent/45'}`}
                style={{ width: `${(alt.rate_per_tonne / max) * 100}%` }}
              />
            </span>
            <span className="text-right font-mono text-meta text-text-secondary">
              {fmt.rate(alt.rate_per_tonne)}
              <br />
              <span className={dl < 0 ? 'text-risk-low' : dl > 0 ? 'text-urgency-medium' : 'text-text-muted'}>{dtxt}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fee-schedule picker — a compact button group with a source link per schedule.
// ---------------------------------------------------------------------------
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
        <span className={LBL}>Fee schedule</span>
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

/** The sticky spec bar — product name, markets, volume, and the running fee. */
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
        <span className={`${LBL} mr-1`}>Sells into</span>
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
    <footer className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-meta text-text-muted">
      <span>
        Fee basis:{' '}
        <a href={schedule.sourceUrl} target="_blank" rel="noopener noreferrer" className="text-green-accent hover:underline">
          {schedule.engine.provenance}
        </a>{' '}
        ({schedule.engine.program}, {schedule.engine.currency})
      </span>
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
// Schedule-driven design-attribute controls — only rendered for schedules that
// modulate on attributes (UK RAM grade today; none for CA/JP).
// ---------------------------------------------------------------------------
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
    <details className="pt-1">
      <summary className="cursor-pointer text-meta text-text-secondary">
        Design attributes <span className="text-text-muted">— these modulate the fee</span>
      </summary>
      <div className="mt-2 grid gap-2.5 sm:grid-cols-2">
        {inputs.map((input) => (
          <AttributeField key={input.attr} input={input} attrs={attrs} onChange={onChange} />
        ))}
      </div>
    </details>
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

  const cur = (attrs?.[input.attr] as string | undefined) ?? input.options?.[0]?.value ?? '';
  return (
    <label htmlFor={id} className="block text-xs text-text-secondary" title={input.help}>
      <span className="block mb-1">{input.label}</span>
      <select id={id} value={cur} onChange={(e) => onChange({ [input.attr]: e.target.value } as PackageAttributes)} className={fieldCls}>
        {input.options?.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

// ---------------------------------------------------------------------------
// The punch list — the guard verdict in plain words.
// ---------------------------------------------------------------------------
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

function PunchList({
  report,
  loading,
  onMarkHandled,
  onOpenBill,
  openingBillId,
  defaultOpen = false,
}: {
  report: ReturnType<typeof evaluate>;
  loading: boolean;
  onMarkHandled: (f: Finding) => void;
  onOpenBill: (billId: number) => void;
  openingBillId: number | null;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const { findings } = report;

  const toHandle = findings.filter((f) => f.severity !== 'note');
  const handled = findings.filter((f) => f.acknowledged);
  const watchOnly = findings.filter((f) => f.severity === 'note' && !f.acknowledged);
  const allClear = toHandle.length === 0;

  const shownToHandle = open ? toHandle : toHandle.slice(0, 4);

  return (
    <div className={`rounded-panel border bg-bg-secondary p-4 ${allClear ? 'border-risk-low/50' : 'border-urgency-high/50'}`}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            allClear ? 'bg-risk-low/15 text-risk-low' : 'bg-urgency-high/15 text-urgency-high'
          }`}
        >
          {allClear ? '✓ Nothing left to handle' : `${toHandle.length} to handle`}
        </span>
        <span className="text-xs text-text-secondary">
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
                      <b className={dd !== null && dd < 0 ? 'text-urgency-high' : 'text-text-primary'}>{formatDate(f.deadline)}</b>
                      {dd !== null && (
                        <span className={`text-meta ${dd < 0 ? 'text-urgency-high' : 'text-text-muted'}`}>
                          {' '}({dd < 0 ? `overdue ${-dd} days` : `in ${dd} days`})
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
          {handled.length > 0 && (
            <div className="mt-4">
              <p className={`${LBL} mb-1.5`}>Handled</p>
              <ul className="space-y-1">
                {handled.map((f, i) => (
                  <li key={`${f.market}-${f.billNumber}-h${i}`} className="flex items-baseline gap-2 text-xs text-text-muted">
                    <span className="text-risk-low" aria-hidden>✓</span>
                    <span className="min-w-0">
                      {actionSentence(f)} (
                      <BillLink billId={f.billId} billNumber={`${f.market} ${f.billNumber}`.trim()} market={f.market} onOpen={onOpenBill} openingBillId={openingBillId} />
                      ) — handled.
                    </span>
                    <WatchStar billId={f.billId} className="shrink-0 self-center -my-1" />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {watchOnly.length > 0 && (
            <div className="mt-4">
              <p className={`${LBL} mb-1.5`}>Watch-only — nothing to file today</p>
              <ul className="space-y-1">
                {watchOnly.map((f, i) => (
                  <li key={`${f.market}-${f.billNumber}-w${i}`} className="flex items-baseline gap-2 text-xs text-text-secondary">
                    <span className="w-8 shrink-0 font-mono text-meta text-green-accent">{f.market}</span>
                    <span className="min-w-0">
                      <BillLink billId={f.billId} billNumber={f.billNumber} market={f.market} onOpen={onOpenBill} openingBillId={openingBillId} />
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
    </div>
  );
}
