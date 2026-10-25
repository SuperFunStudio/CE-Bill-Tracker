'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import type { BillSummary, ButterflyCounts } from '@/lib/types';
import { BillModal } from '@/components/ui/BillModal';
import { regionLabel } from './RegionFilter';
import {
  BUTTERFLY_NODES, ButterflyDiagram, ButterflyUnplaced, UNPLACED_LABELS,
  type ButterflyStepId, type ButterflyUnplacedId,
} from './ButterflyDiagram';
import { track } from '@/lib/analytics';

/**
 * The zoomable butterfly: the diagram, and behind every step its bills as dots. Click a step to open it
 * into clusters by region (or by the picked countries), click a cluster's name to split it by state or
 * country, click a dot to read the bill. Status and search regroup the dots in place. Ported from the
 * butterfly explorer prototype (docs/butterfly-explorer).
 *
 * Bills come from the caller (the snapshot-backed bill list, which carries `butterfly_steps`); the
 * diagram's own counts are tallied from the same list so the two can never disagree.
 */

type Status = 'all' | 'enacted' | 'pending' | 'ended';
const ENACTED = new Set(['enacted', 'active']);
const ENDED = new Set(['failed', 'vetoed', 'repealed']);
const sgroup = (b: BillSummary): Exclude<Status, 'all'> =>
  ENACTED.has(b.status ?? '') ? 'enacted' : ENDED.has(b.status ?? '') ? 'ended' : 'pending';
const STATUS_LABEL: Record<Status, string> = { all: 'All', enacted: 'In force', pending: 'Pending', ended: 'Failed or repealed' };
const ORDER = { enacted: 0, pending: 1, ended: 2 } as const;

const FAMILIES: Array<[string, string, string[]]> = [
  ['US', 'United States', ['US']],
  ['EUR', 'Europe', 'EU FR UK PL SE NL DE ES FI DK IT IE CH SI AT LU LT SK LV EE NO CZ TR BE BG HR CY GR HU MT PT RO'.split(' ')],
  ['APAC', 'Asia-Pacific', 'JP CN AU IN ID MY KR'.split(' ')],
  ['AMER', 'Rest of the Americas', 'CA BR EC CL CO PE UY MX CR HN'.split(' ')],
  ['AFR', 'Africa', 'KE RW ZM MW ZA SL'.split(' ')],
];
const familyOf = (b: BillSummary) => FAMILIES.find(([, , codes]) => codes.includes(b.region))?.[0] ?? 'EUR';
const familyName = (k: string) => FAMILIES.find(([key]) => key === k)?.[1] ?? k;
// US city ordinances are stored as state "<ST>-<CITY>"; they count under their state here.
const jurOf = (b: BillSummary) => (b.region === 'US' ? (b.state === 'US' || !b.state ? 'US federal' : b.state.split('-')[0]) : b.region);
const jurName = (j: string) => (j === 'US federal' ? 'US federal' : j.length === 2 && j === j.toUpperCase() ? regionLabel(j) : j);

const COLOR = { t: '#1e6ae9', b: '#6f8a2e', x: '#3f7a8c', u: '#9aa1ab' };
const BIO = new Set(['organics', 'biobased', 'agriculture', 'biodiversity']);
const CROSS = new Set(['textiles', 'water']);
function dotColor(b: BillSummary) {
  const mats = (b.material_categories ?? []) as string[];
  const bio = mats.some(m => BIO.has(m) || CROSS.has(m));
  const tech = mats.some(m => (!BIO.has(m) && m !== 'other') || CROSS.has(m));
  return bio && tech ? COLOR.x : bio ? COLOR.b : tech ? COLOR.t : COLOR.u;
}

// The "Not on a step" buckets. They overlap (an incentive with no step counts in both), like the steps do.
const instrumentsOf = (b: BillSummary) => (b.instrument_types ?? (b.instrument_type ? [b.instrument_type] : [])) as string[];
const UNPLACED_TEST: Record<ButterflyUnplacedId, (b: BillSummary) => boolean> = {
  incentives: b => instrumentsOf(b).includes('incentives'),
  waste_shipment: b => instrumentsOf(b).includes('waste_shipment'),
  other: b => { const it = instrumentsOf(b); return !it.length || it.some(i => ['other', 'budget', 'preemption', 'reporting'].includes(i)); },
  no_step: b => !(b.butterfly_steps ?? []).length,
};
const isUnplaced = (id: string): id is ButterflyUnplacedId => id in UNPLACED_TEST;

