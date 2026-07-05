// Under Appeal — zero-dependency Node server.
//
// Persona: Dana Okonkwo, "The Docket" (business 45 · dev 30 · design 25).
// Ex-EPR-defense litigator. Every other entry on the board treats an enacted law as a
// rock you build on. Dana spent years trying to blow those rocks up — and sometimes won.
// Her read: the most expensive compliance mistake isn't missing a deadline, it's spending
// to comply with a statute that gets ENJOINED or preempted before it takes effect.
//
// The composition engine is the product. SignalScout tells you what a company OWES
// (/companies/{id}/obligations) and, separately, what's being LITIGATED
// (/bills/{id}/litigation-cases). Neither answers "is what I owe standing on solid
// ground?" This joins the two per obligation, scores each Settled / Under Challenge /
// Enjoined, and — the read the raw API can't give — flags obligations with no suit of
// their own that stand on a legal theory already WINNING in another state (the bellwether).

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname } from 'node:path';
import { SEED_CASES, seedCasesByLaw, dccPrecedent } from './litigation-seed.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 4740;
const API = process.env.SIGNALSCOUT_API || 'https://signalscout-api-36712717703.us-central1.run.app';

// The marquee producers whose portfolios span the litigated laws — the picker chips.
// Pulled live otherwise; these open the demo on the biggest, most legible books.
const FEATURED_BILL = 865; // CA SB-54 — its exposure ranking is the packaging majors.

// The packaging-EPR fee programs the Dormant Commerce Clause fight actually reaches.
// (Not every plastic-labeling law — the precedent is about producer-responsibility fee
// schemes.) An obligation on one of these, with no suit of its own, is still EXPOSED the
// moment the DCC theory wins anywhere. Ids verified against prod.
const PACKAGING_EPR_LAWS = new Map([
  [865, 'CA SB-54'],
  [72452, 'OR SB-582 (RMA)'],
  [79747, 'MD SB-901'],
  [104216, 'MN HF-3911'],
  [104217, 'WA SB-5284'],
]);

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

const isPackaging = (mats) =>
  Array.isArray(mats) && mats.some((m) => String(m).toLowerCase().includes('packag'));

// Bring a live litigation-cases row (LitigationCaseSummary) into the same shape the seed
// uses, so live and seed render identically. When prod ingests cases, live wins and the
// overlay disappears with zero UI change.
function normalizeLive(row) {
  const tighten = String(row.plaintiff_type || '').includes('advocacy');
  return {
    ...row,
    source: 'live',
    filed_label: row.date_filed ? `Filed ${row.date_filed}` : null,
    theories: row.challenge_type ? [row.challenge_type] : [],
    direction: tighten ? 'tighten' : 'strike',
    events: [],
    event_count: row.event_count ?? 0,
    sources: row.cl_url ? [{ label: 'CourtListener docket', url: row.cl_url }] : [],
  };
}

function tagSeed(c) {
  return { ...c, source: 'seed', event_count: c.events?.length ?? 0 };
}

// The verdict for a single obligation, given the cases attached to its law.
// ENJOINED > UNDER_CHALLENGE > EXPOSED (by precedent) > CONTESTED_REGS (rules may tighten) > SETTLED.
function verdictFor(obligation, directCases, precedent) {
  const strike = directCases.filter((c) => c.direction !== 'tighten');
  const tighten = directCases.filter((c) => c.direction === 'tighten');

  const enjoined = strike.find((c) => c.case_status === 'injunction_granted');
  if (enjoined) {
    return { state: 'ENJOINED', rank: 5, risk: enjoined.preemption_risk ?? 90, risk_basis: 'direct',
      headline: 'Enforcement paused by court order', driver: enjoined };
  }
  if (strike.length) {
    const worst = strike.slice().sort((a, b) => (b.preemption_risk ?? 0) - (a.preemption_risk ?? 0))[0];
    return { state: 'UNDER_CHALLENGE', rank: 4, risk: worst.preemption_risk ?? 50, risk_basis: 'direct',
      headline: 'Facing an active constitutional challenge', driver: worst };
  }
  // No suit of its own — but does it stand on a theory already winning elsewhere?
  if (precedent && PACKAGING_EPR_LAWS.has(obligation.bill_id)) {
    return { state: 'EXPOSED', rank: 3, risk: Math.round((precedent.risk ?? 80) * 0.5), risk_basis: 'precedent',
      headline: `Untested here, but the same theory just won in ${precedent.state}`, driver: null };
  }
  if (tighten.length) {
    return { state: 'CONTESTED_REGS', rank: 2, risk: 0, risk_basis: 'tighten',
      headline: 'Rules challenged as too weak — your fees may rise, not vanish', driver: tighten[0] };
  }
  return { state: 'SETTLED', rank: 1, risk: 0, risk_basis: 'none',
    headline: 'No known challenge', driver: null };
}

