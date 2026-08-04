// Atlas Circular "Rise of Circularity Law" timeline banner — a shareable, gazette-styled PNG of the
// annual circular-economy bill count (the Insights timeline, dressed for sharing). Same house style as
// the OG card / Substack banner (dark orb, dusty-pink accent, Playfair wordmark), rendered via headless
// Chrome at 2x for a crisp asset.
//
//   node scripts/render-timeline-banner.mjs                       # horizontal banner -> public/timeline-banner.png
//   node scripts/render-timeline-banner.mjs --vertical            # portrait 1080x1350 -> public/timeline-banner-vertical.png
//   node scripts/render-timeline-banner.mjs --out foo.png --start 2008
//
// Data is pulled LIVE from the prod API (/bills/timeline) so the asset regenerates current. Falls back to
// a sibling timeline.json if the fetch fails. Counts are ce_relevant bills bucketed by year of most recent
// legislative action (status_date) — the exact series behind the Insights "Momentum" timeline.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { geoOrthographic, geoPath, geoGraticule10 } from 'd3-geo';
import { feature } from 'topojson-client';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');

// ── house palette (shared with render-og-preview / render-substack-banner) ───────────────────────────
const ACCENT = '243, 188, 195';   // dusty pink
const OCEAN = '#0b1220';
const LAND = '#273241';
const CREAM = '#f7f1eb';
const fontUrl = (f) => pathToFileURL(join(__dirname, 'og-assets', f)).href;

const API = process.env.API_BASE || 'https://signalscout-api-36712717703.us-central1.run.app';

// Curated coverage set — glows faintly on the decorative corner orb (mirrors the other house assets).
const TRACKED = new Set([
  'United States of America', 'Germany', 'France', 'United Kingdom', 'Spain', 'Italy', 'Netherlands',
  'Belgium', 'Japan', 'South Korea', 'Portugal', 'Ireland', 'Denmark', 'Sweden', 'Norway', 'Finland',
  'Poland', 'Austria', 'Switzerland', 'Czechia', 'Slovakia', 'Slovenia', 'Croatia', 'Hungary', 'Romania',
  'Bulgaria', 'Greece', 'Lithuania', 'Latvia', 'Estonia', 'Luxembourg', 'Malta', 'Cyprus', 'Turkey',
  'Canada', 'Australia', 'New Zealand', 'China', 'India', 'Brazil', 'Chile', 'Colombia', 'Peru', 'Uruguay',
  'Mexico', 'Costa Rica', 'South Africa', 'Kenya', 'Iceland',
]);

// ── args ─────────────────────────────────────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const arg = (k) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : undefined; };
const has = (k) => argv.includes(`--${k}`);
const vertical = has('vertical');
const MODE = (arg('mode') || 'annual').toLowerCase(); // 'annual' (bars) | 'cumulative' (laws-on-the-books area)
const CUMULATIVE = MODE === 'cumulative';
const START = Number(arg('start') || (CUMULATIVE ? 1995 : 2005));

// ── data ───────────────────────────────────────────────────────────────────────────────────────────
async function loadTimeline() {
  try {
    const res = await fetch(`${API}/bills/timeline`);
    if (res.ok) return await res.json();
    throw new Error(`HTTP ${res.status}`);
  } catch (e) {
    const local = join(__dirname, 'timeline.json');
    if (existsSync(local)) { console.warn('fetch failed, using local timeline.json:', e.message); return JSON.parse(readFileSync(local, 'utf8')); }
    throw e;
  }
}

function shape(points) {
  const byYear = new Map(), enacted = new Map(); const regions = new Set();
  let total = 0, enactedTotal = 0;
  for (const p of points) {
    if (p.year == null) continue;
    byYear.set(p.year, (byYear.get(p.year) ?? 0) + p.count);
    if (p.status === 'enacted') { enacted.set(p.year, (enacted.get(p.year) ?? 0) + p.count); enactedTotal += p.count; }
    regions.add(p.region); total += p.count;
  }
  const minYear = Math.min(...byYear.keys());
  const maxYear = Math.max(...byYear.keys());
  const bars = [];
  for (let y = START; y <= maxYear; y++) bars.push({ year: y, count: byYear.get(y) ?? 0 });
  // Cumulative enacted laws "on the books" — accumulate from the earliest record so the value at
  // START already carries all prior history, then plot from START.
  const cumulative = [];
  let run = 0;
  for (let y = minYear; y <= maxYear; y++) {
    run += enacted.get(y) ?? 0;
    if (y >= START) cumulative.push({ year: y, count: run });
  }
  return { bars, cumulative, total, enactedTotal, regions: regions.size, maxYear };
}