const GOLD = 2.39996323;
interface Group { key: string; label: string; bills: BillSummary[]; c: number; rad: number; cx: number; cy: number }

/** Shelf-pack phyllotaxis discs. Narrow screens get two clusters per row (big ones pack tighter). */
function layout(groups: Array<{ key: string; label: string; bills: BillSummary[] }>, c: number, maxW: number) {
  const twoCol = maxW < 640, colW = maxW / 2;
  const gs: Group[] = groups.map(g => {
    const gc = twoCol ? Math.min(c, (colW / 2 - 14) / Math.sqrt(g.bills.length + 0.5)) : c;
    return { ...g, c: gc, rad: gc * Math.sqrt(g.bills.length) + 8, cx: 0, cy: 0 };
  });
  const gw = (g: Group) => (twoCol ? colW - 0.5 : Math.max(2 * g.rad, 150) + 34);
  const rows: Group[][] = [];
  let row: Group[] = [], w = 0;
  for (const g of gs) {
    if (row.length && w + gw(g) > maxW) { rows.push(row); row = []; w = 0; }
    row.push(g); w += gw(g);
  }
  if (row.length) rows.push(row);
  let y = 6, maxX = 0;
  for (const r of rows) {
    const h = Math.max(...r.map(g => g.rad));
    let x = 0;
    for (const g of r) { g.cx = x + gw(g) / 2; g.cy = y + 34 + h; x += gw(g); }
    maxX = Math.max(maxX, x); y += 2 * h + 60;
  }
  const W = Math.max(maxX, maxW);
  for (const r of rows) { const rw = r.reduce((a, g) => a + gw(g), 0); for (const g of r) g.cx += (W - rw) / 2; }
  return { groups: gs, w: W, h: Math.max(y, 260) };
}
const phyllo = (g: Group, i: number): [number, number] => {
  const rr = g.c * Math.sqrt(i + 0.5), th = i * GOLD;
  return [g.cx + rr * Math.cos(th), g.cy + rr * Math.sin(th)];
};

function groupBy(bills: BillSummary[], key: (b: BillSummary) => string, label: (k: string) => string) {
  const m = new Map<string, BillSummary[]>();
  for (const b of bills) { const k = key(b); if (!m.has(k)) m.set(k, []); m.get(k)!.push(b); }
  return [...m].map(([k, bs]) => ({ key: k, label: label(k), bills: bs })).sort((a, b) => b.bills.length - a.bills.length);
}