async function buildReview(companyId) {
  const today = Date.parse(new Date().toISOString().slice(0, 10));
  const ob = await getJSON(`/companies/${companyId}/obligations`);
  const obligations = ob.obligations || [];

  // Precedent read: has the DCC theory actually WON against a packaging-EPR law anywhere?
  const dcc = dccPrecedent();
  const precedent = dcc
    ? { ...dcc, risk: SEED_CASES.find((c) => c.case_name === dcc.case_name)?.preemption_risk ?? 85 }
    : null;

  // Fan the litigation feed across every obligation. Live first; seed only fills the gap.
  const rows = await Promise.all(
    obligations.map(async (o) => {
      let cases = [];
      try {
        const live = await getJSON(`/bills/${o.bill_id}/litigation-cases`);
        cases = Array.isArray(live) && live.length ? live.map(normalizeLive) : seedCasesByLaw(o.bill_id).map(tagSeed);
      } catch {
        cases = seedCasesByLaw(o.bill_id).map(tagSeed);
      }

      const verdict = verdictFor(o, cases, precedent);
      const dl = o.next_deadline || null;
      return {
        bill_id: o.bill_id,
        state: o.state,
        bill_number: o.bill_number,
        bill_title: o.bill_title,
        source_url: o.source_url || null,
        is_packaging: isPackaging(o.matched_materials),
        materials: o.matched_materials || [],
        deadline_date: dl?.deadline_date || o.next_deadline_date || null,
        deadline_type: dl?.deadline_type || null,
        deadline_detail: dl?.description || null,
        days_until: daysUntil(dl?.deadline_date || o.next_deadline_date, today),
        verdict: verdict.state,
        verdict_rank: verdict.rank,
        verdict_headline: verdict.headline,
        risk: verdict.risk,
        risk_basis: verdict.risk_basis,
        cases,
      };
    }),
  );

  // Sort: hottest verdict first, then risk, then soonest deadline.
  rows.sort((a, b) => {
    if (a.verdict_rank !== b.verdict_rank) return b.verdict_rank - a.verdict_rank;
    if (a.risk !== b.risk) return b.risk - a.risk;
    if (a.deadline_date && b.deadline_date) return a.deadline_date < b.deadline_date ? -1 : 1;
    return a.deadline_date ? -1 : 1;
  });

  const contested = rows.filter((r) => ['ENJOINED', 'UNDER_CHALLENGE', 'EXPOSED'].includes(r.verdict));
  const enjoined = rows.filter((r) => r.verdict === 'ENJOINED');
  const challenged = rows.filter((r) => r.verdict === 'UNDER_CHALLENGE');
  const exposed = rows.filter((r) => r.verdict === 'EXPOSED');
  const tighten = rows.filter((r) => r.verdict === 'CONTESTED_REGS');
  const contestedStates = [...new Set(contested.map((r) => r.state))];
  const soonestContested = contested
    .map((r) => r.deadline_date).filter(Boolean).sort()[0] || null;

  return {
    company: { id: companyId, name: ob.company_name },
    generated_utc: new Date().toISOString(),
    precedent, // the bellwether banner
    portfolio: {
      affected_bill_count: ob.affected_bill_count,
      affected_states: ob.affected_states || [],
      fee_low_usd: ob.portfolio_annual_fee_low_usd ?? null,
      fee_high_usd: ob.portfolio_annual_fee_high_usd ?? null,
      any_fee_grounded: ob.any_fee_grounded ?? false,
      next_deadline_date: ob.next_deadline_date || null,
    },
    summary: {
      total: rows.length,
      packaging: rows.filter((r) => r.is_packaging).length,
      contested: contested.length,
      enjoined: enjoined.length,
      challenged: challenged.length,
      exposed: exposed.length,
      tighten: tighten.length,
      contested_states: contestedStates,
      soonest_contested_deadline: soonestContested,
      days_until_soonest_contested: daysUntil(soonestContested, today),
      any_seed: rows.some((r) => r.cases.some((c) => c.source === 'seed')),
    },
    rows,
  };
}

async function buildPicker() {
  // Featured = the packaging majors (SB-54 exposure ranking); rest = searchable universe.
  const [ranking, companies] = await Promise.all([
    getJSON(`/companies/exposure-ranking?bill_id=${FEATURED_BILL}&limit=8`).catch(() => []),
    getJSON('/companies?limit=400').catch(() => []),
  ]);
  const featured = ranking.map((r) => ({ id: r.company.id, name: r.company.name, hq_state: r.company.hq_state || null }));
  const all = companies
    .map((c) => ({ id: c.id, name: c.name, hq_state: c.hq_state || null }))
    .sort((a, b) => a.name.localeCompare(b.name));
  return { featured, companies: all };
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

  if (url.pathname === '/api/companies') {
    try { return sendJSON(res, 200, await buildPicker()); }
    catch (err) { return sendJSON(res, 502, { error: String(err.message || err) }); }
  }

  if (url.pathname === '/api/review') {
    const companyId = url.searchParams.get('company_id');
    if (!companyId) return sendJSON(res, 400, { error: 'pass ?company_id=…' });
    try { return sendJSON(res, 200, await buildReview(companyId)); }
    catch (err) { return sendJSON(res, 502, { error: String(err.message || err) }); }
  }

  res.writeHead(404).end('not found');
});

server.listen(PORT, () => {
  console.log(`\n  ◨ Under Appeal  →  http://localhost:${PORT}`);
  console.log(`  Proxying SignalScout API: ${API}`);
  console.log(`  Litigation: live /bills/{id}/litigation-cases, seed overlay when empty (${SEED_CASES.length} real cases)\n`);
});
