// Renders a seamless-loop spinning-globe GIF for small/email use (Atlas Circular brand).
// Pipeline: d3-geo projects the globe at N evenly-spaced rotations -> one HTML per frame ->
// headless-Chrome screenshots each to PNG -> (assemble_gif.py with Pillow stitches the GIF).
// Simplified vs the OG card: disc fills the frame (reads as a round token when circle-masked),
// flat accent fill + no graticule to keep the GIF palette + file size small.
//   node scripts/gen-globe-gif.mjs <outFramesDir> [theme=dark|light] [frames=60] [tilt=-5] [bg=solid|transparent]
import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { geoOrthographic, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');

const outDir = process.argv[2] || join(__dirname, '.gif-frames');
const THEME = process.argv[3] || 'dark';
const FRAMES = Number(process.argv[4] ?? 60);   // more frames + longer per-frame delay => smooth + calm
const TILT = process.argv[5] !== undefined ? Number(process.argv[5]) : -5; // ~equator (0 = dead-on equator)
const TRANSPARENT = process.argv[6] === 'transparent'; // knock out the square -> just the orb

const SIZE = 400;          // render size (downscaled to the final GIF size by Pillow)
const R = SIZE / 2;        // disc fills the frame
const C = SIZE / 2;
const START_LON = 20;

// Palettes mirror CoverageGlobe's two themes: dark = pink accent on near-black; light = blue accent
// (#1e6ae9) on the light map surface. STROKE separates countries; RIM is the atmosphere edge.
const PALETTES = {
  dark:  { ACCENT: '#f3bcc3', OCEAN: '#0b1220', LAND: '#273241', BG: '#0b1220', STROKE: '#0b1220', RIM: 'rgba(243,188,195,0.35)' },
  light: { ACCENT: '#1e6ae9', OCEAN: '#e9eef3', LAND: '#d3dde8', BG: '#eef2f6', STROKE: '#cdd6e0', RIM: 'rgba(30,106,233,0.30)' },
};
const { ACCENT, OCEAN, LAND, BG, STROKE, RIM } = PALETTES[THEME] ?? PALETTES.dark;

// Same curated lit set as the OG card (flat fill here — one accent color keeps the GIF palette tiny).
const LIT = new Set([
  'United States of America', 'Germany', 'France', 'United Kingdom', 'Spain', 'Italy', 'Netherlands',
  'Belgium', 'Japan', 'South Korea', 'Portugal', 'Ireland', 'Denmark', 'Sweden', 'Norway', 'Finland',
  'Poland', 'Austria', 'Switzerland', 'Czechia', 'Slovakia', 'Slovenia', 'Croatia', 'Hungary', 'Romania',
  'Bulgaria', 'Greece', 'Lithuania', 'Latvia', 'Estonia', 'Luxembourg', 'Malta', 'Cyprus', 'Turkey',
  'Canada', 'Australia', 'New Zealand', 'China', 'India', 'Brazil', 'Chile', 'Colombia', 'Peru',
  'Uruguay', 'Mexico', 'Costa Rica', 'South Africa', 'Kenya', 'Iceland',
]);

const topo = JSON.parse(readFileSync(join(root, 'public/world-countries-50m.json'), 'utf8'));
const fc = feature(topo, topo.objects.countries);
const landObj = feature(topo, topo.objects.land);
const round = (d) => (d == null ? null : d.replace(/-?\d+\.\d+/g, (n) => (+n).toFixed(1)));

rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

const chrome = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

for (let f = 0; f < FRAMES; f++) {
  const lon = START_LON + (360 / FRAMES) * f; // eastward spin, seamless (frame FRAMES == frame 0)
  const projection = geoOrthographic().scale(R).translate([C, C]).clipAngle(90).rotate([lon, TILT]);
  const path = (x) => round(geoPath(projection)(x));

  const litPaths = fc.features
    .filter((ft) => LIT.has(ft.properties?.name))
    .map((ft) => path(ft))
    .filter(Boolean)
    .map((d) => `<path d="${d}" fill="${ACCENT}" stroke="${STROKE}" stroke-width="0.5"/>`)
    .join('');

  const html = `<!doctype html><meta charset="utf-8"><style>*{margin:0}html,body{width:${SIZE}px;height:${SIZE}px;background:${TRANSPARENT ? 'transparent' : BG}}</style>
<svg width="${SIZE}" height="${SIZE}" viewBox="0 0 ${SIZE} ${SIZE}">
  <path d="${path({ type: 'Sphere' })}" fill="${OCEAN}" stroke="${RIM}" stroke-width="2"/>
  <path d="${path(landObj)}" fill="${LAND}" stroke="${STROKE}" stroke-width="0.5"/>
  ${litPaths}
</svg>`;

  const htmlPath = join(outDir, `f${String(f).padStart(2, '0')}.html`);
  const pngPath = join(outDir, `f${String(f).padStart(2, '0')}.png`);
  writeFileSync(htmlPath, html);
  execFileSync(chrome, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
    ...(TRANSPARENT ? ['--default-background-color=00000000'] : []), // alpha screenshot outside the disc
    `--window-size=${SIZE},${SIZE}`, `--screenshot=${pngPath}`, pathToFileURL(htmlPath).href,
  ], { stdio: 'ignore' });
  process.stdout.write(`\rframe ${f + 1}/${FRAMES}`);
}
console.log(`\nwrote ${FRAMES} frames to ${outDir}`);
