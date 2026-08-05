'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { geoOrthographic, geoPath, geoContains, geoGraticule10, geoCentroid } from 'd3-geo';
import { feature } from 'topojson-client';
import { useTheme } from '@/components/layout/ThemeContext';
import { EU_MEMBER_IDS, codeForIso } from '@/components/map/RegionInsetMap';
import { regionLabel } from '@/components/insights/RegionFilter';
import { fetchLawsInForce } from '@/lib/api';
import { track } from '@/lib/analytics';

/**
 * A slowly-rotating orthographic globe of circular-economy laws in force, by jurisdiction — the
 * homepage's cross-region overview (replaces the flat coverage readout). Pure d3-geo drawn to a
 * <canvas> (no Mapbox / WebGL): geoOrthographic + geoPath, animated by advancing the projection's
 * rotation each frame. Shares WorldCoverageMap's data + ISO plumbing so a country is shaded by the
 * enacted CE laws that apply there (its national laws + the EU-central body for EU members).
 *
 * Interaction: drag to spin, hover to read a jurisdiction (auto-rotation pauses), click a tracked
 * country to filter the whole site to its region. Honors prefers-reduced-motion (no auto-spin).
 */

const GEO_URL = '/world-countries-50m.json';
const ANTARCTICA = '010';
const US_ISO = '840';

// Module cache so the 50m topojson is fetched + parsed once and shared across mounts.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let TOPO_CACHE: any = null;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let TOPO_PROMISE: Promise<any> | null = null;
function loadTopo() {
  if (TOPO_CACHE) return Promise.resolve(TOPO_CACHE);
  if (!TOPO_PROMISE) TOPO_PROMISE = fetch(GEO_URL).then(r => r.json()).then(d => (TOPO_CACHE = d));
  return TOPO_PROMISE;
}

/** Region code a country belongs to for click-through: its national code, else EU for members, else US. */
function regionCodeForCountry(id: string): string | undefined {
  const nat = codeForIso(id);
  if (nat) return nat;
  if (id === US_ISO) return 'US';
  if (EU_MEMBER_IDS.includes(id)) return 'EU';
  return undefined;
}

