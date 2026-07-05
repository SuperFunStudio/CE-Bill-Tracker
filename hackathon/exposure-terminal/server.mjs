// Exposure Terminal — zero-dependency Node server.
//
// Persona: Jordan Wu, "The Short Book" (business × dev × design).
//
// Every other entry on the board is built for the company that has to COMPLY.
// This one is built for the people who get to PRICE the fact that it hasn't:
// investors, insurers, procurement, M&A diligence. Same SignalScout data — run
// backwards. Not "what do I owe?" but "who owes, how much, and how late?"
//
// The composition engine is the product. SignalScout ranks who's exposed to a
// law (/companies/exposure-ranking) and, separately, tells one company what it
// owes (/companies/{id}/obligations — penalty/day, annual-fee range, deadline).
// Neither is a leaderboard of dollar liability. This fans the second across the
// first and sorts the result into a short book.

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 4320;
const API = process.env.SIGNALSCOUT_API || 'https://signalscout-api-36712717703.us-central1.run.app';

// Marquee enacted EPR laws that return company-specific exposure rankings — the
// chips the terminal opens with. Verified against prod; ordered by how legible
// the resulting book is. Everything else is reachable via the live bill list.
const FEATURED = [
  { id: 865,    label: 'CA SB-54 — Packaging & foodware' },
  { id: 104216, label: 'MN HF-3911 — Packaging Waste & Cost Reduction' },
  { id: 79747,  label: 'MD SB-901 — Packaging & paper products' },
  { id: 104217, label: 'WA SB-5284 — Recycling Reform Act' },
];

const DAY = 86_400_000;

