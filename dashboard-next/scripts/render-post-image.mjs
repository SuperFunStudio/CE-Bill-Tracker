// Per-post social/cover image for Atlas Circular Substack posts (default 1200x630 PNG) via headless Chrome.
// Consistent house style shared with the OG card + Substack banner (dark orb, accent palette, Playfair
// wordmark), but the orb is ROTATED + ZOOMED onto one country, which is highlighted. Give it a country and
// a headline; the rest of the tracked corpus glows faintly behind for context.
//
//   node scripts/render-post-image.mjs --country France --title "France's eco-modulation, decoded"
//   node scripts/render-post-image.mjs --region KE --no-text --out public/posts/kenya.png  # bare graphic
//   node scripts/render-post-image.mjs --manifest data/post-images.json   # batch: [{country|region,title,out,text}]
//
// --no-text (manifest: "text": false) omits the wordmark/label/headline and centres the country — for
// Substack, which overlays its own title, so the image is just the highlighted-country graphic.
//
// --region accepts DB region codes / ISO2 (FR, KE, CN, US, GB, KR, US-CA...) and maps to the map's country.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { geoOrthographic, geoPath, geoGraticule10, geoCentroid, geoArea } from 'd3-geo';
import { feature } from 'topojson-client';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');

const ACCENT = '243, 188, 195';
const OCEAN = '#0b1220';
const LAND = '#273241';
const fontUrl = (f) => pathToFileURL(join(__dirname, 'og-assets', f)).href;

// Same curated coverage set as the OG card — these glow faintly behind the highlighted country for context.
const TRACKED = new Set([
  'United States of America', 'Germany', 'France', 'United Kingdom', 'Spain', 'Italy', 'Netherlands',
  'Belgium', 'Japan', 'South Korea', 'Portugal', 'Ireland', 'Denmark', 'Sweden', 'Norway', 'Finland',
  'Poland', 'Austria', 'Switzerland', 'Czechia', 'Slovakia', 'Slovenia', 'Croatia', 'Hungary', 'Romania',
  'Bulgaria', 'Greece', 'Lithuania', 'Latvia', 'Estonia', 'Luxembourg', 'Malta', 'Cyprus', 'Turkey',
  'Canada', 'Australia', 'New Zealand', 'China', 'India', 'Brazil', 'Chile', 'Colombia', 'Peru', 'Uruguay',
  'Mexico', 'Costa Rica', 'South Africa', 'Kenya', 'Iceland',
]);

// DB region code / ISO2 -> map country name. US-state / EU-region codes fold up to the parent country.
const REGION_TO_COUNTRY = {
  US: 'United States of America', USA: 'United States of America', EU: 'Germany',
  FR: 'France', DE: 'Germany', GB: 'United Kingdom', UK: 'United Kingdom', ES: 'Spain', IT: 'Italy',
  NL: 'Netherlands', BE: 'Belgium', PT: 'Portugal', IE: 'Ireland', DK: 'Denmark', SE: 'Sweden',
  NO: 'Norway', FI: 'Finland', PL: 'Poland', AT: 'Austria', CH: 'Switzerland', CZ: 'Czechia',
  GR: 'Greece', TR: 'Turkey', JP: 'Japan', KR: 'South Korea', CN: 'China', IN: 'India', AU: 'Australia',
  NZ: 'New Zealand', CA: 'Canada', BR: 'Brazil', CL: 'Chile', CO: 'Colombia', PE: 'Peru', UY: 'Uruguay',
  MX: 'Mexico', CR: 'Costa Rica', ZA: 'South Africa', KE: 'Kenya', IS: 'Iceland',
};

const topo = JSON.parse(readFileSync(join(root, 'public/world-countries-50m.json'), 'utf8'));
const fc = feature(topo, topo.objects.countries);
const landFeature = feature(topo, topo.objects.land);
const byName = new Map(fc.features.map((f) => [f.properties?.name, f]));

const round = (d) => (d == null ? null : d.replace(/-?\d+\.\d+/g, (n) => (+n).toFixed(1)));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// The largest polygon of a (Multi)Polygon — the mainland. Country centroids/bounds are computed from this
// so overseas territories (France's Guiana, US's Alaska/Hawaii) don't drag the framing off the mainland.
function mainland(f) {
  if (f.geometry.type !== 'MultiPolygon') return f;
  let best = f, ba = -1;
  for (const coords of f.geometry.coordinates) {
    const g = { type: 'Feature', geometry: { type: 'Polygon', coordinates: coords } };
    const a = geoArea(g);
    if (a > ba) { ba = a; best = g; }
  }
  return best;
}

function resolveCountry({ country, region }) {
  if (country && byName.has(country)) return country;
  if (region) {
    const key = String(region).toUpperCase().split('-')[0]; // US-CA -> US
    const mapped = REGION_TO_COUNTRY[key];
    if (mapped && byName.has(mapped)) return mapped;
  }
  // Loose fallback: case-insensitive contains match on the raw country string.
  if (country) {
    const hit = fc.features.find((f) => f.properties?.name?.toLowerCase().includes(country.toLowerCase()));
    if (hit) return hit.properties.name;
  }
  return null;
}

const W = 1200, H = 630;
const CX = 600; // where the highlighted country's mainland centroid lands (x); y depends on whether text is drawn

