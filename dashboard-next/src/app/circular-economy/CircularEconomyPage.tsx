'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { useBills } from '@/hooks/useBills';
import { useReferralShare } from '@/hooks/useReferralShare';
import type { BillSummary } from '@/lib/types';
import { BillModal } from '@/components/ui/BillModal';
import { CheckIcon } from '@/components/ui/icons';
import { MATERIAL_CATEGORIES, categoryMatchValues } from '@/components/bills/BillFilters';
import { BUTTERFLY_NODES, ButterflyDiagram } from '@/components/insights/ButterflyDiagram';
import { sgroup, tallyButterfly } from '@/components/insights/ButterflyExplorer';
import { RegionFilter, REGION_CODES, regionLabel } from '@/components/insights/RegionFilter';
import { buildShareLink, captureShareLanding, trackShare } from '@/lib/ceShare';
import { renderShareCard } from '@/lib/svgImage';
import { track } from '@/lib/analytics';

/**
 * /circular-economy: the butterfly as a single-screen, shareable explorer. One region (or the world) on
 * the full diagram, or two regions as fingerprints with their one-sided gaps ringed in gold; a material
 * row re-scopes both. Click a step for its laws in a side panel (a bottom sheet on phones). The page
 * itself never scrolls: only the panel and the material row do.
 *
 * Everything is tallied in the browser from the CDN bill snapshot (it carries butterfly_steps and
 * material_categories), so every filter is instant and the counts match the Insights explorer exactly.
 * The view lives in the URL, which is what makes a share land on the same picture. See lib/ceShare for
 * how shares are tagged so the loop's viral coefficient can be read in GA.
 */

type Mode = 'one' | 'compare';
type Status = 'enacted' | 'all';

// The 14 steps a law can sit on (Share has no law anywhere and Biogas is out of scope by design).
const COUNTED: Array<[string, string]> = [
  ...BUTTERFLY_NODES.filter(n => !n.noSource).map(n => [n.id, n.name] as [string, string]),
  ['parts', 'Chemical restrictions'],
  ['service', 'Labeling'],
];
const stepName = (id: string) => COUNTED.find(([k]) => k === id)?.[1] ?? id;
const materialLabel = (m: string) => {
  const s = m.replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
};
const listNames = (ids: string[], max = 3) =>
  ids.length <= max ? ids.map(stepName).join(', ') : `${ids.slice(0, max).map(stepName).join(', ')} +${ids.length - max} more`;
const scopeName = (codes: string[]) =>
  !codes.length ? 'Every region' : codes.length <= 2 ? codes.map(regionLabel).join(' + ') : `${codes.length} regions`;
const isMobile = () => typeof navigator !== 'undefined' && /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);

