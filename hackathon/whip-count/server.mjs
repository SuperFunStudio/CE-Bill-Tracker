// Whip Count — the EPR champion board.
//
// Persona: Marcus Reyes, "The Whip" (business x design x dev). Former legislative
// director, now runs advocacy strategy. Every other entry on the board serves the
// company that must COMPLY, or the market that PRICES it. This one serves the room
// upstream of all of them — the advocates deciding whether the law should exist and
// who to call about it.
//
// Zero dependencies (Node >= 18: global fetch + built-in http). The real product is
// the COMPOSITION ENGINE below: it fans out to the SignalScout champions feed, then
// scores each legislator into an advocacy bucket the raw API never returns —
//   CLOSER    (reliable carrier: land laws — thank + protect)
//   WORKHORSE (high volume, low conversion: wants it, can't finish — back + coach)
//   RISER     (emerging or cross-aisle: worth the first meeting — watch)
// It also proxies the API server-side so the browser never touches CORS.
//
//   /insights/champions              -> every legislator's CE track record
//   /insights/champions/{id}/bills   -> one legislator's bill-by-bill receipts
//
// Buckets + influence score are a transparent heuristic, printed on the page. See
// enrich().

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const API = (process.env.SIGNALSCOUT_API || 'https://signalscout-api-36712717703.us-central1.run.app').replace(/\/$/, '');
const PORT = Number(process.env.PORT || 4930);
const TOKEN = process.env.SIGNALSCOUT_API_TOKEN || '';

async function api(path) {
  const headers = TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};
  const res = await fetch(`${API}${path}`, { headers });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

// The champions feed is a flat roster with no server-side filter or advocacy read —
// that composition is this file's job. Cache the roster; it changes on the pipeline's
// cadence, not per request.
let ROSTER = null;
async function roster() {
  if (!ROSTER) ROSTER = await api('/insights/champions?limit=500');
  return ROSTER;
}

// Coarse party bucket for the color rail + filter. Keeps the full label for display.
function partyClass(p) {
  const s = (p || '').toLowerCase();
  if (s.startsWith('republican')) return 'R';
  if (s.includes('democratic')) return 'D';
  return 'O';
}

// --- The advocacy read. Pure function of one champion's counts. -----------------
// influence rewards LANDING law far more than merely introducing it — an advocate's
// scarcest ally is someone who can actually finish.
function enrich(c) {
  const enacted = c.enacted_count || 0;
  const primary = c.primary_sponsorships || 0;
  const cosponsor = c.cosponsorships || 0;
  const total = c.total_ce_bills || 0;
  const influence = Math.round(enacted * 6 + primary * 1 + cosponsor * 0.4);

  let bucket, play;
  if (enacted >= 2) {
    bucket = 'CLOSER';
    play = `Thank + protect — ${enacted} CE law${enacted > 1 ? 's' : ''} landed. Your reliable carrier.`;
  } else if (total >= 6) {
    bucket = 'WORKHORSE';
    play = `Back + coach — ${total} bills carried, ${enacted ? 'only ' + enacted + ' enacted' : 'none landed yet'}. Wants it, can't finish alone.`;
  } else {
    bucket = 'RISER';
    play = `First meeting — ${total} CE bill${total > 1 ? 's' : ''} in. Emerging${partyClass(c.party) === 'R' ? ', and cross-aisle' : ''}. Get on the radar early.`;
  }

  return {
    ...c,
    party_class: partyClass(c.party),
    influence,
    bucket,
    play,
    conversion_pct: total ? Math.round((enacted / total) * 100) : 0,
  };
}

function buildBoard({ instrument, material, party, state, minBills }) {
  const floor = Number.isFinite(minBills) ? minBills : 2;
  const all = ROSTER.map(enrich);

  // Facets are derived from the live roster so the UI never offers a dead option.
  const facet = (key) => [...new Set(all.flatMap((c) => c[key]))].sort();
  const facets = {
    instruments: facet('instruments'),
    materials: facet('materials'),
    states: [...new Set(all.flatMap((c) => c.states))].sort(),
  };

  const rows = all
    .filter((c) => c.total_ce_bills >= floor)
    .filter((c) => !instrument || c.instruments.includes(instrument))
    .filter((c) => !material || c.materials.includes(material))
    .filter((c) => !party || c.party_class === party)
    .filter((c) => !state || c.states.includes(state))
    .sort((a, b) => b.influence - a.influence);

  const count = (b) => rows.filter((c) => c.bucket === b).length;
  const topOf = (b) => rows.find((c) => c.bucket === b) || null;
  const summary = {
    matched: rows.length,
    closers: count('CLOSER'),
    workhorses: count('WORKHORSE'),
    risers: count('RISER'),
    states: new Set(rows.flatMap((c) => c.states)).size,
    enacted_total: rows.reduce((s, c) => s + (c.enacted_count || 0), 0),
    top_closer: topOf('CLOSER'),
    top_workhorse: topOf('WORKHORSE'),
  };

  return { champions: rows.slice(0, 80), summary, facets, floor };
}

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://localhost:${PORT}`);

    if (url.pathname === '/api/board') {
      await roster();
      const q = url.searchParams;
      const data = buildBoard({
        instrument: q.get('instrument') || '',
        material: q.get('material') || '',
        party: q.get('party') || '',
        state: q.get('state') || '',
        minBills: q.has('minBills') ? Number(q.get('minBills')) : undefined,
      });
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(JSON.stringify(data));
    }

    // One legislator's bill-by-bill receipts — the "show me the track record" click.
    if (url.pathname === '/api/champion/bills') {
      const id = url.searchParams.get('id');
      if (!id) { res.writeHead(400); return res.end('{"error":"id required"}'); }
      const bills = await api(`/insights/champions/${encodeURIComponent(id)}/bills`);
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(JSON.stringify(bills));
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
  console.log(`Whip Count  ->  http://localhost:${PORT}`);
  console.log(`upstream API: ${API}${TOKEN ? '  (authed)' : '  (public tier)'}`);
});