function buildSvg(countryName, cy) {
  const CY = cy;
  const target = byName.get(countryName);
  const mland = mainland(target);
  const c = geoCentroid(mland);

  // Orthographic, rotated so the target sits at the rotation center (=> it projects exactly to translate,
  // regardless of scale — so no re-centering pass is needed after we pick the zoom).
  const proj = geoOrthographic().clipAngle(90).rotate([-c[0], -c[1]]).translate([CX, CY]);

  // Pick the zoom so the country's larger span fills ~44% of the frame's short side, then clamp so tiny
  // states don't balloon and continent-sized countries still show some neighbourhood context.
  const BASE = 1000;
  proj.scale(BASE);
  const b = geoPath(proj).bounds(mland);
  const span = Math.max(b[1][0] - b[0][0], b[1][1] - b[0][1]) || 1;
  const scale = clamp((BASE * 0.44 * Math.min(W, H)) / span, 460, 2400);
  proj.scale(scale);

  const path = geoPath(proj);
  const p = (x) => round(path(x));

  const tracked = fc.features
    .filter((f) => f.properties?.name !== countryName && TRACKED.has(f.properties?.name))
    .map((f) => p(f)).filter(Boolean)
    .map((d) => `<path d="${d}" fill="rgba(${ACCENT},0.28)" stroke="${OCEAN}" stroke-width="0.5"/>`)
    .join('');

  const targetD = p(target);

  return `
  <svg class="svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <defs>
      <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="14" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>
    <path d="${p({ type: 'Sphere' })}" fill="${OCEAN}" stroke="rgba(${ACCENT},0.22)" stroke-width="2"/>
    <path d="${p(geoGraticule10())}" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>
    <path d="${p(landFeature)}" fill="${LAND}" stroke="${OCEAN}" stroke-width="0.5"/>
    ${tracked}
    <path d="${targetD}" fill="rgba(${ACCENT},0.5)" stroke="rgb(${ACCENT})" stroke-width="2.5"
      filter="url(#glow)" stroke-linejoin="round"/>
    <path d="${targetD}" fill="rgba(${ACCENT},0.95)" stroke="#fff" stroke-width="1" stroke-linejoin="round"/>
  </svg>`;
}

function buildHtml({ countryName, title, noText }) {
  const label = countryName.toUpperCase();
  const headline = title || countryName;
  // Text-off (Substack, where the caption is added separately): centre the country and draw only the globe.
  const cy = noText ? 315 : 278;
  const overlay = noText ? '' : `
  <div class="scrim"></div>
  <div class="brand"><span class="dot"></span>Atlas Circular</div>
  <div class="footer">
    <div class="region">${label}</div>
    <div class="title">${headline.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</div>
  </div>`;
  return `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: 'Playfair'; src: url('${fontUrl('PlayfairDisplay.ttf')}'); font-weight: 600; }
@font-face { font-family: 'Roboto'; src: url('${fontUrl('Roboto.ttf')}'); font-weight: 400; }
* { margin: 0; box-sizing: border-box; }
body { width: ${W}px; height: ${H}px; overflow: hidden; }
.card { width: ${W}px; height: ${H}px; position: relative; font-family: 'Roboto', sans-serif;
  background: radial-gradient(120% 120% at 50% 42%, #101a2b 0%, #0a0f1a 62%, #080b13 100%); }
.svg { position: absolute; top: 0; left: 0; }
.scrim { position: absolute; left: 0; right: 0; bottom: 0; height: 62%;
  background: linear-gradient(180deg, rgba(8,11,19,0) 0%, rgba(8,11,19,0.78) 55%, rgba(8,11,19,0.96) 100%); }
.brand { position: absolute; top: 44px; left: 64px; display: flex; align-items: center; gap: 12px;
  font-size: 20px; font-weight: 500; letter-spacing: 4px; color: #d7c3c6; text-transform: uppercase; }
.brand .dot { width: 11px; height: 11px; border-radius: 50%; background: rgb(${ACCENT});
  box-shadow: 0 0 14px rgba(${ACCENT},0.9); }
.footer { position: absolute; left: 64px; right: 64px; bottom: 56px; }
.region { font-size: 24px; font-weight: 500; letter-spacing: 5px; color: rgb(${ACCENT});
  text-transform: uppercase; margin-bottom: 14px; }
.title { font-family: 'Playfair', serif; font-weight: 600; color: #f7f1eb; letter-spacing: 0.3px;
  font-size: ${headline.length > 58 ? 50 : headline.length > 38 ? 60 : 70}px; line-height: 1.08;
  max-width: 1000px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
</style></head><body>
<div class="card">
  ${buildSvg(countryName, cy)}${overlay}
</div>
</body></html>`;
}

function render(job) {
  const countryName = resolveCountry(job);
  if (!countryName) { console.error('SKIP — could not resolve country for', job); return; }
  const out = job.out ? join(root, job.out) : join(root, 'public', 'posts', `${countryName.toLowerCase().replace(/[^a-z]+/g, '-')}.png`);
  mkdirSync(dirname(out), { recursive: true });
  const noText = job.noText ?? job.text === false; // manifest jobs may set text:false
  const html = buildHtml({ ...job, countryName, noText });
  const htmlPath = join(root, 'scripts', '.post-image.html');
  writeFileSync(htmlPath, html);
  const chrome = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  execFileSync(chrome, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
    `--window-size=${W},${H}`, `--screenshot=${out}`, pathToFileURL(htmlPath).href,
  ], { stdio: 'inherit' });
  console.log('wrote', out, `(${countryName})`);
}

// --- args ---
const argv = process.argv.slice(2);
const arg = (k) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : undefined; };
const has = (k) => argv.includes(`--${k}`);
const manifest = arg('manifest');
if (manifest) {
  const jobs = JSON.parse(readFileSync(join(root, manifest), 'utf8'));
  for (const j of jobs) render(j);
} else {
  // --no-text: the bare globe graphic (Substack, which adds its own headline over the image).
  render({ country: arg('country'), region: arg('region'), title: arg('title'), out: arg('out'), noText: has('no-text') });
}