async function getJSON(path) {
  const res = await fetch(API + path, { headers: { accept: 'application/json' } });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

function daysUntil(dateStr, today) {
  if (!dateStr) return null;
  const d = Date.parse(dateStr);
  if (Number.isNaN(d)) return null;
  return Math.round((d - today) / DAY);
}

// The book's sort key. Fee ceiling (grounded fee schedules + benchmarks) is the
// headline liability; when a name has no fee data we fall back to SignalScout's
// composite exposure score so it still ranks, just below every priced name.
function ceilingOf(row) {
  return row.annual_fee_high_usd != null ? row.annual_fee_high_usd : -1;
}

async function buildBook({ billId, limit }) {
  const today = Date.parse(new Date().toISOString().slice(0, 10));

  // Header context + the ranked set, in parallel.
  const [bill, ranking] = await Promise.all([
    getJSON(`/bills/${billId}`).catch(() => null),
    getJSON(`/companies/exposure-ranking?bill_id=${billId}&limit=${limit}`),
  ]);

  // Fan the per-company obligations rollup across the ranked set. Each ~300ms;
  // a failed name drops to its ranking-only row rather than sinking the book.
  const rows = await Promise.all(
    ranking.map(async (r, i) => {
      const c = r.company;
      const s = r.impact_score || {};
      let ob = null;
      try { ob = await getJSON(`/companies/${c.id}/obligations`); } catch { /* ranking-only */ }

      const feeHigh = ob?.portfolio_annual_fee_high_usd ?? null;
      const feeLow = ob?.portfolio_annual_fee_low_usd ?? null;
      const penDay = ob?.max_penalty_per_day_usd ?? null;
      const nextDl = ob?.next_deadline_date ?? null;

      return {
        rank: i + 1,
        company_id: c.id,
        company: c.name,
        hq_state: c.hq_state || null,
        composite_score: s.composite_score ?? null,
        estimated_annual_cost: s.estimated_annual_cost ?? null, // null on prod today; future-proofed
        affected_bill_count: ob?.affected_bill_count ?? null,
        affected_state_count: ob?.affected_states?.length ?? null,
        annual_fee_low_usd: feeLow,
        annual_fee_high_usd: feeHigh,
        any_fee_grounded: ob?.any_fee_grounded ?? false,
        // Statutory max if in continuous default for a year. Shown separately and
        // labelled — it is a ceiling, never added into the fee liability.
        max_penalty_per_day_usd: penDay,
        penalty_annualized_usd: penDay != null ? penDay * 365 : null,
        next_deadline_date: nextDl,
        days_until: daysUntil(nextDl, today),
      };
    }),
  );

  // Priced names first (by fee ceiling), unpriced names after (by composite).
  rows.sort((a, b) => {
    const ca = ceilingOf(a), cb = ceilingOf(b);
    if (ca !== cb) return cb - ca;
    return (b.composite_score ?? 0) - (a.composite_score ?? 0);
  });
  rows.forEach((r, i) => { r.rank = i + 1; });

  const priced = rows.filter((r) => r.annual_fee_high_usd != null);
  const soonest = rows
    .map((r) => r.next_deadline_date).filter(Boolean).sort()[0] || null;

  return {
    bill: bill && {
      id: bill.id,
      state: bill.state,
      bill_number: bill.bill_number,
      title: bill.title,
      source_url: bill.source_url_final || bill.source_url || null,
    },
    generated_utc: new Date().toISOString(),
    summary: {
      names: rows.length,
      priced: priced.length,
      grounded: rows.filter((r) => r.any_fee_grounded).length,
      // Book-level liability: fees are per-company, so summing across names is legit.
      book_fee_low_usd: priced.reduce((t, r) => t + (r.annual_fee_low_usd || 0), 0) || null,
      book_fee_high_usd: priced.reduce((t, r) => t + (r.annual_fee_high_usd || 0), 0) || null,
      max_penalty_per_day_usd: rows.reduce((m, r) => Math.max(m, r.max_penalty_per_day_usd || 0), 0) || null,
      soonest_deadline: soonest,
      days_until_soonest: daysUntil(soonest, today),
    },
    rows,
  };
}

// ---------------------------------- HTTP ----------------------------------
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' };

async function serveStatic(res) {
  try {
    const file = join(__dirname, 'public', 'index.html');
    const body = await readFile(file);
    res.writeHead(200, { 'content-type': MIME[extname(file)] || 'text/plain' });
    res.end(body);
  } catch {
    res.writeHead(500).end('index.html missing');
  }
}

function sendJSON(res, code, obj) {
  res.writeHead(code, { 'content-type': 'application/json' });
  res.end(JSON.stringify(obj));
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (url.pathname === '/' || url.pathname === '/index.html') return serveStatic(res);

  // The bill picker: featured chips + the live enacted-EPR universe to search.
  if (url.pathname === '/api/bills') {
    try {
      const list = await getJSON('/bills?status=enacted&ce_relevant=true&instrument_type=epr&limit=300');
      const bills = list
        .filter((b) => b.bill_number && b.title)
        .map((b) => ({ id: b.id, state: b.state, bill_number: b.bill_number, title: b.title }))
        .sort((a, b) => (a.state + a.bill_number).localeCompare(b.state + b.bill_number));
      return sendJSON(res, 200, { featured: FEATURED, bills });
    } catch (err) {
      return sendJSON(res, 502, { error: String(err.message || err) });
    }
  }

  if (url.pathname === '/api/book') {
    const billId = Number(url.searchParams.get('bill_id'));
    const limit = Math.min(Number(url.searchParams.get('limit')) || 12, 25);
    if (!billId) return sendJSON(res, 400, { error: 'pass ?bill_id=865' });
    try {
      return sendJSON(res, 200, await buildBook({ billId, limit }));
    } catch (err) {
      return sendJSON(res, 502, { error: String(err.message || err) });
    }
  }

  res.writeHead(404).end('not found');
});

server.listen(PORT, () => {
  console.log(`\n  Exposure Terminal  →  http://localhost:${PORT}`);
  console.log(`  Proxying SignalScout API: ${API}\n`);
});
