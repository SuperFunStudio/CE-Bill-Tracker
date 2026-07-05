// EPR Forward Curve — the "what regulates next" forecast engine.
//
// Zero dependencies (Node >= 18: uses the global fetch + built-in http).
// Fans out to three PUBLIC SignalScout endpoints, computes a per-state Forward
// Score server-side, and serves the result as GET /api/forecast. Also proxies
// the API server-side so the browser never touches CORS.
//
//   /bills/map-summary        -> pending pipeline pressure per state
//   /insights/state-gap       -> how hard a state over-indexes on CE lawmaking
//   /bills/stance-momentum    -> national tailwind (advances vs weakens)
//
// The score is a transparent heuristic, not an ML model — see computeForecast().

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const API = (process.env.SIGNALSCOUT_API || 'https://signalscout-api-36712717703.us-central1.run.app').replace(/\/$/, '');
const PORT = Number(process.env.PORT || 4720);
const TOKEN = process.env.SIGNALSCOUT_API_TOKEN || '';

// Only these keys map onto the tile-grid; drops federal "US" and any non-US region.
const US_STATES = new Set(['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC']);

async function api(path) {
  const headers = TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};
  const res = await fetch(`${API}${path}`, { headers });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

const clamp01 = (x) => Math.max(0, Math.min(1, x));

function verdict(score, pending) {
  if (pending === 0) return { tier: 'no-pipeline', label: 'No active pipeline' };
  if (score >= 65) return { tier: 'imminent',  label: 'Imminent — heavy pending load, likely to enact within ~12–18 mo' };
  if (score >= 45) return { tier: 'building',  label: 'Building — active pipeline, watch the next session' };
  if (score >= 25) return { tier: 'early',     label: 'Early — bills introduced, no critical mass yet' };
  return { tier: 'dormant', label: 'Dormant — little forward movement' };
}

// The forecast model. Pure function of the three feeds so it's easy to reason about.
function computeForecast(mapSummary, stateGap, momentum) {
  // --- National tailwind: advances vs weakens over the most recent 5 data-years.
  const maxYear = momentum.reduce((m, r) => Math.max(m, r.year), 0);
  const windowStart = maxYear - 4;
  let advances = 0, weakens = 0;
  for (const r of momentum) {
    if (r.year < windowStart) continue;
    if (r.stance === 'advances') advances += r.count;
    else if (r.stance === 'weakens') weakens += r.count;
  }
  const tailwind = advances + weakens > 0 ? advances / (advances + weakens) : 0.5;
  // Momentum modulates the score as a 0.6–1.0 national multiplier (never zeroes a state out).
  const climate = 0.6 + 0.4 * tailwind;

  const gapByState = new Map(stateGap.map((r) => [r.state, r.gap]));
  const rows = mapSummary.filter((r) => US_STATES.has(r.state) && r.total_relevant > 0);
  const maxPending = rows.reduce((m, r) => Math.max(m, r.pending_count), 1);
  const gaps = rows.map((r) => gapByState.get(r.state) ?? 0);
  const minGap = Math.min(...gaps, 0), maxGap = Math.max(...gaps, 0.001);

  const states = rows.map((r) => {
    const pending = r.pending_count;
    const enacted = r.enacted_count;
    const gap = gapByState.get(r.state) ?? 0;

    const pressure = pending / maxPending;                       // raw in-flight volume
    const room = pending / Math.max(1, enacted + pending);        // how much is queued vs already passed
    const propensity = clamp01((gap - minGap) / (maxGap - minGap)); // does this state lead or lag its peers

    const base = 0.5 * pressure + 0.3 * room + 0.2 * propensity;
    const score = Math.round(100 * climate * base);
    return {
      state: r.state, score, pending, enacted,
      totalRelevant: r.total_relevant,
      gap: Number(gap.toFixed(4)),
      ...verdict(score, pending),
      components: {
        pressure: Math.round(pressure * 100),
        room: Math.round(room * 100),
        propensity: Math.round(propensity * 100),
      },
    };
  });

  states.sort((a, b) => b.score - a.score);
  return {
    national: {
      advances, weakens,
      tailwindPct: Math.round(tailwind * 100),
      windowStart, windowEnd: maxYear,
    },
    states,
  };
}

async function forecast() {
  const [mapSummary, stateGap, momentum] = await Promise.all([
    api('/bills/map-summary'),
    api('/insights/state-gap'),
    api('/bills/stance-momentum'),
  ]);
  return computeForecast(mapSummary, stateGap, momentum);
}

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    if (url.pathname === '/api/forecast') {
      const data = await forecast();
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(JSON.stringify(data));
    }
    // static
    const file = url.pathname === '/' ? 'index.html' : url.pathname.replace(/^\/+/, '');
    const full = join(__dirname, 'public', file);
    if (!full.startsWith(join(__dirname, 'public'))) { res.writeHead(403); return res.end('no'); }
    const body = await readFile(full);
    res.writeHead(200, { 'content-type': MIME[extname(full)] || 'application/octet-stream' });
    res.end(body);
  } catch (err) {
    const notFound = err?.code === 'ENOENT';
    res.writeHead(notFound ? 404 : 502, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: String(err.message || err) }));
  }
});

server.listen(PORT, () => {
  console.log(`EPR Forward Curve  ->  http://localhost:${PORT}`);
  console.log(`upstream API: ${API}${TOKEN ? '  (authed)' : '  (public tier)'}`);
});
