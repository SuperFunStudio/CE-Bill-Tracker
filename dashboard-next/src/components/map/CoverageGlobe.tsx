'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { geoOrthographic, geoPath, geoContains, geoGraticule10, geoCentroid } from 'd3-geo';
import { feature } from 'topojson-client';
import { useTheme } from '@/components/layout/ThemeContext';
import { EU_MEMBER_IDS, codeForIso } from '@/components/map/RegionInsetMap';
import { regionLabel, REGION_CODES } from '@/components/insights/RegionFilter';
import { MapLegend } from '@/components/map/MapLegend';
import { fetchLawsInForce } from '@/lib/api';
import { track } from '@/lib/analytics';
import { MAP_METRIC, fillFor, fmtCount, mapPalette } from '@/lib/mapScale';
import { useTapOrClick } from '@/hooks/useTapOrClick';

/**
 * An orthographic globe of circular-economy laws in force, by jurisdiction — the homepage's
 * cross-region overview. Pure d3-geo drawn to a <canvas> (no Mapbox / WebGL). A country is shaded by
 * the enacted CE laws that apply there (its national laws + the EU-central body for EU members),
 * through the site-wide scale in lib/mapScale — the same bins the US state map uses.
 *
 * Opens centred on the North Atlantic so the US and Europe — most of the corpus — are both readable on
 * load, and holds still: it used to auto-spin, which carried both off-screen within seconds. Drag to
 * spin, hover to read a jurisdiction, click/tap a tracked country to filter the page to it.
 *
 * Colour = more enacted laws, only. Hover, selection and the row-hover preview (`highlightIds`) are an
 * ink outline, never a fill change.
 */

const GEO_URL = '/world-countries-50m.json';
const ANTARCTICA = '010';
const US_ISO = '840';
const FRANCE_ISO = '250';
// rotate([λ, φ]) centres the view on (-λ, -φ): 38°W, 34°N puts the Atlantic in the middle with the
// eastern US and western Europe both well inside the visible hemisphere.
const START_ROTATION: [number, number] = [38, -34];
// Slightly past "whole disc": the poles carry no data, and the extra scale gives Europe room to read.
const BASE_ZOOM = 1.15;

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

const TRACKED_CODES = new Set(REGION_CODES);

/** Region code a country belongs to for click-through: its national code, else EU for members, else US. */
function regionCodeForCountry(id: string): string | undefined {
  const nat = codeForIso(id);
  if (nat && TRACKED_CODES.has(nat)) return nat;
  if (id === US_ISO) return 'US';
  if (EU_MEMBER_IDS.includes(id)) return 'EU';
  return undefined;
}

type Hover = { region: string; count: number; note?: string };