// ── decorative corner orb (faint, behind the masthead) ───────────────────────────────────────────────
function buildOrb(cx, cy, r) {
  const topo = JSON.parse(readFileSync(join(root, 'public/world-countries-50m.json'), 'utf8'));
  const fc = feature(topo, topo.objects.countries);
  const land = feature(topo, topo.objects.land);
  const proj = geoOrthographic().scale(r).translate([cx, cy]).clipAngle(90).rotate([28, -32]);
  const gp = geoPath(proj);
  const round = (d) => (d == null ? null : d.replace(/-?\d+\.\d+/g, (n) => (+n).toFixed(1)));
  const p = (x) => round(gp(x));
  const lit = fc.features.map((f) => {
    if (!TRACKED.has(f.properties?.name)) return null;
    const d = p(f); return d ? `<path d="${d}" fill="rgba(${ACCENT},0.34)" stroke="${OCEAN}" stroke-width="0.5"/>` : null;
  }).filter(Boolean).join('');
  return `
    <path d="${p({ type: 'Sphere' })}" fill="${OCEAN}" stroke="rgba(${ACCENT},0.18)" stroke-width="2"/>
    <path d="${p(geoGraticule10())}" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>
    <path d="${p(land)}" fill="${LAND}" stroke="${OCEAN}" stroke-width="0.5"/>
    ${lit}`;
}

// ── bar chart svg ────────────────────────────────────────────────────────────────────────────────────
// plot: {x0,x1,y0,y1} in svg px. y0 = top (max), y1 = baseline (zero).
function buildChart(bars, plot, opts) {
  const { x0, x1, y0, y1 } = plot;
  const { yMax, gridStep, labelEvery, trackingStart, barLabelSize = 20, tickSize = 20, gridLabelSize = 17 } = opts;
  const yFor = (v) => y1 - (v / yMax) * (y1 - y0);
  const n = bars.length;
  const slot = (x1 - x0) / n;
  const bw = Math.min(slot * 0.60, 46);

  // gridlines + y labels
  let grid = '';
  for (let v = 0; v <= yMax; v += gridStep) {
    const y = yFor(v);
    grid += `<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" stroke="rgba(255,255,255,${v === 0 ? 0.22 : 0.07})" stroke-width="1"/>`;
    grid += `<text x="${x0 - 16}" y="${(y + gridLabelSize * 0.35).toFixed(1)}" text-anchor="end" font-size="${gridLabelSize}" fill="rgba(233,224,216,0.55)" font-family="Roboto">${v}</text>`;
  }

  // continuous-tracking marker (honesty: pre-marker years are reconstructed enacted laws only)
  let marker = '';
  if (trackingStart) {
    const idx = bars.findIndex((b) => b.year === trackingStart);
    if (idx >= 0) {
      const mx = x0 + idx * slot + slot / 2 - bw / 2 - Math.max(slot * 0.20, 8);
      marker = `<line x1="${mx.toFixed(1)}" y1="${y0 - 6}" x2="${mx.toFixed(1)}" y2="${y1}" stroke="rgba(233,224,216,0.30)" stroke-width="1.4" stroke-dasharray="5 4"/>
        <text x="${(mx + 8).toFixed(1)}" y="${(y0 + 6).toFixed(1)}" font-size="${gridLabelSize - 1}" fill="rgba(233,224,216,0.55)" font-family="Roboto" font-style="italic">continuous tracking begins</text>`;
    }
  }

  // bars + x ticks + selective direct labels
  let barsSvg = '', ticks = '';
  const r = Math.min(bw / 2, 6);
  const lastIdx = n - 1;
  bars.forEach((b, i) => {
    const cx = x0 + i * slot + slot / 2;
    const x = cx - bw / 2;
    const yv = yFor(b.count);
    const h = Math.max(y1 - yv, 0.5);
    const partial = b.year === opts.maxYear && opts.partialLast;
    const fill = partial ? 'url(#barPartial)' : 'url(#barFill)';
    const rr = Math.min(r, h);
    // rounded top, square base (anchored to baseline)
    const d = `M${x.toFixed(1)},${y1} L${x.toFixed(1)},${(yv + rr).toFixed(1)} Q${x.toFixed(1)},${yv.toFixed(1)} ${(x + rr).toFixed(1)},${yv.toFixed(1)} L${(x + bw - rr).toFixed(1)},${yv.toFixed(1)} Q${(x + bw).toFixed(1)},${yv.toFixed(1)} ${(x + bw).toFixed(1)},${(yv + rr).toFixed(1)} L${(x + bw).toFixed(1)},${y1} Z`;
    barsSvg += `<path d="${d}" fill="${fill}"${partial ? ` stroke="rgba(${ACCENT},0.85)" stroke-width="1.3" stroke-dasharray="4 3"` : ''}/>`;

    // direct labels: first bar, peak-ish last two full years, and the partial last bar
    const label = (i === 0) || (i === lastIdx) || (i === lastIdx - 1);
    if (label) {
      barsSvg += `<text x="${cx.toFixed(1)}" y="${(yv - 12).toFixed(1)}" text-anchor="middle" font-size="${barLabelSize}" fill="${CREAM}" font-family="Roboto" font-weight="500">${b.count}${partial ? '*' : ''}</text>`;
    }
    // x-axis year ticks (every labelEvery, plus the last) — suppress a regular tick when it would
    // collide with the always-shown final (YTD) label.
    if ((i % labelEvery === 0 && lastIdx - i > 1) || i === lastIdx) {
      ticks += `<text x="${cx.toFixed(1)}" y="${(y1 + tickSize + 6).toFixed(1)}" text-anchor="middle" font-size="${tickSize}" fill="rgba(233,224,216,0.70)" font-family="Roboto">${b.year}${partial ? "\u2009YTD" : ''}</text>`;
    }
  });

  return grid + marker + barsSvg + ticks;
}

