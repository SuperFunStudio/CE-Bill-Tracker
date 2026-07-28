// Generates the OpenGraph / Twitter share card (public/og-image.png) via headless Chrome.
// Dark North-Atlantic globe (US + Western Europe lit) + Playfair wordmark + tagline + coverage legend.
// Palette mirrors CoverageGlobe's dark theme so the card reads as the same product. Regenerate with:
//   node scripts/gen-og-globe.mjs        # re-project the globe (framing / lit set)
//   node scripts/render-og-preview.mjs   # re-render public/og-image.png
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');
const globe = JSON.parse(readFileSync(join(__dirname, 'og-assets/globe-paths.json'), 'utf8'));

const ACCENT = '243, 188, 195';
const OCEAN = '#0b1220';
const LAND = '#273241';
const fontUrl = (f) => pathToFileURL(join(__dirname, 'og-assets', f)).href;

const litPaths = globe.lit
  .map((c) => `<path d="${c.d}" fill="rgba(${ACCENT}, ${c.o})" stroke="${OCEAN}" stroke-width="0.75"/>`)
  .join('');

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: 'Playfair'; src: url('${fontUrl('PlayfairDisplay.ttf')}'); font-weight: 600; }
@font-face { font-family: 'Roboto'; src: url('${fontUrl('Roboto.ttf')}'); font-weight: 400; }
* { margin: 0; box-sizing: border-box; }
body { width: 1200px; height: 630px; overflow: hidden; }
.card { width: 1200px; height: 630px; position: relative; font-family: 'Roboto', sans-serif;
  background: radial-gradient(120% 120% at 78% 50%, #101a2b 0%, #0a0f1a 60%, #080b13 100%); }
.svg { position: absolute; top: 0; left: 0; }
.col { position: absolute; top: 0; left: 0; width: 560px; height: 100%; display: flex; flex-direction: column;
  justify-content: center; padding: 0 0 0 72px; }
.kicker { display: flex; align-items: center; gap: 12px; margin-bottom: 22px; }
.kicker .bar { width: 34px; height: 3px; background: rgb(${ACCENT}); border-radius: 2px; }
.kicker .txt { font-size: 20px; letter-spacing: 4px; color: rgb(${ACCENT}); text-transform: uppercase; }
.word { font-family: 'Playfair', serif; font-weight: 600; font-size: 82px; line-height: 1.02; color: #f6efe9; letter-spacing: 1px; }
.tag { margin-top: 26px; font-size: 25px; line-height: 1.35; color: #9fadbd; max-width: 430px; }
.legend { display: flex; align-items: center; gap: 12px; margin-top: 40px; }
.legend .lo { font-size: 16px; color: #6b7887; }
.legend .hi { font-size: 16px; color: #8b98a7; }
.legend .grad { width: 150px; height: 9px; border-radius: 5px; background: linear-gradient(90deg, rgba(${ACCENT},0.12), rgb(${ACCENT})); }
</style></head><body>
<div class="card">
  <svg class="svg" width="1200" height="630" viewBox="0 0 1200 630">
    <path d="${globe.sphere}" fill="${OCEAN}" stroke="rgba(${ACCENT}, 0.28)" stroke-width="2"/>
    <path d="${globe.graticule}" fill="none" stroke="rgba(255,255,255,0.045)" stroke-width="1"/>
    <path d="${globe.land}" fill="${LAND}" stroke="${OCEAN}" stroke-width="0.75"/>
    ${litPaths}
  </svg>
  <div class="col">
    <div class="kicker"><div class="bar"></div><div class="txt">Circular-economy law</div></div>
    <div class="word">Atlas<br/>Circular</div>
    <div class="tag">Navigate circular-economy legislation — bills, deadlines, and analysis across the globe, by jurisdiction.</div>
    <div class="legend"><span class="lo">Fewer</span><div class="grad"></div><span class="hi">More laws</span></div>
  </div>
</div>
</body></html>`;

const htmlPath = join(root, 'scripts', '.og-preview.html');
writeFileSync(htmlPath, html);

const chrome = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const outPng = process.argv[2] || join(root, 'public', 'og-image.png');
execFileSync(chrome, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
  '--window-size=1200,630', `--screenshot=${outPng}`, pathToFileURL(htmlPath).href,
], { stdio: 'inherit' });
console.log('wrote', outPng);
