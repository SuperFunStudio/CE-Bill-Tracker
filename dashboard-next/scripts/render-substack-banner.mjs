// Generates the Substack publication banner (public/substack-banner.png, 1100x220) via headless Chrome.
// Adapted from render-og-preview.mjs: same dark globe / Playfair wordmark / accent palette, but reprojected
// and re-laid-out for the wide short banner strip — the orb bleeds off the right, wordmark + tagline sit left.
// Substack recommends 1100x220 PNG. Regenerate with:
//   node scripts/render-substack-banner.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { geoOrthographic, geoPath, geoGraticule10 } from 'd3-geo';
import { feature } from 'topojson-client';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');

const W = 1100, H = 220;
// Orb sits on the right and bleeds off the top/bottom/right edges; wordmark + tagline occupy the left.
const CX = 940, CY = H / 2, R = 235;
const ROTATE = [28, -32]; // center ~28°W / ~32°N -> US + Europe both on the near hemisphere (matches OG card)

const ACCENT = '243, 188, 195';
const OCEAN = '#0b1220';
const LAND = '#273241';
const fontUrl = (f) => pathToFileURL(join(__dirname, 'og-assets', f)).href;

const topo = JSON.parse(readFileSync(join(root, 'public/world-countries-50m.json'), 'utf8'));
const fc = feature(topo, topo.objects.countries);

const projection = geoOrthographic().scale(R).translate([CX, CY]).clipAngle(90).rotate(ROTATE);
const rawPath = geoPath(projection);
const round = (d) => (d == null ? null : d.replace(/-?\d+\.\d+/g, (n) => (+n).toFixed(1)));
const path = (x) => round(rawPath(x));

// Coverage tiers -> accent opacity (mirrors gen-og-globe.mjs curated set).
const HOT = new Set([
  'United States of America', 'Germany', 'France', 'United Kingdom', 'Spain', 'Italy',
  'Netherlands', 'Belgium', 'Japan', 'South Korea',
]);
const WARM = new Set([
  'Portugal', 'Ireland', 'Denmark', 'Sweden', 'Norway', 'Finland', 'Poland', 'Austria',
  'Switzerland', 'Czechia', 'Slovakia', 'Slovenia', 'Croatia', 'Hungary', 'Romania',
  'Bulgaria', 'Greece', 'Lithuania', 'Latvia', 'Estonia', 'Luxembourg', 'Malta', 'Cyprus',
  'Turkey', 'Canada', 'Australia', 'New Zealand', 'China', 'India', 'Brazil', 'Chile',
  'Colombia', 'Peru', 'Uruguay', 'Mexico', 'Costa Rica', 'South Africa', 'Kenya', 'Iceland',
]);

const litPaths = fc.features
  .map((f) => {
    const name = f.properties?.name;
    const o = HOT.has(name) ? 0.95 : WARM.has(name) ? 0.6 : null;
    if (o == null) return null;
    const d = path(f);
    return d ? `<path d="${d}" fill="rgba(${ACCENT}, ${o})" stroke="${OCEAN}" stroke-width="0.6"/>` : null;
  })
  .filter(Boolean)
  .join('');

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: 'Playfair'; src: url('${fontUrl('PlayfairDisplay.ttf')}'); font-weight: 600; }
@font-face { font-family: 'Roboto'; src: url('${fontUrl('Roboto.ttf')}'); font-weight: 400; }
* { margin: 0; box-sizing: border-box; }
body { width: ${W}px; height: ${H}px; overflow: hidden; }
.card { width: ${W}px; height: ${H}px; position: relative; font-family: 'Roboto', sans-serif;
  background: radial-gradient(120% 220% at 82% 50%, #101a2b 0%, #0a0f1a 60%, #080b13 100%); }
.svg { position: absolute; top: 0; left: 0; }
.col { position: absolute; top: 0; left: 0; width: 640px; height: 100%; display: flex; flex-direction: column;
  justify-content: center; padding: 0 0 0 60px; }
.word { font-family: 'Playfair', serif; font-weight: 600; font-size: 76px; line-height: 1.0; color: #f6efe9; letter-spacing: 0.5px; }
.subtitle { margin-top: 14px; font-size: 27px; font-weight: 500; letter-spacing: 0.3px; color: rgb(${ACCENT}); }
</style></head><body>
<div class="card">
  <svg class="svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <path d="${path({ type: 'Sphere' })}" fill="${OCEAN}" stroke="rgba(${ACCENT}, 0.28)" stroke-width="2"/>
    <path d="${path(geoGraticule10())}" fill="none" stroke="rgba(255,255,255,0.045)" stroke-width="1"/>
    <path d="${path(feature(topo, topo.objects.land))}" fill="${LAND}" stroke="${OCEAN}" stroke-width="0.6"/>
    ${litPaths}
  </svg>
  <div class="col">
    <div class="word">Atlas Circular</div>
    <div class="subtitle">Tracking circularity globally</div>
  </div>
</div>
</body></html>`;

const htmlPath = join(root, 'scripts', '.substack-banner.html');
writeFileSync(htmlPath, html);

const chrome = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const outPng = process.argv[2] || join(root, 'public', 'substack-banner.png');
execFileSync(chrome, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
  `--window-size=${W},${H}`, `--screenshot=${outPng}`, pathToFileURL(htmlPath).href,
], { stdio: 'inherit' });
console.log('wrote', outPng);
