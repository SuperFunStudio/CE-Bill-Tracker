// Multi-region / instrument post image for Atlas Circular (default 1200x630 PNG) via headless Chrome — the
// place-agnostic sibling of render-post-image.mjs. For articles that draw from MANY jurisdictions (a
// right-to-repair or deposit-return round-up, an "everywhere at once" piece) the graphic is just the
// coverage globe — the same dark/light orb the site's CoverageGlobe draws, multi-region lit. No headline
// baked in; Substack (or the site) adds the title separately.
//
//   node scripts/render-instrument-image.mjs                       # light (blue), default
//   node scripts/render-instrument-image.mjs --theme dark --out public/posts/globe-dark.png
//   node scripts/render-instrument-image.mjs --manifest data/globe-images.json   # [{theme,out}]
//
// --theme light|dark defaults to LIGHT (country posts default dark). Palette mirrors CoverageGlobe: light =
// blue accent (30 106 233) on a pale globe, dark = rose (243 188 195) on navy.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { geoOrthographic, geoPath, geoGraticule10 } from 'd3-geo';
import { feature } from 'topojson-client';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');
const fontUrl = (f) => pathToFileURL(join(__dirname, 'og-assets', f)).href;

const W = 1200, H = 630;
const CX = 600, CY = 315, R = 292; // centred, near-full-height orb (matches the site's CoverageGlobe framing)
const ROTATE = [18, -26]; // Atlantic-centred: US + EU + South America + Africa all on the near hemisphere

// Palette per theme — accent + ocean/land/stroke mirror CoverageGlobe's own per-theme values.
const THEMES = {
  light: { accent: '30, 106, 233', bg: 'radial-gradient(120% 120% at 50% 42%, #f4f7fb 0%, #e9eef4 60%, #e3e9f1 100%)',
    ocean: '#e9eef3', land: '#e2e8f0', stroke: '#cdd6e0', grat: 'rgba(30,45,70,0.06)', ringGlow: 0.14 },
  dark: { accent: '243, 188, 195', bg: 'radial-gradient(120% 120% at 50% 42%, #101a2b 0%, #0a0f1a 62%, #080b13 100%)',
    ocean: '#0b1220', land: '#273241', stroke: '#0b1220', grat: 'rgba(255,255,255,0.045)', ringGlow: 0.22 },
};

// Coverage tiers -> accent opacity (same curated set as the OG card / gen-og-globe.mjs).
const HOT = new Set([
  'United States of America', 'Germany', 'France', 'United Kingdom', 'Spain', 'Italy', 'Netherlands',
  'Belgium', 'Japan', 'South Korea',
]);
const WARM = new Set([
  'Portugal', 'Ireland', 'Denmark', 'Sweden', 'Norway', 'Finland', 'Poland', 'Austria', 'Switzerland',
  'Czechia', 'Slovakia', 'Slovenia', 'Croatia', 'Hungary', 'Romania', 'Bulgaria', 'Greece', 'Lithuania',
  'Latvia', 'Estonia', 'Luxembourg', 'Malta', 'Cyprus', 'Turkey', 'Canada', 'Australia', 'New Zealand',
  'China', 'India', 'Brazil', 'Chile', 'Colombia', 'Peru', 'Uruguay', 'Mexico', 'Costa Rica',
  'South Africa', 'Kenya', 'Iceland',
]);

const topo = JSON.parse(readFileSync(join(root, 'public/world-countries-50m.json'), 'utf8'));
const fc = feature(topo, topo.objects.countries);
const landFeature = feature(topo, topo.objects.land);
const round = (d) => (d == null ? null : d.replace(/-?\d+\.\d+/g, (n) => (+n).toFixed(1)));

const projection = geoOrthographic().scale(R).translate([CX, CY]).clipAngle(90).rotate(ROTATE);
const path = geoPath(projection);
const p = (x) => round(path(x));
const SPHERE = p({ type: 'Sphere' });
const GRAT = p(geoGraticule10());
const LAND = p(landFeature);
const LIT = fc.features
  .map((f) => {
    const name = f.properties?.name;
    const o = HOT.has(name) ? 0.95 : WARM.has(name) ? 0.6 : null;
    if (o == null) return null;
    const d = p(f);
    return d ? { d, o } : null;
  })
  .filter(Boolean);

function buildHtml(theme) {
  const t = THEMES[theme] || THEMES.light;
  const lit = LIT.map((c) => `<path d="${c.d}" fill="rgba(${t.accent}, ${c.o})" stroke="${t.stroke}" stroke-width="0.75"/>`).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><style>
* { margin: 0; box-sizing: border-box; }
body { width: ${W}px; height: ${H}px; overflow: hidden; }
.card { width: ${W}px; height: ${H}px; position: relative; background: ${t.bg}; }
.svg { position: absolute; top: 0; left: 0; }
</style></head><body>
<div class="card">
  <svg class="svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <defs>
      <radialGradient id="halo" cx="50%" cy="50%" r="50%">
        <stop offset="82%" stop-color="rgba(${t.accent},0)"/>
        <stop offset="97%" stop-color="rgba(${t.accent},${t.ringGlow})"/>
        <stop offset="100%" stop-color="rgba(${t.accent},0)"/>
      </radialGradient>
    </defs>
    <circle cx="${CX}" cy="${CY}" r="${R + 16}" fill="url(#halo)"/>
    <path d="${SPHERE}" fill="${t.ocean}" stroke="rgba(${t.accent},0.30)" stroke-width="1.5"/>
    <path d="${GRAT}" fill="none" stroke="${t.grat}" stroke-width="1"/>
    <path d="${LAND}" fill="${t.land}" stroke="${t.stroke}" stroke-width="0.75"/>
    ${lit}
  </svg>
</div>
</body></html>`;
}

function render(job) {
  const theme = THEMES[job.theme] ? job.theme : 'light'; // multi-region posts default light (blue)
  const out = job.out ? join(root, job.out) : join(root, 'public', 'posts', `globe-${theme}.png`);
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(join(root, 'scripts', '.instrument-image.html'), buildHtml(theme));
  const chrome = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  execFileSync(chrome, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
    `--window-size=${W},${H}`, `--screenshot=${out}`, pathToFileURL(join(root, 'scripts', '.instrument-image.html')).href,
  ], { stdio: 'inherit' });
  console.log('wrote', out, `(${theme})`);
}

const argv = process.argv.slice(2);
const arg = (k) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : undefined; };
const manifest = arg('manifest');
if (manifest) {
  for (const j of JSON.parse(readFileSync(join(root, manifest), 'utf8'))) render(j);
} else {
  render({ theme: arg('theme'), out: arg('out') });
}