// Cumulative "laws on the books" area chart — single filled series rising to the running total.
function buildArea(points, plot, opts) {
  const { x0, x1, y0, y1 } = plot;
  const { yMax, gridStep, labelEvery, trackingStart, tickSize = 20, gridLabelSize = 17, partialLast, maxYear } = opts;
  const yFor = (v) => y1 - (v / yMax) * (y1 - y0);
  const n = points.length;
  const xFor = (i) => x0 + (n === 1 ? 0 : (i / (n - 1)) * (x1 - x0));

  let grid = '';
  for (let v = 0; v <= yMax; v += gridStep) {
    const y = yFor(v);
    grid += `<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" stroke="rgba(255,255,255,${v === 0 ? 0.22 : 0.07})" stroke-width="1"/>`;
    grid += `<text x="${x0 - 16}" y="${(y + gridLabelSize * 0.35).toFixed(1)}" text-anchor="end" font-size="${gridLabelSize}" fill="rgba(233,224,216,0.55)" font-family="Roboto">${v.toLocaleString()}</text>`;
  }

  const pts = points.map((p, i) => [xFor(i), yFor(p.count)]);
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `M${pts[0][0].toFixed(1)},${y1} ` + pts.map(([x, y]) => `L${x.toFixed(1)},${y.toFixed(1)}`).join(' ') + ` L${pts[n - 1][0].toFixed(1)},${y1} Z`;

  let marker = '';
  if (trackingStart) {
    const idx = points.findIndex((p) => p.year === trackingStart);
    if (idx >= 0) {
      const mx = xFor(idx);
      marker = `<line x1="${mx.toFixed(1)}" y1="${y0 - 6}" x2="${mx.toFixed(1)}" y2="${y1}" stroke="rgba(233,224,216,0.28)" stroke-width="1.4" stroke-dasharray="5 4"/>
        <text x="${(mx + 8).toFixed(1)}" y="${(y0 + 6).toFixed(1)}" font-size="${gridLabelSize - 1}" fill="rgba(233,224,216,0.55)" font-family="Roboto" font-style="italic">continuous tracking begins</text>`;
    }
  }

  // endpoint dots + labels (first + last), and x ticks
  let deco = '', ticks = '';
  points.forEach((p, i) => {
    const isLast = i === n - 1;
    const partial = isLast && partialLast;
    if (i === 0 || isLast) {
      const [x, y] = pts[i];
      deco += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6" fill="rgb(${ACCENT})" stroke="${OCEAN}" stroke-width="2"/>`;
      deco += `<text x="${x.toFixed(1)}" y="${(y - 18).toFixed(1)}" text-anchor="${isLast ? 'end' : 'start'}" font-size="24" fill="${CREAM}" font-family="Roboto" font-weight="500">${p.count.toLocaleString()}${partial ? '*' : ''}</text>`;
    }
    if ((i % labelEvery === 0 && (n - 1) - i > 1) || isLast) {
      ticks += `<text x="${xFor(i).toFixed(1)}" y="${(y1 + tickSize + 6).toFixed(1)}" text-anchor="middle" font-size="${tickSize}" fill="rgba(233,224,216,0.70)" font-family="Roboto">${p.year}${partial ? " YTD" : ''}</text>`;
    }
  });

  return grid + marker + `<path d="${area}" fill="url(#areaFill)"/><path d="${line}" fill="none" stroke="rgb(${ACCENT})" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>` + deco + ticks;
}

