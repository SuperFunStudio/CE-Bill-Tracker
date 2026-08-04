'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useBills } from '@/hooks/useBills';
import { formatInstrumentType } from '@/lib/utils';
import { regionLabel } from '@/components/insights/RegionFilter';
import { track } from '@/lib/analytics';

/**
 * Bill-flow Sankey for Insights: how the corpus flows between two dimensions. Two flows —
 * Material → Instrument (which levers regulate each material) and Region → Material (what each
 * jurisdiction legislates). A bill can carry several materials, so it splits across each; link weights
 * are therefore bill × material coverage, called out inline. Built from scratch (compact layout, no d3)
 * into a ref, product-themed via the status/accent tokens so light and dark are handled by the tokens.
 */
type FlowId = 'mat-instr' | 'reg-mat';
const FLOWS: { id: FlowId; src: 'material' | 'region'; tgt: 'instrument' | 'material'; colL: string; colR: string; label: string }[] = [
  { id: 'mat-instr', src: 'material', tgt: 'instrument', colL: 'Material', colR: 'Instrument', label: 'Material → Instrument' },
  { id: 'reg-mat', src: 'region', tgt: 'material', colL: 'Jurisdiction', colR: 'Material', label: 'Region → Material' },
];

const SEP = '';
const titleizeMaterial = (m: string) => m.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
const esc = (s: string) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const nodeName = (kind: string, key: string) =>
  key === '—' ? 'Unspecified' : kind === 'region' ? regionLabel(key) : kind === 'instrument' ? formatInstrumentType(key) : titleizeMaterial(key);