// 320px, not the taller hero it started as: the globe is the overview, and the bill table below it is
// what visitors came for — keeping it short leaves the top of the table above the fold.
export function CoverageGlobe({ onSelect, height = 320 }: { onSelect: (region: string) => void; height?: number }) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [topo, setTopo] = useState<any>(TOPO_CACHE);
  const [counts, setCounts] = useState<Map<string, number> | null>(null);
  const [hover, setHover] = useState<{ region: string; count: number } | null>(null);
  const [width, setWidth] = useState(0);

  // Mutable render state that must survive effect re-runs (resize/theme) without resetting the spin.
  const rotationRef = useRef<[number, number]>([-12, -18]);
  const zoomRef = useRef(1);
  const draggingRef = useRef(false);
  const overGlobeRef = useRef(false);
  const hoverIdRef = useRef<string | null>(null);
  // An in-flight "fly to" zoom; onDone hands off to the page's detailed map after the animation.
  const flyRef = useRef<null | {
    start: number; dur: number;
    fromRot: [number, number]; toRot: [number, number];
    fromZoom: number; toZoom: number; onDone: () => void;
  }>(null);
  // Keep onSelect current without churning the render effect (inline arrow → new identity each render).
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (topo) return;
    let alive = true;
    loadTopo().then(d => { if (alive) setTopo(d); }).catch(() => {});
    return () => { alive = false; };
  }, [topo]);

  useEffect(() => {
    let cancelled = false;
    fetchLawsInForce() // no region filter → every region grouped
      .then(pts => {
        if (cancelled) return;
        const m = new Map<string, number>();
        for (const p of pts) m.set(p.region, (m.get(p.region) ?? 0) + p.count);
        setCounts(m);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Track the container width so the canvas is responsive (globe is centered, sized to the height).
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const ro = new ResizeObserver(entries => { for (const e of entries) setWidth(e.contentRect.width); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Drawn features + the "laws that apply here" count fn + max, shared with the shading ramp.
  const { features, countForCountry, max, totals } = useMemo(() => {
    if (!topo || !counts) {
      return { features: [] as unknown[], countForCountry: (_: string) => 0, max: 0, totals: { jur: 0, laws: 0 } };
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const fc: any = feature(topo, topo.objects.countries);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const drawn = fc.features.filter((f: any) => String(f.id) !== ANTARCTICA);
    const euCount = counts.get('EU') ?? 0;
    // National + subnational: laws-in-force groups by the national region code (a US state law is
    // region="US", an Ontario reg is region="CA"), so counts.get(code) already rolls sub-national
    // units in. We also add any namespaced sub-national region keys (CODE-*) defensively, in case a
    // jurisdiction ever lands its provinces under a region rather than the state column.
    const subOf = (code: string): number => {
      let s = 0;
      for (const [k, v] of counts) if (k.startsWith(`${code}-`)) s += v;
      return s;
    };
    const cf = (id: string): number => {
      const natCode = id === US_ISO ? 'US' : codeForIso(id);
      const nat = natCode ? (counts.get(natCode) ?? 0) + subOf(natCode) : 0;
      const euBase = EU_MEMBER_IDS.includes(id) ? euCount : 0;
      return nat + euBase;
    };
    let mx = 0;
    for (const f of drawn) mx = Math.max(mx, cf(String(f.id)));
    const tracked = new Set<string>();
    for (const [region, n] of counts) if (n > 0) tracked.add(region);
    const laws = [...counts.values()].reduce((s, n) => s + n, 0);
    return { features: drawn as unknown[], countForCountry: cf, max: mx, totals: { jur: tracked.size, laws } };
  }, [topo, counts]);

  // The render + animation + interaction loop. Re-runs on size/theme/data change; rotation persists
  // via rotationRef so those re-runs don't jump the globe.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !width || features.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = width;
    const H = height;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    ctx.scale(dpr, dpr);

    const radius = Math.min(W, H) / 2 - 10;
    const cx = W / 2;
    const cy = H / 2;
    const projection = geoOrthographic().scale(radius).translate([cx, cy]).clipAngle(90);
    const path = geoPath(projection, ctx);

    // Colors: accent from the brand token (matches the Insights map); ocean/land tuned per theme.
    const cs = getComputedStyle(document.documentElement);
    const accentTriple = cs.getPropertyValue('--green-accent').trim() || (isDark ? '243 188 195' : '30 106 233');
    const accent = `rgb(${accentTriple})`;
    const ocean = isDark ? '#0b1220' : '#e9eef3';
    const stroke = isDark ? '#0b1220' : '#cdd6e0';
    const land = isDark ? '#273241' : '#e2e8f0';
    // Depth: activity drives accent OPACITY over the land base — bare land at 0, full accent at the
    // max — so more laws read as deeper colour and the busiest country never washes out to white.
    const depth = (n: number): number => (n <= 0 || max <= 0) ? 0 : 0.16 + 0.84 * Math.sqrt(n / max);

    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let dirty = true;
    const withinDisc = (px: number, py: number) => {
      const dx = px - cx, dy = py - cy;
      return dx * dx + dy * dy <= radius * radius;
    };
    const idAt = (clientX: number, clientY: number): string | null => {
      const rect = canvas.getBoundingClientRect();
      const px = clientX - rect.left, py = clientY - rect.top;
      if (!withinDisc(px, py)) return null;
      projection.rotate(rotationRef.current);
      const inv = projection.invert?.([px, py]);
      if (!inv) return null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      for (const f of features as any[]) if (geoContains(f, inv)) return String(f.id);
      return null;
    };

    function draw() {
      if (!ctx) return;
      projection.rotate(rotationRef.current);
      projection.scale(radius * zoomRef.current);
      ctx.clearRect(0, 0, W, H);

      // Ocean sphere.
      ctx.beginPath();
      path({ type: 'Sphere' });
      ctx.fillStyle = ocean;
      ctx.fill();

      // Graticule — faint lat/long grid to read as a globe.
      ctx.beginPath();
      path(geoGraticule10());
      ctx.globalAlpha = isDark ? 0.16 : 0.5;
      ctx.lineWidth = 0.4;
      ctx.strokeStyle = stroke;
      ctx.stroke();
      ctx.globalAlpha = 1;

      // Countries: land base, then accent at activity-driven opacity (full on hover).
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      for (const f of features as any[]) {
        const id = String(f.id);
        const n = countForCountry(id);
        ctx.beginPath();
        path(f);
        ctx.fillStyle = land;
        ctx.fill();
        const a = hoverIdRef.current === id && n > 0 ? 1 : depth(n);
        if (a > 0) {
          ctx.globalAlpha = a;
          ctx.fillStyle = accent;
          ctx.fill();
          ctx.globalAlpha = 1;
        }
        ctx.lineWidth = 0.4;
        ctx.globalAlpha = 0.55;
        ctx.strokeStyle = stroke;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }

      // Atmosphere rim.
      ctx.beginPath();
      path({ type: 'Sphere' });
      ctx.globalAlpha = 0.18;
      ctx.lineWidth = 2;
      ctx.strokeStyle = accent;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    // Hover hit-testing is throttled to once per frame (geoContains over ~200 features is not free).
    let probe: { x: number; y: number } | null = null;
    let raf = 0;
    let lastT = 0;
    function frame(t: number) {
      const dt = lastT ? t - lastT : 16;
      lastT = t;

      // A fly-to zoom takes precedence over spin + hover — ease rotation to the target + scale up,
      // then hand off to the page's detailed map.
      if (flyRef.current) {
        const f = flyRef.current;
        if (f.start < 0) f.start = t;
        const p = Math.min(1, (t - f.start) / f.dur);
        const e = 1 - Math.pow(1 - p, 3); // easeOutCubic
        rotationRef.current = [
          f.fromRot[0] + (f.toRot[0] - f.fromRot[0]) * e,
          f.fromRot[1] + (f.toRot[1] - f.fromRot[1]) * e,
        ];
        zoomRef.current = f.fromZoom + (f.toZoom - f.fromZoom) * e;
        draw();
        if (p >= 1) { const done = f.onDone; flyRef.current = null; done(); }
        raf = requestAnimationFrame(frame);
        return;
      }

      if (probe) {
        const { x, y } = probe;
        probe = null;
        overGlobeRef.current = withinDisc(x - canvas!.getBoundingClientRect().left, y - canvas!.getBoundingClientRect().top);
        const id = idAt(x, y);
        if (id !== hoverIdRef.current) {
          hoverIdRef.current = id;
          dirty = true;
          const n = id ? countForCountry(id) : 0;
          const region = id ? regionCodeForCountry(id) : undefined;
          setHover(id && region && n > 0 ? { region, count: n } : null);
          canvas!.style.cursor = id && region && n > 0 ? 'pointer' : 'grab';
        }
      }

      const spinning = !draggingRef.current && !overGlobeRef.current && !prefersReduced;
      if (spinning) {
        rotationRef.current = [rotationRef.current[0] + 0.0055 * dt, rotationRef.current[1]];
        draw();
      } else if (dirty) {
        draw();
        dirty = false;
      }
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    // --- Pointer interaction: drag to spin, click (no drag) to filter. ---
    let dragStart: { x: number; y: number; rot: [number, number] } | null = null;
    let moved = false;

    const onDown = (e: PointerEvent) => {
      canvas.setPointerCapture(e.pointerId);
      dragStart = { x: e.clientX, y: e.clientY, rot: [...rotationRef.current] as [number, number] };
      moved = false;
      draggingRef.current = true;
      canvas.style.cursor = 'grabbing';
    };
    const onMove = (e: PointerEvent) => {
      if (dragStart) {
        const dx = e.clientX - dragStart.x, dy = e.clientY - dragStart.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
        const k = 0.28; // degrees per pixel
        const phi = Math.max(-90, Math.min(90, dragStart.rot[1] - dy * k));
        rotationRef.current = [dragStart.rot[0] + dx * k, phi];
        dirty = true;
      } else {
        probe = { x: e.clientX, y: e.clientY };
      }
    };
    const onUp = (e: PointerEvent) => {
      const wasClick = dragStart != null && !moved;
      dragStart = null;
      draggingRef.current = false;
      canvas.style.cursor = hoverIdRef.current ? 'pointer' : 'grab';
      if (wasClick && !flyRef.current) {
        const id = idAt(e.clientX, e.clientY);
        const region = id ? regionCodeForCountry(id) : undefined;
        const n = id ? countForCountry(id) : 0;
        if (id && region && n > 0) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const f = (features as any[]).find(ff => String(ff.id) === id);
          const [lon, lat] = f ? geoCentroid(f) : [0, 0];
          // Target rotation centers the country; unwrap longitude so the spin takes the short way.
          let toLon = -lon;
          const cur = rotationRef.current[0];
          while (toLon - cur > 180) toLon -= 360;
          while (toLon - cur < -180) toLon += 360;
          hoverIdRef.current = null;
          setHover(null);
          flyRef.current = {
            start: -1,
            dur: 850,
            fromRot: [...rotationRef.current] as [number, number],
            toRot: [toLon, -lat],
            fromZoom: zoomRef.current,
            toZoom: 2.4,
            onDone: () => { track('home_globe_select', { region }); onSelectRef.current(region); },
          };
        }
      }
    };
    const onLeave = () => {
      overGlobeRef.current = false;
      if (hoverIdRef.current !== null) { hoverIdRef.current = null; setHover(null); dirty = true; }
      canvas.style.cursor = 'grab';
    };

    canvas.style.cursor = 'grab';
    canvas.addEventListener('pointerdown', onDown);
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('pointerup', onUp);
    canvas.addEventListener('pointerleave', onLeave);

    return () => {
      cancelAnimationFrame(raf);
      canvas.removeEventListener('pointerdown', onDown);
      canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerup', onUp);
      canvas.removeEventListener('pointerleave', onLeave);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [features, countForCountry, max, isDark, width, height]);

  const loading = !topo || !counts;

  return (
    <div
      ref={wrapRef}
      className="relative w-full overflow-hidden rounded-lg border border-border-default"
      style={{ height, background: isDark ? '#0b1220' : '#e9eef3' }}
    >
      <canvas ref={canvasRef} className="block" style={{ touchAction: 'none' }} />

      {loading && (
        <div className="absolute inset-0 grid place-items-center">
          <div className="h-40 w-40 animate-pulse rounded-full bg-bg-tertiary" />
        </div>
      )}

      {/* Hover / prompt readout, pinned so the canvas never reflows. */}
      <div className="pointer-events-none absolute left-3 top-3 rounded-md bg-bg-primary/85 px-2.5 py-1.5 text-xs shadow-sm backdrop-blur-sm">
        {hover ? (
          <span className="text-text-primary">
            <span className="font-semibold">{regionLabel(hover.region)}</span>
            {' · '}{hover.count.toLocaleString()} law{hover.count === 1 ? '' : 's'} in force
          </span>
        ) : (
          <span className="text-text-muted">Drag to spin · click a country to explore</span>
        )}
      </div>

      {/* Totals + legend, bottom strip. */}
      {!loading && (
        <div className="pointer-events-none absolute inset-x-3 bottom-3 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="flex items-center gap-2 rounded-md bg-bg-primary/85 px-2.5 py-1.5 text-text-muted shadow-sm backdrop-blur-sm">
            <span>Fewer</span>
            <span
              className="h-2 w-16 rounded-full"
              style={{
                background: `linear-gradient(to right,
                  color-mix(in srgb, rgb(var(--green-accent)), transparent 85%),
                  rgb(var(--green-accent)))`,
              }}
            />
            <span>More laws</span>
          </span>
          <span className="rounded-md bg-bg-primary/85 px-2.5 py-1.5 text-text-secondary shadow-sm backdrop-blur-sm">
            <span className="font-semibold text-text-primary">{totals.jur}</span> jurisdictions ·{' '}
            <span className="font-semibold text-text-primary">{totals.laws.toLocaleString()}</span> laws in force
          </span>
        </div>
      )}
    </div>
  );
}