export function CoverageGlobe({
  onSelect, height = 320, highlightIds,
}: {
  onSelect: (region: string) => void;
  height?: number;
  /** ISO numeric ids to outline from outside — the jurisdiction of the table row under the pointer. */
  highlightIds?: string[];
}) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const palette = useMemo(() => mapPalette(isDark), [isDark]);
  const verb = useTapOrClick();

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [topo, setTopo] = useState<any>(TOPO_CACHE);
  const [counts, setCounts] = useState<Map<string, number> | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const [width, setWidth] = useState(0);

  // Mutable render state that must survive effect re-runs (resize/theme) without resetting the view.
  const rotationRef = useRef<[number, number]>([...START_ROTATION]);
  const zoomRef = useRef(BASE_ZOOM);
  const draggingRef = useRef(false);
  const hoverIdRef = useRef<string | null>(null);
  const highlightRef = useRef<Set<string>>(new Set());
  const dirtyRef = useRef(true);
  // An in-flight "fly to" zoom; onDone hands off to the page's detailed map after the animation.
  const flyRef = useRef<null | {
    start: number; dur: number;
    fromRot: [number, number]; toRot: [number, number];
    fromZoom: number; toZoom: number; onDone: () => void;
  }>(null);
  // Keep onSelect current without churning the render effect (inline arrow → new identity each render).
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Row-hover preview from the table: outline only, redraw on the next frame.
  useEffect(() => {
    highlightRef.current = new Set(highlightIds ?? []);
    dirtyRef.current = true;
  }, [highlightIds]);

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

  // Drawn features + the "laws that apply here" count fn, plus which countries we track at all.
  const { features, countForCountry, isTracked, totals } = useMemo(() => {
    if (!topo || !counts) {
      return {
        features: [] as unknown[], countForCountry: (_: string) => 0, isTracked: (_: string) => false,
        totals: { jur: 0, laws: 0 },
      };
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const fc: any = feature(topo, topo.objects.countries);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const drawn = fc.features.filter((f: any) => String(f.id) !== ANTARCTICA);
    const euCount = counts.get('EU') ?? 0;
    // National + subnational: laws-in-force groups by the national region code (a US state law is
    // region="US", an Ontario reg is region="CA"), so counts.get(code) already rolls sub-national
    // units in. We also add any namespaced sub-national region keys (CODE-*) defensively.
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
    const tracked = (id: string) => regionCodeForCountry(id) !== undefined || cf(id) > 0;
    const jur = new Set<string>();
    for (const [region, n] of counts) if (n > 0) jur.add(region);
    const laws = [...counts.values()].reduce((s, n) => s + n, 0);
    return { features: drawn as unknown[], countForCountry: cf, isTracked: tracked, totals: { jur: jur.size, laws } };
  }, [topo, counts]);

  // The render + interaction loop. Re-runs on size/theme/data change; rotation persists via
  // rotationRef so those re-runs don't jump the globe.
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

    // Hatch for "not tracked": a tiny diagonal tile, repeated. Distinct from every data bin by texture,
    // not just by lightness, so it survives colour-vision differences and dark mode.
    const tile = document.createElement('canvas');
    tile.width = tile.height = 6 * dpr;
    const tctx = tile.getContext('2d')!;
    tctx.scale(dpr, dpr);
    tctx.fillStyle = palette.land;
    tctx.fillRect(0, 0, 6, 6);
    tctx.strokeStyle = palette.hatch;
    tctx.lineWidth = 1;
    tctx.beginPath();
    tctx.moveTo(0, 6); tctx.lineTo(6, 0);
    tctx.moveTo(-1, 1); tctx.lineTo(1, -1);
    tctx.moveTo(5, 7); tctx.lineTo(7, 5);
    tctx.stroke();
    const hatch = ctx.createPattern(tile, 'repeat');
    hatch?.setTransform?.(new DOMMatrix().scale(1 / dpr));

    const withinDisc = (px: number, py: number) => {
      const dx = px - cx, dy = py - cy;
      return dx * dx + dy * dy <= radius * zoomRef.current * radius * zoomRef.current;
    };
    const hitAt = (clientX: number, clientY: number): { id: string; lonLat: [number, number] } | null => {
      const rect = canvas.getBoundingClientRect();
      const px = clientX - rect.left, py = clientY - rect.top;
      if (!withinDisc(px, py)) return null;
      projection.rotate(rotationRef.current);
      const inv = projection.invert?.([px, py]);
      if (!inv) return null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      for (const f of features as any[]) if (geoContains(f, inv)) return { id: String(f.id), lonLat: inv as [number, number] };
      return null;
    };

    function draw() {
      if (!ctx) return;
      projection.rotate(rotationRef.current);
      projection.scale(radius * zoomRef.current);
      ctx.clearRect(0, 0, W, H);

      ctx.beginPath();
      path({ type: 'Sphere' });
      ctx.fillStyle = palette.ocean;
      ctx.fill();

      // Graticule — faint lat/long grid to read as a globe.
      ctx.beginPath();
      path(geoGraticule10());
      ctx.globalAlpha = isDark ? 0.16 : 0.5;
      ctx.lineWidth = 0.4;
      ctx.strokeStyle = palette.stroke;
      ctx.stroke();
      ctx.globalAlpha = 1;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const outlined: any[] = [];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      for (const f of features as any[]) {
        const id = String(f.id);
        ctx.beginPath();
        path(f);
        ctx.fillStyle = isTracked(id) ? fillFor(countForCountry(id), palette) : (hatch ?? palette.land);
        ctx.fill();
        ctx.lineWidth = 0.5;
        ctx.strokeStyle = palette.stroke;
        ctx.stroke();
        if (id === hoverIdRef.current || highlightRef.current.has(id)) outlined.push(f);
      }
      // Outlines last so a neighbour's hairline never paints over them.
      for (const f of outlined) {
        ctx.beginPath();
        path(f);
        ctx.lineWidth = 1.75;
        ctx.strokeStyle = palette.outline;
        ctx.stroke();
      }

      // Thin rim so the sphere edge reads on both themes.
      ctx.beginPath();
      path({ type: 'Sphere' });
      ctx.lineWidth = 1;
      ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(26,26,46,0.12)';
      ctx.stroke();
    }

    // Hover hit-testing is throttled to once per frame (geoContains over ~200 features is not free).
    let probe: { x: number; y: number } | null = null;
    let raf = 0;
    function frame(t: number) {
      // A fly-to zoom takes precedence over hover — ease rotation to the target + scale up, then hand
      // off to the page's detailed view.
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
        const hit = hitAt(x, y);
        const id = hit?.id ?? null;
        const n = id ? countForCountry(id) : 0;
        const region = id ? regionCodeForCountry(id) : undefined;
        // French Guiana is part of France's geometry (it's an overseas region, so French and EU law
        // apply) — say so, or its France-coloured shape in South America reads as a data error.
        const note = id === FRANCE_ISO && hit && hit.lonLat[0] < -20
          ? 'French Guiana is an overseas region of France, so French and EU law apply there.'
          : undefined;
        if (id !== hoverIdRef.current || note !== undefined) {
          hoverIdRef.current = id && region ? id : null;
          dirtyRef.current = true;
          setHover(id && region ? { region, count: n, note } : null);
          canvas!.style.cursor = id && region ? 'pointer' : 'grab';
        }
      }

      if (dirtyRef.current) {
        draw();
        dirtyRef.current = false;
      }
      raf = requestAnimationFrame(frame);
    }
    dirtyRef.current = true;
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
        dirtyRef.current = true;
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
        const hit = hitAt(e.clientX, e.clientY);
        const id = hit?.id;
        const region = id ? regionCodeForCountry(id) : undefined;
        if (id && region) {
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
            dur: 600,
            fromRot: [...rotationRef.current] as [number, number],
            toRot: [toLon, -lat],
            fromZoom: zoomRef.current,
            toZoom: BASE_ZOOM * 1.6,
            onDone: () => {
              track('home_globe_select', { region });
              // Settle back to the overview framing so returning to the globe isn't a zoomed crop.
              zoomRef.current = BASE_ZOOM;
              dirtyRef.current = true;
              onSelectRef.current(region);
            },
          };
        }
      }
    };
    const onLeave = () => {
      if (hoverIdRef.current !== null) { hoverIdRef.current = null; setHover(null); dirtyRef.current = true; }
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
  }, [features, countForCountry, isTracked, palette, isDark, width, height]);

  const loading = !topo || !counts;

  return (
    <div>
      <div
        ref={wrapRef}
        className="relative w-full overflow-hidden rounded-lg border border-border-default"
        style={{ height, background: palette.ocean }}
      >
        <canvas ref={canvasRef} className="block" style={{ touchAction: 'none' }} />

        {loading && (
          <div className="absolute inset-0 grid place-items-center">
            <div className="h-40 w-40 animate-pulse rounded-full bg-bg-tertiary" />
          </div>
        )}

        {/* Hover readout — the count preview for the country under the pointer, pinned so the canvas
            never reflows. */}
        <div className="pointer-events-none absolute left-2 top-2 max-w-[calc(100%-1rem)] rounded-md bg-bg-primary/90 px-2.5 py-1.5 text-xs shadow-sm backdrop-blur-sm">
          {hover ? (
            <>
              <span className="text-text-primary">
                <span className="font-semibold">{regionLabel(hover.region)}</span>
                {' · '}{fmtCount(hover.count)} {hover.count === 1 ? 'enacted law' : MAP_METRIC}
              </span>
              {hover.note && <span className="mt-0.5 block text-text-muted">{hover.note}</span>}
            </>
          ) : (
            <span className="text-text-muted">Drag to spin · {verb} a country to filter</span>
          )}
        </div>

        {!loading && (
          <div className="pointer-events-none absolute right-2 bottom-2 rounded-md bg-bg-primary/90 px-2.5 py-1.5 text-xs text-text-secondary shadow-sm backdrop-blur-sm tabular-nums">
            <span className="font-semibold text-text-primary">{fmtCount(totals.laws)}</span> {MAP_METRIC} ·{' '}
            <span className="font-semibold text-text-primary">{totals.jur}</span> jurisdictions
          </div>
        )}
      </div>
      <MapLegend palette={palette} className="mt-2" />
    </div>
  );
}