function statTiles(stats, x, y, gap, opts = {}) {
  const { size = 44, labelSize = 15 } = opts;
  return stats.map((s, i) => {
    const tx = x + i * gap;
    return `<g>
      <text x="${tx}" y="${y}" font-family="Playfair" font-weight="600" font-size="${size}" fill="${CREAM}">${s.value}</text>
      <text x="${tx}" y="${y + labelSize + 8}" font-family="Roboto" font-size="${labelSize}" letter-spacing="1.5" fill="rgba(${ACCENT},0.95)">${s.label.toUpperCase()}</text>
    </g>`;
  }).join('');
}

function defs() {
  return `<defs>
    <linearGradient id="barFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="rgba(${ACCENT},0.98)"/>
      <stop offset="100%" stop-color="rgba(${ACCENT},0.42)"/>
    </linearGradient>
    <linearGradient id="barPartial" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="rgba(${ACCENT},0.30)"/>
      <stop offset="100%" stop-color="rgba(${ACCENT},0.08)"/>
    </linearGradient>
    <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="rgba(${ACCENT},0.55)"/>
      <stop offset="100%" stop-color="rgba(${ACCENT},0.03)"/>
    </linearGradient>
  </defs>`;
}

// ── layouts ──────────────────────────────────────────────────────────────────────────────────────────
function horizontal(data) {
  const W = 1600, H = 1000;
  const plot = { x0: 118, x1: 1512, y0: 452, y1: 806 };
  const orb = buildOrb(1452, 150, 250);
  const chart = CUMULATIVE
    ? buildArea(data.cumulative, plot, {
        yMax: 1200, gridStep: 300, labelEvery: 5, trackingStart: 2019,
        maxYear: data.maxYear, partialLast: true, tickSize: 20, gridLabelSize: 17,
      })
    : buildChart(data.bars, plot, {
        yMax: 400, gridStep: 100, labelEvery: 5, trackingStart: 2019,
        maxYear: data.maxYear, partialLast: true, barLabelSize: 21, tickSize: 20, gridLabelSize: 17,
      });
  const subtitle = CUMULATIVE
    ? 'Cumulative circular-economy laws in force worldwide, by year enacted'
    : 'Circular-economy bills tracked worldwide, by year of most recent legislative action';
  const stats = statTiles([
    { value: data.total.toLocaleString(), label: 'bills tracked' },
    { value: String(data.regions), label: 'jurisdictions' },
    { value: data.enactedTotal.toLocaleString(), label: 'enacted laws' },
  ], 120, 372, 210, { size: 46, labelSize: 15 });

  const svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
    ${defs()}
    <g opacity="0.85">${orb}</g>
    <g>
      <text x="120" y="96" font-family="Roboto" font-size="19" letter-spacing="5" fill="#d7c3c6">ATLAS CIRCULAR</text>
      <circle cx="103" cy="90" r="6" fill="rgb(${ACCENT})"/>
      <text x="118" y="188" font-family="Playfair" font-weight="600" font-size="72" fill="${CREAM}">The Rise of Circularity Law</text>
      <text x="120" y="238" font-family="Playfair" font-style="italic" font-size="27" fill="rgba(${ACCENT},0.95)">${subtitle}</text>
    </g>
    <g>${stats}</g>
    <g>${chart}</g>
    <line x1="118" y1="880" x2="1512" y2="880" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <text x="118" y="918" font-family="Roboto" font-size="16" fill="rgba(233,224,216,0.55)">Source: Atlas Circular corpus &#183; ${CUMULATIVE ? 'enacted circular-economy laws, cumulative' : 'ce-relevant bills with a dated status'} &#183; *2026 is year-to-date</text>
    <text x="1512" y="918" text-anchor="end" font-family="Roboto" font-size="16" fill="rgba(233,224,216,0.45)">atlascircular.com</text>
    <text x="118" y="944" font-family="Roboto" font-size="14" fill="rgba(233,224,216,0.38)">Pre-2019 counts are enacted laws reconstructed from the historical record; continuous multi-status tracking begins ~2019.</text>
  </svg>`;
  return { W, H, svg };
}

function verticalLayout(data) {
  const W = 1080, H = 1350;
  const plot = { x0: 96, x1: 992, y0: 640, y1: 1120 };
  const orb = buildOrb(920, 150, 230);
  const chart = CUMULATIVE
    ? buildArea(data.cumulative, plot, {
        yMax: 1200, gridStep: 300, labelEvery: 5, trackingStart: 2019,
        maxYear: data.maxYear, partialLast: true, tickSize: 21, gridLabelSize: 18,
      })
    : buildChart(data.bars, plot, {
        yMax: 400, gridStep: 100, labelEvery: 5, trackingStart: 2019,
        maxYear: data.maxYear, partialLast: true, barLabelSize: 22, tickSize: 21, gridLabelSize: 18,
      });
  const sub = CUMULATIVE
    ? ['Cumulative circular-economy laws', 'in force worldwide, by year enacted']
    : ['Circular-economy bills tracked worldwide,', 'by year of most recent legislative action'];
  const stats = statTiles([
    { value: data.total.toLocaleString(), label: 'bills' },
    { value: String(data.regions), label: 'jurisdictions' },
    { value: data.enactedTotal.toLocaleString(), label: 'enacted laws' },
  ], 98, 560, 320, { size: 52, labelSize: 16 });

  const svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
    ${defs()}
    <g opacity="0.80">${orb}</g>
    <g>
      <text x="115" y="118" font-family="Roboto" font-size="20" letter-spacing="5" fill="#d7c3c6">ATLAS CIRCULAR</text>
      <circle cx="98" cy="112" r="6" fill="rgb(${ACCENT})"/>
      <text x="96" y="330" font-family="Playfair" font-weight="600" font-size="82" fill="${CREAM}">The Rise of</text>
      <text x="96" y="422" font-family="Playfair" font-weight="600" font-size="82" fill="${CREAM}">Circularity Law</text>
      <text x="98" y="478" font-family="Playfair" font-style="italic" font-size="29" fill="rgba(${ACCENT},0.95)">${sub[0]}</text>
      <text x="98" y="514" font-family="Playfair" font-style="italic" font-size="29" fill="rgba(${ACCENT},0.95)">${sub[1]}</text>
    </g>
    <g>${stats}</g>
    <g>${chart}</g>
    <line x1="96" y1="1196" x2="992" y2="1196" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <text x="96" y="1234" font-family="Roboto" font-size="17" fill="rgba(233,224,216,0.55)">Source: Atlas Circular corpus &#183; *2026 is year-to-date</text>
    <text x="96" y="1262" font-family="Roboto" font-size="15" fill="rgba(233,224,216,0.38)">Pre-2019 = enacted laws reconstructed from the record; continuous tracking begins ~2019.</text>
    <text x="992" y="1300" text-anchor="end" font-family="Roboto" font-size="16" fill="rgba(233,224,216,0.45)">atlascircular.com</text>
  </svg>`;
  return { W, H, svg };
}

