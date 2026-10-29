'use client';
import { useEffect, useMemo, useState } from 'react';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';
import { geoEqualEarth, geoArea, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { Feature, FeatureCollection, Polygon, MultiPolygon } from 'geojson';
import { useTheme } from '@/components/layout/ThemeContext';
import { regionLabel } from '@/components/insights/RegionFilter';
import { MAP_METRIC, fillFor, fmtCount, mapPalette } from '@/lib/mapScale';
import { useTapOrClick } from '@/hooks/useTapOrClick';

// A cropped, auto-framed regional map. Instead of a global overview, the map now *shows the selected
// region*: the region's countries are highlighted and the view is fit to them (fitExtent), so US /
// EU / a single country each fill the frame at their own scale — no empty-ocean world, no false
// cross-region comparison. Framing is derived from the geometry, so no per-country centroids/scales.
// 50m Natural Earth — smooth coastlines, member borders, small islands (Malta/Cyprus), at ~236KB
// gzipped. (The finer 10m tier smears/over-fills at country-level zoom and is 4x the weight for a
// marginal gain, so 50m is the sweet spot.) Fetched only when a region map shows, then shared across
// mounts via TOPO_CACHE so drilling never re-parses it.
const GEO_URL = '/world-countries-50m.json';
// Fixed drawing box the projection is fit into; the wrapper scales it responsively.
const VB_W = 800;
const VB_H = 420;
// The region fills this fraction of the frame — leaves breathing room so elongated regions (Japan)
// aren't clipped at the edges.
const FILL = 0.82;

// Module-level cache: the 10m TopoJSON is big, so fetch + parse it once and share it across every
// RegionInsetMap mount (keyed remounts for the zoom animation would otherwise re-parse 3.7MB).
let TOPO_CACHE: unknown = null;
let TOPO_PROMISE: Promise<unknown> | null = null;
function loadTopo(): Promise<unknown> {
  if (TOPO_CACHE) return Promise.resolve(TOPO_CACHE);
  if (!TOPO_PROMISE) {
    TOPO_PROMISE = fetch(GEO_URL)
      .then(r => r.json())
      .then(d => { TOPO_CACHE = d; return d; });
  }
  return TOPO_PROMISE;
}

// EU member states as ISO 3166-1 numeric ids (matches geo.id in world-atlas).
export const EU_MEMBER_IDS = [
  '040', '056', '100', '191', '196', '203', '208', '233', '246', '250', '276', '300', '348',
  '372', '380', '428', '440', '442', '528', '616', '620', '642', '703', '705', '724', '752',
];

// Region/country code (from the Regions dropdown) → ISO numeric id (matches geo.id). Covers every EU
// member plus the foreign codes we ingest / may ingest; an unknown code yields [] and the caller
// falls back to a text panel.
const CODE_TO_ISO: Record<string, string> = {
  FR: '250', JP: '392', DE: '276', ES: '724', UK: '826', PL: '616', SE: '752',
  NL: '528', FI: '246', IE: '372', DK: '208', AT: '040', LU: '442', LV: '428', SK: '703',
  LT: '440', CZ: '203', EE: '233', SI: '705', IT: '380', PT: '620', GR: '300', RO: '642',
  BG: '100', HR: '191', CY: '196', HU: '348', BE: '056', MT: '470',
  CH: '756', NO: '578', CL: '152', BR: '076', KR: '410', TW: '158', RU: '643', CA: '124', AU: '036', MX: '484',
  CN: '156', IN: '356', TR: '792',
  CO: '170', PE: '604', UY: '858', EC: '218', MY: '458', ID: '360', PH: '608', VN: '704', TH: '764',
  KE: '404', RW: '646', ZM: '894', MW: '454', SL: '694',
};

// Reverse lookup for click-to-drill: a clicked country's geo.id → its dropdown region code.
const ISO_TO_CODE: Record<string, string> = Object.fromEntries(
  Object.entries(CODE_TO_ISO).map(([code, iso]) => [iso, code]),
);

/** Dropdown region code for a clicked country's ISO numeric id (undefined if we don't track it). */
export function codeForIso(id: string): string | undefined {
  return ISO_TO_CODE[id];
}

/** Enacted-law count per ISO numeric id from laws-in-force points — national law (sub-national rolled
 *  in) plus the EU-central body for every member, exactly as the globe counts it. */
export function enactedCountsByIso(points: { region: string; count: number }[]): Record<string, number> {
  const byRegion: Record<string, number> = {};
  for (const p of points) {
    const nat = p.region.split('-')[0];
    byRegion[nat] = (byRegion[nat] ?? 0) + p.count;
  }
  const out: Record<string, number> = {};
  for (const [code, iso] of Object.entries(CODE_TO_ISO)) if (byRegion[code]) out[iso] = byRegion[code];
  if (byRegion.US) out['840'] = byRegion.US;
  const eu = byRegion.EU ?? 0;
  for (const iso of EU_MEMBER_IDS) out[iso] = (out[iso] ?? 0) + eu;
  return out;
}

/** ISO numeric ids to highlight for a region code. EU = the whole bloc; else the single country. */
export function highlightIdsFor(code: string): string[] {
  if (code === 'EU') return EU_MEMBER_IDS;
  const iso = CODE_TO_ISO[code];
  return iso ? [iso] : [];
}

// Reduce a country to its single largest polygon (by spherical area) for framing purposes, so
// overseas territories don't blow up the bounding box. Polygons pass through unchanged.
function primaryLandmass(feat: Feature): Feature {
  if (feat.geometry?.type !== 'MultiPolygon') return feat;
  const polys = (feat.geometry as MultiPolygon).coordinates;
  let best = polys[0];
  let bestArea = -1;
  for (const rings of polys) {
    const area = geoArea({ type: 'Polygon', coordinates: rings });
    if (area > bestArea) { bestArea = area; best = rings; }
  }
  const geometry: Polygon = { type: 'Polygon', coordinates: best };
  return { ...feat, geometry };
}

interface RegionInsetMapProps {
  /** ISO numeric ids that are the subject of the view — framed, and shaded by count. */
  highlightIds: string[];
  /** Enacted-law count per ISO id (see enactedCountsByIso) — subject countries shade on the site-wide
   *  scale. Omitted → subjects take the middle bin, as a plain locator. */
  countsByIso?: Record<string, number>;
  /** Subject ids drawn with the selection outline (a lone country in focus). */
  selectedIds?: string[];
  /** Ids outlined from outside — the jurisdiction of the table row under the pointer. */
  previewIds?: string[];
  caption?: string;
  /** When set, highlighted countries become clickable and drill into that region (re-crop + filter).
   *  Only fires for countries we track (codeForIso resolves). */
  onCountrySelect?: (code: string) => void;
  height?: number;
}

export function RegionInsetMap({
  highlightIds, countsByIso, selectedIds, previewIds, caption, onCountrySelect, height = 380,
}: RegionInsetMapProps) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const palette = useMemo(() => mapPalette(isDark), [isDark]);
  // Context countries outside the subject sit back as a flat, faint landmass.
  const backdrop = isDark ? '#1c2533' : '#e9edf2';
  const verb = useTapOrClick();
  const [hover, setHover] = useState<string | null>(null);
  const outlineSet = useMemo(
    () => new Set([...(selectedIds ?? []), ...(previewIds ?? [])].map(String)),
    [selectedIds, previewIds],
  );

  // Seed from the shared cache so a drill-in (keyed remount) paints instantly — no re-fetch flash.
  const [topo, setTopo] = useState<any>(TOPO_CACHE);
  useEffect(() => {
    if (topo) return;
    let alive = true;
    loadTopo().then(d => { if (alive) setTopo(d); }).catch(() => {});
    return () => { alive = false; };
  }, [topo]);

  const hiSet = useMemo(() => new Set(highlightIds.map(String)), [highlightIds]);

  // Fit an Equal-Earth projection to just the highlighted countries → the region fills the frame.
  // We frame to each country's LARGEST landmass only: some countries (e.g. France) carry far-flung
  // overseas territories (French Guiana, Réunion) whose bbox would otherwise shrink the mainland to a
  // dot. The full geometry still renders; the territories simply fall outside the crop.
  const projection = useMemo(() => {
    if (!topo) return null;
    const fc = feature(topo, topo.objects.countries);
    const mainlands = fc.features
      .filter(f => hiSet.has(String(f.id)))
      .map(primaryLandmass);
    if (!mainlands.length) return null;
    const fit: FeatureCollection = { type: 'FeatureCollection', features: mainlands };
    // Fit into a centered inset box that's FILL of the frame → the region fills ~82% with even margin
    // on all sides (so elongated regions like Japan aren't clipped). fitExtent handles the centering.
    const mx = (VB_W * (1 - FILL)) / 2;
    const my = (VB_H * (1 - FILL)) / 2;
    return geoEqualEarth().fitExtent([[mx, my], [VB_W - mx, VB_H - my]], fit);
  }, [topo, hiSet]);

  // Only draw countries that actually fall within the frame. At a country-level zoom the other ~250
  // nations project far off-screen, and some (Antarctica) sweep a stray fill across the viewBox — plus
  // rendering the whole world's 10m geometry is needlessly heavy. geoPath.bounds gives each country's
  // projected box; keep those overlapping the viewBox (highlighted ones always survive).
  const pathGen = useMemo(() => (projection ? geoPath(projection) : null), [projection]);
  const inView = (geo: unknown, id: string): boolean => {
    if (hiSet.has(id)) return true;
    if (!pathGen) return false;
    const b = pathGen.bounds(geo as any);
    const [[x0, y0], [x1, y1]] = b;
    if (![x0, y0, x1, y1].every(Number.isFinite)) return false;
    const M = 40;
    return x1 >= -M && x0 <= VB_W + M && y1 >= -M && y0 <= VB_H + M;
  };

  if (!topo || !projection) {
    return <div className="bg-bg-secondary rounded-lg animate-pulse" style={{ height }} />;
  }

  const countOf = (id: string) => countsByIso ? (countsByIso[id] ?? 0) : 20;
  const hoverCode = hover ? codeForIso(hover) : undefined;

  return (
    <div>
      <div className="relative rounded-lg border border-border-default" style={{ height, background: palette.ocean }}>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <ComposableMap width={VB_W} height={VB_H} projection={projection as any} style={{ width: '100%', height: '100%' }}>
          <Geographies geography={topo}>
            {({ geographies }) =>
              geographies
                .filter(geo => inView(geo, String(geo.id)))
                // Outlined countries last, so neighbours' hairlines never paint over the outline.
                .sort((a, b) => Number(outlineSet.has(String(a.id)) || hover === String(a.id)) - Number(outlineSet.has(String(b.id)) || hover === String(b.id)))
                .map(geo => {
                const id = String(geo.id);
                const on = hiSet.has(id);
                const code = on ? codeForIso(id) : undefined;
                const clickable = !!onCountrySelect && !!code;
                const name = (geo.properties?.name as string) ?? code ?? '';
                const select = () => code && onCountrySelect?.(code);
                const fill = on ? fillFor(countOf(id), palette) : backdrop;
                const outlined = outlineSet.has(id) || (clickable && hover === id);

                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={fill}
                    stroke={outlined ? palette.outline : palette.stroke}
                    strokeWidth={outlined ? 1.75 : 0.5}
                    onClick={clickable ? select : undefined}
                    onMouseEnter={on ? () => setHover(id) : undefined}
                    onMouseLeave={on ? () => setHover(h => (h === id ? null : h)) : undefined}
                    // Keyboard parity with the click handler (WCAG 2.1.1): focusable + Enter/Space.
                    tabIndex={clickable ? 0 : -1}
                    role={clickable ? 'button' : undefined}
                    aria-label={clickable ? `${name}: ${countOf(id)} ${MAP_METRIC} — filter` : undefined}
                    onKeyDown={
                      clickable
                        ? (e: React.KeyboardEvent) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              select();
                            }
                          }
                        : undefined
                    }
                    style={{
                      // Fill never changes on hover — the outline is the hover signal.
                      default: { fill, outline: 'none', cursor: clickable ? 'pointer' : 'default' },
                      hover: { fill, outline: 'none' },
                      pressed: { fill, outline: 'none' },
                    }}
                  />
                );
              })
            }
          </Geographies>
        </ComposableMap>
        {onCountrySelect && (
          <div className="pointer-events-none absolute left-2 top-2 rounded-md bg-bg-primary/90 px-2.5 py-1.5 text-xs shadow-sm backdrop-blur-sm">
            {hover && hoverCode ? (
              <span className="text-text-primary">
                <span className="font-semibold">{regionLabel(hoverCode)}</span>
                {' · '}{fmtCount(countOf(hover))} {countOf(hover) === 1 ? 'enacted law' : MAP_METRIC}
              </span>
            ) : (
              <span className="text-text-muted">{verb === 'tap' ? 'Tap' : 'Click'} a country to filter</span>
            )}
          </div>
        )}
      </div>
      {caption && <div className="mt-1 text-center text-meta text-text-muted">{caption}</div>}
    </div>
  );
}