function useWidth(ref: RefObject<HTMLElement>) {
  const [w, setW] = useState(900);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

export function ButterflyExplorer({
  bills,
  groupByCountry = false,
  baseStatus = 'all',
  haloColor = 'var(--bg-secondary)',
}: {
  /** The in-scope bills to draw (already region-filtered by the caller). null while loading. */
  bills: BillSummary[] | null;
  /** True when the caller filtered to picked regions: zoom then groups by country, not continent. */
  groupByCountry?: boolean;
  /** The caller's status scope for the diagram counts ('enacted' on Insights by default). */
  baseStatus?: Status;
  haloColor?: string;
}) {
  const [step, setStep] = useState<ButterflyStepId | ButterflyUnplacedId | null>(null);
  const [fam, setFam] = useState<string | null>(null);
  const [jur, setJur] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>('all');
  const [q, setQ] = useState('');
  const [shown, setShown] = useState(30);
  const [open, setOpen] = useState<BillSummary | null>(null);
  const [origin, setOrigin] = useState('50% 30%');
  const stageRef = useRef<HTMLDivElement>(null);
  const width = useWidth(stageRef as RefObject<HTMLElement>);

  // The caller's status scope applies everywhere; the in-stage status chips narrow further.
  const scoped = useMemo(
    () => (bills ?? []).filter(b => baseStatus === 'all' || sgroup(b) === baseStatus),
    [bills, baseStatus],
  );
  // A new scope (other regions picked) can drop the picked cluster: step back out. Keyed on a content
  // signature, not the array: a caller that re-filters every render would otherwise reset the zoom on
  // every render (the same array-identity thrash that once broke the homepage dot wall).
  const scopeSig = bills ? `${bills.length}:${bills[0]?.id ?? ''}:${bills[bills.length - 1]?.id ?? ''}` : '';
  useEffect(() => { setFam(null); setJur(null); }, [groupByCountry, scopeSig]);

  const counts: ButterflyCounts | null = useMemo(() => {
    if (!bills) return null;
    const steps: Record<string, number> = {};
    for (const b of scoped) for (const s of b.butterfly_steps ?? []) steps[s] = (steps[s] ?? 0) + 1;
    const unplaced = { incentives: 0, waste_shipment: 0, other: 0, no_step: 0 };
    for (const b of scoped) for (const id of Object.keys(UNPLACED_TEST) as ButterflyUnplacedId[]) if (UNPLACED_TEST[id](b)) unplaced[id]++;
    return { total: scoped.length, steps, wings: {}, unplaced };
  }, [bills, scoped]);

  const stepBills = useMemo(
    () => (!step ? [] : isUnplaced(step) ? scoped.filter(UNPLACED_TEST[step]) : scoped.filter(b => b.butterfly_steps?.includes(step))),
    [scoped, step],
  );
  const l1 = groupByCountry
    ? { key: (b: BillSummary) => b.region, label: (k: string) => regionLabel(k) }
    : { key: familyOf, label: familyName };
  const level = step ? (fam ? 2 : 1) : 0;
  const famBills = useMemo(() => (fam ? stepBills.filter(b => l1.key(b) === fam) : stepBills), [stepBills, fam, l1]);
  const focus = useMemo(() => (jur ? famBills.filter(b => jurOf(b) === jur) : famBills), [famBills, jur]);
  const matches = (b: BillSummary) =>
    (status === 'all' || sgroup(b) === status) &&
    (!q || `${b.bill_number ?? ''} ${b.title ?? ''} ${b.state} ${regionLabel(b.region)}`.toLowerCase().includes(q.toLowerCase()));
  const listed = useMemo(
    () => focus.filter(matches).sort((a, b) => (b.last_action_date ?? b.status_date ?? '').localeCompare(a.last_action_date ?? a.status_date ?? '')),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [focus, status, q],
  );
  const filtering = status !== 'all' || !!q;
  const ok = useMemo(() => new Set(listed.map(b => b.id)), [listed]);

  const stage = useMemo(() => {
    if (!level) return null;
    const groups = level === 1 ? groupBy(stepBills, l1.key, l1.label) : groupBy(famBills, jurOf, jurName);
    return layout(groups, level === 1 ? 7.2 : 9.4, Math.max(280, width - 8));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, stepBills, famBills, width, groupByCountry]);
  const dot = level === 1 ? 4.8 : 6.4;
  const stepName = !step ? ''
    : isUnplaced(step) ? UNPLACED_LABELS[step]
    : BUTTERFLY_NODES.find(n => n.id === step)?.name ?? (step === 'parts' ? 'Chemical restrictions' : 'Labeling');

  const zoomFrom = (el: Element | null) => {
    const host = stageRef.current;
    if (el && host) {
      const a = host.getBoundingClientRect(), r = el.getBoundingClientRect();
      setOrigin(`${r.left + r.width / 2 - a.left}px ${r.top + r.height / 2 - a.top}px`);
    } else setOrigin('50% 30%');
  };
  const openStep = (id: ButterflyStepId | ButterflyUnplacedId, el: Element) => {
    zoomFrom(el); setStep(id); setFam(null); setJur(null); setShown(30);
    track('butterfly_step_open', { step: id });
  };
  const back = () => { setOrigin('50% 50%'); if (jur) setJur(null); else if (fam) setFam(null); else setStep(null); };

  return (
    <div className="space-y-3">
      {/* Breadcrumb + the in-stage filters. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        <nav aria-label="Zoom level" className="flex flex-wrap items-center gap-1">
          {[
            { label: 'Butterfly', n: scoped.length, go: level ? () => { setOrigin('50% 50%'); setStep(null); setFam(null); setJur(null); } : null },
            ...(step ? [{ label: stepName, n: stepBills.length, go: fam ? () => { setOrigin('50% 50%'); setFam(null); setJur(null); } : null }] : []),
            ...(fam ? [{ label: l1.label(fam), n: famBills.length, go: jur ? () => setJur(null) : null }] : []),
            ...(jur ? [{ label: jurName(jur), n: focus.length, go: null }] : []),
          ].map((c, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <span className="text-text-muted">›</span>}
              {c.go ? (
                <button type="button" onClick={c.go} className="rounded px-1 text-[rgb(var(--green-accent))] hover:bg-bg-tertiary">{c.label}</button>
              ) : (
                <span className="px-1 font-medium text-text-primary">{c.label}</span>
              )}
              <span className="font-mono text-xs text-text-muted">{c.n.toLocaleString()}</span>
            </span>
          ))}
        </nav>
        {level > 0 && (
          <>
            <button type="button" onClick={back} className="ml-auto rounded-md border border-border-default px-3 py-1 text-xs text-text-secondary hover:text-text-primary">
              Zoom out
            </button>
            <div className="flex w-full flex-wrap items-center gap-2">
              <div role="group" aria-label="Status" className="inline-flex overflow-hidden rounded-md border border-border-default text-xs">
                {(['all', 'enacted', 'pending', 'ended'] as Status[]).filter(s => baseStatus === 'all' || s === 'all' || s === baseStatus).map((s, i) => (
                  <button key={s} type="button" aria-pressed={status === s} onClick={() => setStatus(s)}
                    className={`px-2.5 py-1 ${i ? 'border-l border-border-default' : ''} ${status === s ? 'bg-text-primary text-bg-primary' : 'text-text-secondary hover:text-text-primary'}`}>
                    {STATUS_LABEL[s]}
                  </button>
                ))}
              </div>
              <input type="search" value={q} onChange={e => { setQ(e.target.value); setShown(30); }} placeholder="Search these bills"
                aria-label="Search the bills in view"
                className="h-7 w-full max-w-[16rem] rounded-md border border-border-default bg-bg-secondary px-2 text-xs text-text-primary" />
            </div>
          </>
        )}
      </div>

      <div ref={stageRef} className="relative overflow-hidden">
        {level === 0 ? (
          <div key="bf" className="bf-stage" style={{ transformOrigin: origin }}>
            {/* Phones get the compact fingerprint: at that width the full diagram's labels can't be read. */}
            <ButterflyDiagram counts={counts} compact={width < 640} unit="laws and bills" haloColor={haloColor} onStepClick={openStep} />
            <p className="mt-2 text-xs text-text-muted">
              {width < 640 ? 'Tap a step to open it into its bills. Turn your phone sideways for step names.' : 'Click a step to open it into its bills.'}
            </p>
          </div>
        ) : (
          stage && (
            <div key={`${step}-${fam}`} className="bf-stage" style={{ transformOrigin: origin }}>
              <p className="mb-1 text-xs text-text-muted">
                {level === 1
                  ? `Grouped by ${groupByCountry ? 'country' : 'region'}. Click a name to split it by state or country; click a dot to read the bill.`
                  : 'Click a name to list just that place below; click a dot to read the bill.'}
              </p>
              <svg viewBox={`0 0 ${stage.w} ${stage.h}`} style={{ width: '100%', height: 'auto', display: 'block' }} role="img"
                aria-label={`${stepName}: bills grouped by place`}>
                {stage.groups.map(g => {
                  const sorted = [...g.bills].sort((a, b) => ORDER[sgroup(a)] - ORDER[sgroup(b)]);
                  const d = dot * g.c / (level === 1 ? 7.2 : 9.4);
                  const selected = level === 2 && jur === g.key;
                  const dim = level === 2 && !!jur && !selected;
                  let k = 0;
                  const drill = () => {
                    if (level === 1) { setOrigin(`${(g.cx / stage.w) * 100}% ${(g.cy / stage.h) * 100}%`); setFam(g.key); setJur(null); }
                    else setJur(jur === g.key ? null : g.key);
                    setShown(30);
                  };
                  return (
                    <g key={g.key} style={{ opacity: dim ? 0.28 : 1, transition: 'opacity .2s' }}>
                      <circle cx={g.cx} cy={g.cy} r={g.rad} fill="var(--bg-primary)" stroke={selected ? '#f2b84b' : 'var(--border-default)'}
                        strokeWidth={selected ? 3 : 1} onClick={drill} style={{ cursor: 'pointer' }} />
                      <g role="button" tabIndex={0} onClick={drill} style={{ cursor: 'pointer' }}
                        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); drill(); } }}>
                        <text x={g.cx} y={g.cy - g.rad - 22} textAnchor="middle"
                          style={{ fontSize: width < 640 ? 13 : 15, fontWeight: 700, fill: level === 1 ? 'rgb(var(--green-accent))' : 'var(--text-primary)' }}>
                          {g.label}{level === 1 ? ' ›' : ''}
                        </text>
                        <text x={g.cx} y={g.cy - g.rad - 6} textAnchor="middle" style={{ fontSize: width < 640 ? 11.5 : 13, fill: 'var(--text-muted)', fontFamily: 'var(--font-mono), monospace' }}>
                          {g.bills.length.toLocaleString()} · {g.bills.filter(b => sgroup(b) === 'enacted').length.toLocaleString()} in force
                        </text>
                      </g>
                      {sorted.map((b, i) => {
                        const [x, y] = phyllo(g, i);
                        const hit = !filtering || ok.has(b.id);
                        let tx = x, ty = y, scale = 1;
                        if (filtering && hit) [tx, ty] = phyllo(g, k++);
                        else if (!hit) {
                          const a = Math.atan2(y - g.cy, x - g.cx) || i * GOLD;
                          tx = g.cx + (g.rad - 4) * Math.cos(a); ty = g.cy + (g.rad - 4) * Math.sin(a); scale = 0.55;
                        }
                        const sg = sgroup(b), col = dotColor(b);
                        return (
                          <g key={b.id} className={`bf-dw${hit ? '' : ' fade'}`}
                            style={{ transform: tx === x && ty === y && scale === 1 ? undefined : `translate(${tx - x}px, ${ty - y}px) scale(${scale})`,
                              transitionDelay: `${Math.min(i * 0.8, 260)}ms` }}>
                            <circle
                              className="bf-dot"
                              cx={x} cy={y}
                              r={sg === 'enacted' ? d : sg === 'pending' ? d * 0.88 : d * 0.82}
                              fill={sg === 'enacted' ? col : sg === 'pending' ? 'var(--bg-secondary)' : '#c3c8cf'}
                              stroke={sg === 'pending' ? col : undefined}
                              strokeWidth={sg === 'pending' ? d * 0.4 : undefined}
                              style={{ ['--dx' as string]: `${g.cx - x}px`, ['--dy' as string]: `${g.cy - y}px`, animationDelay: `${Math.min(i * 1.4, 420)}ms` }}
                              onClick={() => { setOpen(b); track('butterfly_bill_open', { step: step ?? '' }); }}
                            >
                              <title>{`${b.bill_number ?? ''} · ${b.region === 'US' ? `US · ${b.state}` : regionLabel(b.region)}\n${b.title ?? ''}`}</title>
                            </circle>
                          </g>
                        );
                      })}
                    </g>
                  );
                })}
              </svg>
            </div>
          )
        )}
      </div>

      {level === 0 && <ButterflyUnplaced counts={counts} onOpen={openStep} />}

      {level > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <span className="flex items-center gap-1.5"><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="var(--text-secondary)" /></svg>In force</span>
            <span className="flex items-center gap-1.5"><svg width="12" height="12"><circle cx="6" cy="6" r="4.2" fill="none" stroke="var(--text-secondary)" strokeWidth="1.6" /></svg>Pending</span>
            <span className="flex items-center gap-1.5"><svg width="12" height="12"><circle cx="6" cy="6" r="4" fill="#c3c8cf" /></svg>Failed or repealed</span>
          </div>
          <h3 className="font-serif text-lg text-text-primary">
            {[stepName, fam && l1.label(fam), jur && jurName(jur)].filter(Boolean).join(' · ')}
            <span className="ml-2 font-sans text-sm text-text-muted">{listed.length.toLocaleString()} of {focus.length.toLocaleString()}</span>
          </h3>
          <ul className="divide-y divide-border-default rounded-lg border border-border-default">
            {listed.slice(0, shown).map(b => (
              <li key={b.id}>
                <button type="button" onClick={() => setOpen(b)} className="flex w-full items-start gap-3 px-3 py-2 text-left hover:bg-bg-tertiary">
                  <span className="w-28 shrink-0 font-mono text-xs text-text-muted">{b.region === 'US' ? `US · ${b.state}` : regionLabel(b.region)}</span>
                  <span className="min-w-0 flex-1 text-sm text-text-primary">
                    {b.title}
                    <span className="block font-mono text-xs text-text-muted">{b.bill_number} · {STATUS_LABEL[sgroup(b)]}</span>
                  </span>
                </button>
              </li>
            ))}
            {!listed.length && <li className="px-3 py-4 text-center text-sm text-text-muted">No bills match. Clear the search or pick another status.</li>}
          </ul>
          {listed.length > shown && (
            <button type="button" onClick={() => setShown(s => s + 30)} className="mx-auto block rounded-md border border-border-default px-4 py-1.5 text-sm text-text-secondary hover:text-text-primary">
              Show {Math.min(30, listed.length - shown)} more of {(listed.length - shown).toLocaleString()}
            </button>
          )}
        </div>
      )}

      <BillModal bill={open} onClose={() => setOpen(null)} />
    </div>
  );
}