// ── render ───────────────────────────────────────────────────────────────────────────────────────────
const data = shape(await loadTimeline());
console.log(`data: ${data.total} bills, ${data.regions} regions, ${data.enactedTotal} enacted, ${data.bars.length} bars (${START}-${data.maxYear})`);
const { W, H, svg } = vertical ? verticalLayout(data) : horizontal(data);

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family:'Playfair'; src:url('${fontUrl('PlayfairDisplay.ttf')}'); font-weight:600; }
@font-face { font-family:'Roboto'; src:url('${fontUrl('Roboto.ttf')}'); font-weight:400; }
* { margin:0; box-sizing:border-box; }
body { width:${W}px; height:${H}px; overflow:hidden;
  background: radial-gradient(120% 120% at 82% 12%, #101a2b 0%, #0a0f1a 58%, #080b13 100%); }
svg { display:block; }
</style></head><body>${svg}</body></html>`;

const htmlPath = join(root, 'scripts', `.timeline-banner${vertical ? '-v' : ''}.html`);
writeFileSync(htmlPath, html);

const suffix = `${CUMULATIVE ? '-cumulative' : ''}${vertical ? '-vertical' : ''}`;
const out = arg('out') ? join(root, arg('out')) : join(root, 'public', `timeline-banner${suffix}.png`);
mkdirSync(dirname(out), { recursive: true });
const chrome = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
execFileSync(chrome, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=2',
  `--window-size=${W},${H}`, `--screenshot=${out}`, pathToFileURL(htmlPath).href,
], { stdio: 'inherit' });
console.log('wrote', out, `(${W}x${H} @2x)`);