export function BillFlowSankey() {
  const { data: bills = [], isLoading } = useBills({ ce_relevant: true, limit: 5000, regions: 'all' });
  const [flow, setFlow] = useState<FlowId>('mat-instr');
  const wrapRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(900);

  // Track the container width so the diagram fills its card (min 760, scrolls on narrow screens).
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(760, el.clientWidth || 900));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [isLoading]);

  const v = FLOWS.find((f) => f.id === flow)!;

  const svg = useMemo(() => {
    if (!bills.length) return '';
    // aggregate links (respecting the multi-material split)
    const links = new Map<string, number>();
    const sV = new Map<string, number>();
    const tV = new Map<string, number>();
    const add = (s: string, t: string) => {
      const k = s + SEP + t;
      links.set(k, (links.get(k) ?? 0) + 1);
      sV.set(s, (sV.get(s) ?? 0) + 1);
      tV.set(t, (tV.get(t) ?? 0) + 1);
    };
    for (const b of bills) {
      const mats = (b.material_categories ?? []).filter(Boolean);
      const M = mats.length ? mats : ['—'];
      if (v.src === 'material') M.forEach((m) => add(m, b.instrument_type || 'other'));
      else M.forEach((m) => add(b.region || '—', m));
    }
    if (!links.size) return '';
    // keep top 12 per side, fold the rest into "Other"
    const top = (m: Map<string, number>, n: number) => new Set([...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map((e) => e[0]));
    const keepS = top(sV, 12), keepT = top(tV, 12);
    const L = new Map<string, number>(), SV = new Map<string, number>(), TV = new Map<string, number>();
    for (const [k, c] of links) {
      let [s, t] = k.split(SEP);
      if (!keepS.has(s)) s = 'Other';
      if (!keepT.has(t)) t = 'Other';
      const kk = s + SEP + t;
      L.set(kk, (L.get(kk) ?? 0) + c);
      SV.set(s, (SV.get(s) ?? 0) + c);
      TV.set(t, (TV.get(t) ?? 0) + c);
    }
    const ord = (m: Map<string, number>) => [...m.entries()].sort((a, b) => (Number(a[0] === 'Other') - Number(b[0] === 'Other')) || b[1] - a[1]);
    const srcNodes = ord(SV), tgtNodes = ord(TV);
    // layout
    const W = width, padX = 176, nodeW = 13, top0 = 40, bot = 14;
    const H = Math.max(440, Math.min(760, Math.max(srcNodes.length, tgtNodes.length) * 52));
    const availH = H - top0 - bot, GAP = 11, T = [...L.values()].reduce((a, x) => a + x, 0);
    const ky = Math.min((availH - GAP * (srcNodes.length - 1)) / T, (availH - GAP * (tgtNodes.length - 1)) / T);
    type N = { name: string; val: number; x: number; y: number; h: number; cur: number };
    const S = new Map<string, N>();
    let y = top0;
    for (const [name, val] of srcNodes) { const h = val * ky; S.set(name, { name, val, x: padX, y, h, cur: y }); y += h + GAP; }
    const Tn = new Map<string, N>();
    y = top0;
    for (const [name, val] of tgtNodes) { const h = val * ky; Tn.set(name, { name, val, x: W - padX - nodeW, y, h, cur: y }); y += h + GAP; }
    let ribbons = '';
    for (const [sname] of srcNodes) {
      for (const [tname] of tgtNodes) {
        const c = L.get(sname + SEP + tname);
        if (!c) continue;
        const s = S.get(sname)!, t = Tn.get(tname)!, th = c * ky;
        const sy = s.cur; s.cur += th; const ty = t.cur; t.cur += th;
        const x0 = s.x + nodeW, x1 = t.x, xm = ((x0 + x1) / 2).toFixed(1);
        const d = `M${x0},${sy.toFixed(1)} C${xm},${sy.toFixed(1)} ${xm},${ty.toFixed(1)} ${x1},${ty.toFixed(1)} L${x1},${(ty + th).toFixed(1)} C${xm},${(ty + th).toFixed(1)} ${xm},${(sy + th).toFixed(1)} ${x0},${(sy + th).toFixed(1)} Z`;
        ribbons += `<path class="bfs-link" data-s="${esc(sname)}" data-t="${esc(tname)}" data-c="${c}" data-sl="${esc(nodeName(v.src, sname))}" data-tl="${esc(nodeName(v.tgt, tname))}" d="${d}"/>`;
      }
    }
    const nodeSvg = (n: N, side: 'src' | 'tgt') => {
      const nm = nodeName(side === 'src' ? v.src : v.tgt, n.name);
      const lx = side === 'src' ? n.x - 9 : n.x + nodeW + 9, anchor = side === 'src' ? 'end' : 'start', cy = n.y + n.h / 2;
      return `<g class="bfs-node ${side}" data-side="${side}" data-name="${esc(n.name)}"><rect x="${n.x}" y="${n.y.toFixed(1)}" width="${nodeW}" height="${Math.max(1.5, n.h).toFixed(1)}" rx="2"/><text class="bfs-name" x="${lx}" y="${(cy + 4).toFixed(1)}" text-anchor="${anchor}">${esc(nm)} <tspan class="v">${n.val}</tspan></text></g>`;
    };
    let out = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(v.colL)} to ${esc(v.colR)} flow"><text class="bfs-col" x="${padX}" y="20" text-anchor="end">${v.colL}</text><text class="bfs-col" x="${W - padX - nodeW}" y="20">${v.colR}</text>${ribbons}`;
    for (const [name] of srcNodes) out += nodeSvg(S.get(name)!, 'src');
    for (const [name] of tgtNodes) out += nodeSvg(Tn.get(name)!, 'tgt');
    return out + '</svg>';
  }, [bills, v, width]);

  useEffect(() => {
    if (wrapRef.current) wrapRef.current.innerHTML = svg;
  }, [svg]);

  const onMove = (e: React.MouseEvent) => {
    const wrap = wrapRef.current, tip = tipRef.current, svgEl = wrap?.querySelector('svg');
    if (!wrap || !tip || !svgEl) return;
    const target = e.target as HTMLElement;
    const link = target.closest?.('.bfs-link') as HTMLElement | null;
    const node = target.closest?.('.bfs-node') as HTMLElement | null;
    wrap.querySelectorAll('.hot').forEach((x) => x.classList.remove('hot'));
    if (link) {
      wrap.classList.add('dim'); link.classList.add('hot');
      tip.innerHTML = `<div class="n">${esc(link.dataset.sl || '')} → ${esc(link.dataset.tl || '')}</div><div class="t">${Number(link.dataset.c).toLocaleString()} bills</div>`;
      tip.classList.add('on');
      const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
      let x = e.clientX + 16, ty = e.clientY + 16;
      if (x + w + pad > window.innerWidth) x = e.clientX - w - 16;
      if (ty + h + pad > window.innerHeight) ty = e.clientY - h - 16;
      tip.style.left = Math.max(pad, x) + 'px'; tip.style.top = Math.max(pad, ty) + 'px';
    } else if (node) {
      wrap.classList.add('dim'); node.classList.add('hot');
      const key = node.dataset.side === 'src' ? 's' : 't', name = node.dataset.name;
      svgEl.querySelectorAll<HTMLElement>('.bfs-link').forEach((p) => { if (p.dataset[key] === name) p.classList.add('hot'); });
      tip.classList.remove('on');
    } else {
      wrap.classList.remove('dim'); tip.classList.remove('on');
    }
  };
  const onLeave = () => {
    const wrap = wrapRef.current;
    wrap?.classList.remove('dim');
    wrap?.querySelectorAll('.hot').forEach((x) => x.classList.remove('hot'));
    tipRef.current?.classList.remove('on');
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-border-default bg-bg-primary p-0.5">
          {FLOWS.map((f) => (
            <button
              key={f.id}
              onClick={() => { setFlow(f.id); track('insights_sankey_flow', { flow: f.id }); }}
              aria-pressed={flow === f.id}
              className={`px-3.5 py-1.5 text-sm rounded-md transition-colors ${
                flow === f.id ? 'bg-green-accent text-bg-primary font-medium' : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-text-muted max-w-md">
          A bill can span several materials, so it flows from each — link weights are bill × material coverage. Hover a ribbon or node.
        </p>
      </div>

      {isLoading ? (
        <div className="h-[460px] animate-pulse rounded-lg bg-bg-tertiary" />
      ) : (
        <div ref={wrapRef} className="bfs-wrap" onMouseMove={onMove} onMouseLeave={onLeave} />
      )}
      <div ref={tipRef} className="bde-tip" role="tooltip" />
    </div>
  );
}
