// Generates static orthographic-globe SVG path data for the OpenGraph image (src/app/opengraph-image.tsx).
// Framed on the North Atlantic so the two most law-dense regions — the US and Western Europe — are both
// lit, which is the whole pitch of Atlas Circular. Palette mirrors CoverageGlobe's dark theme exactly.
// Re-run after changing the lit set or framing:  node scripts/gen-og-globe.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { geoOrthographic, geoPath, geoGraticule10 } from 'd3-geo';
import { feature } from 'topojson-client';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');

const W = 1200, H = 630;
// Globe sits on the right; wordmark + tagline occupy the left third.
const CX = 800, CY = H / 2, R = 300;
const ROTATE = [28, -32]; // center ~28°W / ~32°N -> US + Europe both on the near hemisphere

const topo = JSON.parse(readFileSync(join(root, 'public/world-countries-50m.json'), 'utf8'));
const fc = feature(topo, topo.objects.countries);

const projection = geoOrthographic().scale(R).translate([CX, CY]).clipAngle(90).rotate(ROTATE);
const rawPath = geoPath(projection);
// Round every coordinate to 1 decimal — sub-pixel precision is invisible at this size and cuts the
// serialized path data by ~4x so the JSON is cheap to inline into the ImageResponse route.
const round = (d) => (d == null ? null : d.replace(/-?\d+\.\d+/g, (n) => (+n).toFixed(1)));
const path = (x) => round(rawPath(x));

// Coverage tiers -> accent opacity. Curated to reflect the real corpus emphasis (US + EU deepest,
// then the other enacted-law regions Atlas tracks). Purely cosmetic for the share card.
const HOT = new Set([ // brightest — the flagship regimes
  'United States of America', 'Germany', 'France', 'United Kingdom', 'Spain', 'Italy',
  'Netherlands', 'Belgium', 'Japan', 'South Korea',
]);
const WARM = new Set([ // rest of the EU + other tracked enacted-law countries
  'Portugal', 'Ireland', 'Denmark', 'Sweden', 'Norway', 'Finland', 'Poland', 'Austria',
  'Switzerland', 'Czechia', 'Slovakia', 'Slovenia', 'Croatia', 'Hungary', 'Romania',
  'Bulgaria', 'Greece', 'Lithuania', 'Latvia', 'Estonia', 'Luxembourg', 'Malta', 'Cyprus',
  'Turkey', 'Canada', 'Australia', 'New Zealand', 'China', 'India', 'Brazil', 'Chile',
  'Colombia', 'Peru', 'Uruguay', 'Mexico', 'Costa Rica', 'South Africa', 'Kenya', 'Iceland',
]);

const lit = [];
for (const f of fc.features) {
  const name = f.properties?.name;
  const tier = HOT.has(name) ? 0.95 : WARM.has(name) ? 0.6 : null;
  if (tier == null) continue;
  const d = path(f);
  if (d) lit.push({ d, o: tier });
}

const out = {
  w: W, h: H, cx: CX, cy: CY, r: R,
  sphere: path({ type: 'Sphere' }),
  graticule: path(geoGraticule10()),
  land: path(feature(topo, topo.objects.land)),
  lit,
};
writeFileSync(join(__dirname, 'og-assets/globe-paths.json'), JSON.stringify(out));
console.log(`wrote globe-paths.json — ${lit.length} lit countries, ${(JSON.stringify(out).length / 1024).toFixed(0)} KB`);