function useSize(ref: RefObject<HTMLElement>) {
  const [size, setSize] = useState({ w: 1000, h: 600 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.round(e.contentRect.width), h: Math.round(e.contentRect.height) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}

function Seg<T extends string>({ value, options, onChange, label }: {
  value: T; options: Array<[T, string]>; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex shrink-0 overflow-hidden rounded-md border border-border-default">
      {options.map(([v, text], i) => (
        <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
          className={`px-3 py-1.5 text-sm ${i ? 'border-l border-border-default' : ''} ${
            value === v ? 'bg-text-primary text-bg-primary' : 'bg-bg-secondary text-text-secondary hover:text-text-primary'}`}>
          {text}
        </button>
      ))}
    </div>
  );
}

function RegionSelect({ id, value, onChange, label }: { id: string; value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label htmlFor={id} className="flex items-center">
      <span className="sr-only">{label}</span>
      <select id={id} value={value} onChange={e => onChange(e.target.value)}
        className="h-8 max-w-[11rem] rounded-md border border-border-default bg-bg-secondary px-2 text-sm text-text-primary">
        {REGION_CODES.map(c => <option key={c} value={c}>{regionLabel(c)}</option>)}
      </select>
    </label>
  );
}

export default function CircularEconomyPage() {
  const [mode, setMode] = useState<Mode>('one');
  const [regions, setRegions] = useState<string[]>([]);
  const [a, setA] = useState('FR');
  const [b, setB] = useState('US');
  const [material, setMaterial] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>('enacted');
  const [step, setStep] = useState<string | null>(null);
  const [open, setOpen] = useState<BillSummary | null>(null);
  const [urlReady, setUrlReady] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busyImage, setBusyImage] = useState(false);

  const stageRef = useRef<HTMLDivElement>(null);
  const oneRef = useRef<HTMLDivElement>(null);
  const aRef = useRef<HTMLDivElement>(null);
  const bRef = useRef<HTMLDivElement>(null);
  const stage = useSize(stageRef as RefObject<HTMLElement>);

  const { link: refLink } = useReferralShare('ce_map');
  const refCode = useMemo(() => {
    try { return refLink ? new URL(refLink).searchParams.get('ref') : null; } catch { return null; }
  }, [refLink]);

  // Read the view from the URL once, and record a share-link landing.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const known = (c: string | null) => (c && REGION_CODES.includes(c.toUpperCase()) ? c.toUpperCase() : null);
    if (p.get('a') || p.get('b')) {
      setMode('compare');
      setA(known(p.get('a')) ?? 'FR');
      setB(known(p.get('b')) ?? 'US');
    } else if (p.get('r')) {
      setRegions(p.get('r')!.split(',').map(known).filter((c): c is string => !!c));
    }
    const m = p.get('m');
    if (m && MATERIAL_CATEGORIES.includes(m)) setMaterial(m);
    if (p.get('s') === 'all') setStatus('all');
    const st = p.get('step');
    if (st && COUNTED.some(([k]) => k === st)) setStep(st);
    captureShareLanding();
    setUrlReady(true);
  }, []);

  const viewParams = () => {
    const p = new URLSearchParams();
    if (mode === 'compare') { p.set('a', a); p.set('b', b); }
    else if (regions.length) p.set('r', regions.join(','));
    if (material) p.set('m', material);
    if (status === 'all') p.set('s', 'all');
    if (step) p.set('step', step);
    return p;
  };

  // Keep the address bar on the current view, so a copied URL is a working share too. Waits for the
  // read above: the first write also drops the landing's via/utm/ref params, which the attribution and
  // referral capture (AuthContext, a parent, so its mount effect runs after ours) have read by then.
  useEffect(() => {
    if (!urlReady) return;
    const q = viewParams().toString();
    window.history.replaceState(null, '', q ? `?${q}` : window.location.pathname);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlReady, mode, regions, a, b, material, status, step]);

  const { data: all } = useBills({ ce_relevant: true, limit: 5000, regions: 'all' });

  const statusOk = (x: BillSummary) => status === 'all' || sgroup(x) === 'enacted';
  const matSet = useMemo(() => (material ? new Set(categoryMatchValues(material)) : null), [material]);
  const matOk = (x: BillSummary) => !matSet || (x.material_categories ?? []).some(m => matSet.has(m as string));

  // Status + region scope before the material filter: the material row counts against it.
  const base = useMemo(() => {
    if (!all) return null;
    const inScope = mode === 'compare'
      ? (x: BillSummary) => x.region === a || x.region === b
      : (x: BillSummary) => !regions.length || regions.includes(x.region);
    return all.filter(x => statusOk(x) && inScope(x));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, mode, regions, a, b, status]);
  const scoped = useMemo(() => (base ? base.filter(matOk) : null), [base, matSet]); // eslint-disable-line react-hooks/exhaustive-deps
  const aBills = useMemo(() => (scoped ?? []).filter(x => x.region === a), [scoped, a]);
  const bBills = useMemo(() => (scoped ?? []).filter(x => x.region === b), [scoped, b]);

  const counts = useMemo(() => (scoped ? tallyButterfly(scoped) : null), [scoped]);
  const aCounts = useMemo(() => (scoped ? tallyButterfly(aBills) : null), [scoped, aBills]);
  const bCounts = useMemo(() => (scoped ? tallyButterfly(bBills) : null), [scoped, bBills]);

  const materials = useMemo(() => {
    if (!base) return [];
    const rows = MATERIAL_CATEGORIES.filter(m => m !== 'other').map(m => {
      const vals = new Set(categoryMatchValues(m));
      return { m, n: base.filter(x => (x.material_categories ?? []).some(v => vals.has(v as string))).length };
    });
    return rows.filter(r => r.n > 0 || r.m === material).sort((x, y) => y.n - x.n);
  }, [base, material]);

  const covered = (c: ReturnType<typeof tallyButterfly> | null) => COUNTED.filter(([id]) => (c?.steps[id] ?? 0) > 0).map(([id]) => id);
  const gaps = (c: ReturnType<typeof tallyButterfly> | null) => COUNTED.filter(([id]) => !(c?.steps[id] ?? 0)).map(([id]) => id);
  const onlyA = useMemo(() => covered(aCounts).filter(id => !(bCounts?.steps[id] ?? 0)), [aCounts, bCounts]);
  const onlyB = useMemo(() => covered(bCounts).filter(id => !(aCounts?.steps[id] ?? 0)), [aCounts, bCounts]);

  const noun = status === 'enacted' ? 'laws in force' : 'laws and bills';
  const on = material ? ` on ${materialLabel(material).toLowerCase()}` : '';
  const title = mode === 'compare'
    ? `${regionLabel(a)} vs ${regionLabel(b)}${material ? ` · ${materialLabel(material)}` : ''}`
    : `${scopeName(regions)}${material ? ` · ${materialLabel(material)}` : ''}`;
  const headline = !counts
    ? 'Loading the corpus…'
    : mode === 'compare'
      ? `${regionLabel(a)} covers ${covered(aCounts).length} of ${COUNTED.length} circular-economy steps${on}; ${regionLabel(b)} covers ${covered(bCounts).length}.`
      : counts.total
        ? `${counts.total.toLocaleString()} ${noun}${on} cover ${covered(counts).length} of ${COUNTED.length} circular-economy steps.`
        : `No ${noun}${on} here yet: every step is a gap.`;

  // ── actions ──
  const pick = <T,>(set: (v: T) => void, kind: string, value: T, label?: string) => {
    set(value);
    track('ce_map_filter', { filter_kind: kind, filter_value: label ?? String(value ?? 'all') });
  };
  const clickStep = (id: string) => {
    setStep(s => (s === id ? null : id));
    track('ce_map_step', { step: id, view_mode: mode });
  };
  const shareCtx = () => ({ view_mode: mode, material: material ?? 'all', status, has_step: !!step });

  async function onShare() {
    if (isMobile() && navigator.share) {
      const s = buildShareLink(viewParams(), 'native', refCode);
      try {
        await navigator.share({ title: `Circular Economy Policies: ${title}`, text: headline, url: s.url });
        trackShare('native', s.id, s.gen, shareCtx());
      } catch { /* dismissed */ }
      return;
    }
    const s = buildShareLink(viewParams(), 'copy', refCode);
    try {
      await navigator.clipboard.writeText(s.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      window.prompt('Copy this link:', s.url);
    }
    trackShare('copy', s.id, s.gen, shareCtx());
  }

  async function onImage() {
    const svgs = (mode === 'compare' ? [aRef, bRef] : [oneRef])
      .map(r => r.current?.querySelector('svg'))
      .filter((x): x is SVGSVGElement => !!x);
    if (!svgs.length) return;
    setBusyImage(true);
    try {
      const blob = await renderShareCard({
        title,
        headline,
        panels: svgs.map((svg, i) => ({ svg, caption: mode === 'compare' ? regionLabel(i ? b : a) : undefined })),
        footer: 'atlascircular.com/circular-economy',
      });
      const file = new File([blob], `circular-economy-${mode === 'compare' ? `${a}-vs-${b}` : regions.join('-') || 'world'}${material ? `-${material}` : ''}.png`.toLowerCase(), { type: 'image/png' });
      if (isMobile() && navigator.canShare?.({ files: [file] })) {
        const s = buildShareLink(viewParams(), 'image', refCode);
        try {
          await navigator.share({ files: [file], title: `Circular Economy Policies: ${title}`, text: `${headline} ${s.url}` });
          trackShare('image', s.id, s.gen, shareCtx());
        } catch { /* dismissed */ }
      } else {
        const href = URL.createObjectURL(blob);
        const el = document.createElement('a');
        el.href = href;
        el.download = file.name;
        el.click();
        setTimeout(() => URL.revokeObjectURL(href), 1000);
        track('ce_map_image_download', shareCtx());
      }
    } catch {
      track('ce_map_image_error', {});
    } finally {
      setBusyImage(false);
    }
  }

  // ── step panel ──
  const panelGroups = useMemo(() => {
    if (!step || !scoped) return [];
    const at = (xs: BillSummary[]) => xs.filter(x => x.butterfly_steps?.includes(step))
      .sort((x, y) => (sgroup(x) === 'enacted' ? 0 : 1) - (sgroup(y) === 'enacted' ? 0 : 1)
        || (y.last_action_date ?? y.status_date ?? '').localeCompare(x.last_action_date ?? x.status_date ?? ''));
    return mode === 'compare'
      ? [{ name: regionLabel(a), bills: at(aBills) }, { name: regionLabel(b), bills: at(bBills) }]
      : [{ name: '', bills: at(scoped) }];
  }, [step, scoped, mode, a, b, aBills, bBills]);
  const places = useMemo(() => {
    if (mode === 'compare' || !panelGroups[0]) return [];
    const m = new Map<string, number>();
    for (const x of panelGroups[0].bills) {
      const k = x.region === 'US' && regions.length === 1 && regions[0] === 'US' ? (x.state?.split('-')[0] || 'US') : regionLabel(x.region);
      m.set(k, (m.get(k) ?? 0) + 1);
    }
    return [...m].sort((x, y) => y[1] - x[1]).slice(0, 6);
  }, [panelGroups, mode, regions]);

  const narrow = stage.w < 640;
  const highlight = useMemo(() => new Set([...onlyA, ...onlyB]), [onlyA, onlyB]);

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-bg-primary text-text-primary">
      {/* Slim header: the brand, the page, and the two share actions. */}
      <header className="flex items-center gap-2 border-b border-border-default px-4 py-2">
        <Link href="/" className="shrink-0 font-serif text-base font-semibold text-text-primary hover:text-[rgb(var(--green-accent))]">Atlas Circular</Link>
        <span className="hidden text-text-muted sm:inline" aria-hidden>/</span>
        {/* Phones: the headline row names the scope; the title stays for assistive tech. */}
        <h1 className="sr-only min-w-0 truncate font-serif text-base sm:not-sr-only sm:text-lg">Circular Economy Policies</h1>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <button type="button" onClick={onShare}
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-text-primary px-3 text-sm font-medium text-bg-primary hover:opacity-90">
            {copied ? <CheckIcon /> : null}{copied ? 'Link copied' : 'Share this view'}
          </button>
          <button type="button" onClick={onImage} disabled={busyImage} aria-label="Download this view as an image"
            className="hidden h-8 items-center rounded-md border border-border-default px-3 text-sm text-text-secondary hover:text-text-primary disabled:opacity-50 sm:inline-flex">
            {busyImage ? 'Rendering…' : 'Image'}
          </button>
          <Link href="/" onClick={() => track('ce_map_exit', { target: 'explore' })}
            className="hidden text-sm text-[rgb(var(--green-accent))] hover:underline lg:inline">Explore every law →</Link>
        </div>
      </header>

      {/* Scope: mode, region(s), status. */}
      <div className="flex flex-wrap items-center gap-2 px-4 pt-2">
        <Seg label="View" value={mode} onChange={v => pick(setMode, 'mode', v)} options={[['one', 'Explore'], ['compare', 'Compare two']]} />
        {mode === 'one' ? (
          <RegionFilter selected={regions} variant="toolbar" onChange={v => pick(setRegions, 'regions', v, v.join(',') || 'all')} />
        ) : (
          <div className="flex items-center gap-1">
            <RegionSelect id="ce-a" label="First region" value={a} onChange={v => pick(setA, 'region_a', v)} />
            <button type="button" aria-label="Swap the two regions" onClick={() => { setA(b); setB(a); track('ce_map_filter', { filter_kind: 'swap', filter_value: '' }); }}
              className="h-8 rounded-md px-1.5 text-text-muted hover:bg-bg-tertiary hover:text-text-primary">⇄</button>
            <RegionSelect id="ce-b" label="Second region" value={b} onChange={v => pick(setB, 'region_b', v)} />
          </div>
        )}
        <Seg label="Status" value={status} onChange={v => pick(setStatus, 'status', v)} options={[['enacted', 'In force'], ['all', 'Incl. bills']]} />
      </div>

      {/* Material row: one at a time, so the diagram answers "what about plastics?" cleanly. */}
      <div role="group" aria-label="Material" className="flex shrink-0 gap-1.5 overflow-x-auto px-4 py-2 [scrollbar-width:none]">
        {[{ m: null as string | null, n: base?.length ?? 0 }, ...materials].map(({ m, n }) => {
          const active = material === m;
          return (
            <button key={m ?? 'all'} type="button" aria-pressed={active} onClick={() => pick(setMaterial, 'material', active && m ? null : m, m ?? 'all')}
              className={`shrink-0 whitespace-nowrap rounded-full border px-3 py-1 text-xs transition-colors ${
                active ? 'border-text-primary bg-text-primary text-bg-primary' : 'border-border-default text-text-secondary hover:border-text-muted hover:text-text-primary'}`}>
              {m ? materialLabel(m) : 'All materials'} <span className={`font-mono ${active ? '' : 'text-text-muted'}`}>{n.toLocaleString()}</span>
            </button>
          );
        })}
      </div>

      {/* The headline: the sentence a share carries. */}
      <div className="px-4 pb-1">
        <p className="font-serif text-lg leading-snug sm:text-xl">
          <span className="text-text-muted">{title}: </span>{headline}
        </p>
        <p className="mt-0.5 truncate text-xs text-text-secondary">
          {mode === 'compare'
            ? <>Only {regionLabel(a)}: {onlyA.length ? listNames(onlyA) : 'none'} · Only {regionLabel(b)}: {onlyB.length ? listNames(onlyB) : 'none'} {highlight.size > 0 && <span className="text-text-muted">(ringed in gold)</span>}</>
            : counts && <>Gaps: {gaps(counts).length ? listNames(gaps(counts), 4) : 'none, every step is covered'}. Click a step to see its laws.</>}
        </p>
      </div>

      {/* Stage: fills what's left of the screen. */}
      <div className="relative flex min-h-0 flex-1 gap-3 px-4 pb-2">
        <div ref={stageRef} className="min-h-0 min-w-0 flex-1">
          {mode === 'one' ? (
            <div ref={oneRef} className="h-full">
              <ButterflyDiagram counts={counts} fit compact={narrow} unit={noun} selected={step} onStepClick={id => clickStep(id)}
                haloColor="var(--bg-primary)" ariaLabel={`Circular economy policies: ${title}`} />
            </div>
          ) : (
            <div className="grid h-full grid-rows-2 gap-2 md:grid-cols-2 md:grid-rows-1">
              {([[a, aCounts, aRef, aBills], [b, bCounts, bRef, bBills]] as const).map(([code, c, ref, xs], i) => (
                <div key={i} className="flex min-h-0 flex-col rounded-lg border border-border-default p-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <h2 className="truncate font-serif text-base">{regionLabel(code)}</h2>
                    <span className="shrink-0 text-xs text-text-muted">
                      <span className="font-mono text-text-primary">{covered(c).length}/{COUNTED.length}</span> steps · <span className="font-mono">{xs.length.toLocaleString()}</span> {noun}
                    </span>
                  </div>
                  <div ref={ref} className="min-h-0 flex-1">
                    <ButterflyDiagram counts={c} fit compact unit={noun} selected={step} highlight={highlight}
                      onStepClick={id => clickStep(id)} haloColor="var(--bg-primary)" ariaLabel={`Coverage fingerprint for ${regionLabel(code)}`} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {step && (
          <aside aria-label={`${stepName(step)}: laws`}
            className="absolute inset-x-0 bottom-0 z-20 flex max-h-[62%] flex-col rounded-t-xl border border-border-default bg-bg-secondary shadow-xl md:static md:z-auto md:max-h-none md:w-80 md:shrink-0 md:rounded-xl md:shadow-none">
            <div className="flex items-start justify-between gap-2 border-b border-border-default px-3 py-2">
              <div>
                <h2 className="font-serif text-lg leading-tight">{stepName(step)}</h2>
                <p className="text-xs text-text-muted">
                  {panelGroups.map(g => `${g.name ? `${g.name} ` : ''}${g.bills.length.toLocaleString()}`).join(' · ')} {noun}{on}
                </p>
              </div>
              <button type="button" onClick={() => setStep(null)} aria-label="Close" className="rounded px-2 text-lg text-text-muted hover:text-text-primary">×</button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-2">
              {places.length > 1 && (
                <ul className="mb-3 space-y-1">
                  {places.map(([name, n]) => (
                    <li key={name} className="flex items-center gap-2 text-xs">
                      <span className="w-24 shrink-0 truncate text-text-secondary">{name}</span>
                      <span className="h-2 rounded-sm bg-[rgb(var(--green-accent))]" style={{ width: `${(n / places[0][1]) * 100}%`, maxWidth: '9rem' }} />
                      <span className="font-mono text-text-muted">{n}</span>
                    </li>
                  ))}
                </ul>
              )}
              {panelGroups.map(g => (
                <div key={g.name} className="mb-3">
                  {g.name && <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-text-muted">{g.name}</h3>}
                  {!g.bills.length && <p className="text-sm text-text-muted">None: a gap.</p>}
                  <ul className="divide-y divide-border-default">
                    {g.bills.slice(0, 60).map(x => (
                      <li key={x.id}>
                        <button type="button" onClick={() => { setOpen(x); track('ce_map_bill_open', { step }); }}
                          className="w-full py-1.5 text-left text-sm hover:text-[rgb(var(--green-accent))]">
                          <span className="line-clamp-2">{x.title}</span>
                          <span className="block font-mono text-[11px] text-text-muted">
                            {x.region === 'US' ? `US · ${x.state}` : regionLabel(x.region)} · {x.bill_number} · {sgroup(x) === 'enacted' ? 'In force' : sgroup(x) === 'ended' ? 'Ended' : 'Pending'}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  {g.bills.length > 60 && (
                    <Link href="/" className="mt-1 block text-xs text-[rgb(var(--green-accent))] hover:underline">
                      {(g.bills.length - 60).toLocaleString()} more in the full explorer →
                    </Link>
                  )}
                </div>
              ))}
            </div>
          </aside>
        )}
      </div>

      {/* Legend + credit. */}
      <footer className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border-default px-4 py-1.5 text-[11px] text-text-muted">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#1e6ae9]" />Technical cycle</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#637c25]" />Biological cycle</span>
        <span>Darker = more laws · hatched = no law (a gap)</span>
        <span className="ml-auto hidden sm:inline">
          After the <a href="https://www.ellenmacarthurfoundation.org/circular-economy-diagram" target="_blank" rel="noopener noreferrer" className="hover:underline">Ellen MacArthur Foundation butterfly</a>
          {' · '}<Link href="/methodology/" className="hover:underline">How steps are placed</Link>
        </span>
      </footer>

      <BillModal bill={open} onClose={() => setOpen(null)} />
    </div>
  );
}
