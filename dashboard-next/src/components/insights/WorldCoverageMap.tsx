'use client';

import { useEffect, useMemo, useState } from 'react';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';
import { geoEqualEarth, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import { useTheme } from '@/components/layout/ThemeContext';
import { useRegion } from '@/components/layout/RegionContext';
import { EU_MEMBER_IDS, codeForIso } from '@/components/map/RegionInsetMap';
import { regionLabel } from './RegionFilter';
import { fetchLawsInForce } from '@/lib/api';
import { track } from '@/lib/analytics';

/**
 * World choropleth of circular-economy laws in force, by jurisdiction — the cross-region overview the
 * unified corpus unlocks. Each country is shaded by how many enacted CE laws apply there: its own
 * national laws PLUS the EU-central body for EU member states (EU regulations/directives bind every
 * member), so the map reads as "regulatory exposure here", not just "laws we scraped from this portal".
 *
 * Data: /bills/laws-in-force grouped by region (US, EU, FR, JP, …), summed across years. The ISO-code
 * plumbing (EU_MEMBER_IDS, codeForIso) is shared with the RegionInsetMap. Untracked countries render as
 * muted land. Clicking a tracked country drives the global region filter, so the map is also a picker.
 */

const GEO_URL = '/world-countries-50m.json';
const VB_W = 800;
const VB_H = 415;
const ANTARCTICA = '010'; // stretches the frame + sweeps a stray fill; dropped from fit + render.
const US_ISO = '840';

// Module cache so the 50m topojson is fetched + parsed once and shared across mounts.
let TOPO_CACHE: unknown = null;
let TOPO_PROMISE: Promise<unknown> | null = null;
function loadTopo(): Promise<unknown> {
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

export function WorldCoverageMap() {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const accent = isDark ? '#f3bcc3' : '#1e6ae9';
  const stroke = isDark ? '#111827' : '#f8f9fa';
  const land = isDark ? '#1f2937' : '#e5e7eb';

  const { setRegions } = useRegion();
  const [topo, setTopo] = useState<any>(TOPO_CACHE);
  const [counts, setCounts] = useState<Map<string, number> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<{ name: string; region: string; count: number } | null>(null);

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
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load coverage.'); });
    return () => { cancelled = true; };
  }, []);

  // Laws-in-force that apply in a given country: its national tally + the EU-central body if a member.
  const countForCountry = useMemo(() => {
    const euCount = counts?.get('EU') ?? 0;
    return (id: string): number => {
      if (!counts) return 0;
      const nat = id === US_ISO ? (counts.get('US') ?? 0) : (() => {
        const c = codeForIso(id);
        return c ? (counts.get(c) ?? 0) : 0;
      })();
      const euBase = EU_MEMBER_IDS.includes(id) ? euCount : 0;
      return nat + euBase;
    };
  }, [counts]);

  const { projection, max, totals } = useMemo(() => {
    if (!topo || !counts) return { projection: null, geographies: [] as any[], max: 0, totals: { jur: 0, laws: 0 } };
    const fc: any = feature(topo, topo.objects.countries);
    const drawn = fc.features.filter((f: any) => String(f.id) !== ANTARCTICA);
    const proj = geoEqualEarth().fitExtent(
      [[8, 8], [VB_W - 8, VB_H - 8]],
      { type: 'FeatureCollection', features: drawn },
    );
    let max = 0;
    const trackedRegions = new Set<string>();
    for (const [region, n] of counts) { if (n > 0) trackedRegions.add(region); }
    for (const f of drawn) max = Math.max(max, countForCountry(String(f.id)));
    // Headline totals: distinct regions we hold laws for, and the sum of laws in force across them.
    const laws = [...counts.values()].reduce((s, n) => s + n, 0);
    return { projection: proj, geographies: drawn, max, totals: { jur: trackedRegions.size, laws } };
  }, [topo, counts, countForCountry]);

  const pathGen = useMemo(() => (projection ? geoPath(projection) : null), [projection]);

  if (error) return <p className="text-sm text-error">{error}</p>;
  if (!topo || !counts || !pathGen) return <div className="h-[380px] w-full animate-pulse rounded-lg bg-bg-tertiary" />;

  // sqrt tint so the long tail (3 … 1500) stays legible instead of everything but the US washing out.
  const tint = (n: number): string => (n <= 0 || max <= 0)
    ? land
    : `color-mix(in srgb, ${accent} ${(15 + 80 * Math.sqrt(n / max)).toFixed(1)}%, ${land})`;

  return (
    <div className="space-y-3">
      <div className="relative">
        <ComposableMap
          width={VB_W}
          height={VB_H}
          /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
          projection={projection as any}
          style={{ width: '100%', height: 'auto' }}
        >
          <Geographies geography={topo}>
            {({ geographies: geos }) =>
              geos.filter(geo => String(geo.id) !== ANTARCTICA).map(geo => {
                const id = String(geo.id);
                const n = countForCountry(id);
                const region = regionCodeForCountry(id);
                const clickable = n > 0 && !!region;
                const name = (geo.properties?.name as string) ?? region ?? '';
                const go = () => {
                  if (!clickable || !region) return;
                  setRegions([region]);
                  track('insights_worldmap_select', { region });
                };
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={tint(n)}
                    stroke={stroke}
                    strokeWidth={0.4}
                    onMouseEnter={() => n > 0 && region && setHover({ name, region, count: n })}
                    onMouseLeave={() => setHover(null)}
                    onClick={clickable ? go : undefined}
                    tabIndex={clickable ? 0 : -1}
                    role={clickable ? 'button' : undefined}
                    aria-label={clickable ? `${name}: ${n} circular-economy laws in force — filter to this region` : undefined}
                    onKeyDown={clickable ? (e: React.KeyboardEvent) => {
                      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); }
                    } : undefined}
                    style={{
                      default: { outline: 'none', cursor: clickable ? 'pointer' : 'default' },
                      hover: { outline: 'none', fill: clickable ? accent : tint(n), fillOpacity: clickable ? 0.85 : 1 },
                      pressed: { outline: 'none' },
                    }}
                  />
                );
              })
            }
          </Geographies>
        </ComposableMap>

        {/* Hover readout, pinned so the map doesn't reflow. */}
        <div className="pointer-events-none absolute left-3 top-3 rounded-md bg-bg-primary/90 px-2.5 py-1.5 text-xs shadow-sm">
          {hover ? (
            <span className="text-text-primary">
              <span className="font-semibold">{regionLabel(hover.region)}</span>
              {' · '}{hover.count.toLocaleString()} law{hover.count === 1 ? '' : 's'} in force
            </span>
          ) : (
            <span className="text-text-muted">Hover a jurisdiction · click to filter</span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <span>Fewer</span>
          <span className="h-2.5 w-28 rounded-full" style={{ background: `linear-gradient(to right, ${land}, ${accent})` }} />
          <span>More laws in force</span>
        </div>
        <p className="text-xs text-text-secondary">
          <span className="font-semibold text-text-primary">{totals.jur}</span> jurisdictions ·{' '}
          <span className="font-semibold text-text-primary">{totals.laws.toLocaleString()}</span> CE laws in force
        </p>
      </div>

      <p className="text-text-muted text-xs leading-relaxed">
        Each jurisdiction is shaded by the count of enacted circular-economy laws in force that apply
        there — a country&apos;s own national laws plus the EU-central body (regulations &amp; directives)
        for EU member states. Shading is relative (√-scaled), so read the hover count, not just the tint.
        Untracked countries are muted. Click a jurisdiction to filter the whole site to it.
      </p>
    </div>
  );
}
