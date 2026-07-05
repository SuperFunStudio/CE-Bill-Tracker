// Comply by Friday — zero-dependency Node server.
//
// Two jobs:
//   1. Serve the static UI (public/index.html).
//   2. Compose SignalScout's raw feeds into a dated action plan (/api/plan).
//
// The composition engine is the actual product here: SignalScout's API is rich on
// *data* (what laws exist, what their deadlines are, which PRO runs each program) but
// thin on *decisions*. This turns three GETs into the one-pager a compliance lead
// would forward to their boss: "here's what to do, in date order, by when."

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 4310;
const API = process.env.SIGNALSCOUT_API || 'https://signalscout-api-36712717703.us-central1.run.app';

// ---- Domain knowledge: how SignalScout's action_type maps to a human next-step ----
// Tier ACT = a real obligation with a party you register/join/file with.
// Tier WATCH = no obligation yet, but rules/fees are coming.
// action_type 'none' is dropped — no next action to surface.
const ACTIONS = {
  join_pro:            { tier: 'act',   label: 'Join a producer responsibility org (PRO)' },
  register_with_state: { tier: 'act',   label: 'Register with the state program' },
  file_individual_plan:{ tier: 'act',   label: 'File an individual stewardship plan' },
  arrange_collection:  { tier: 'act',   label: 'Stand up a collection program' },
  report_to_program:   { tier: 'act',   label: 'File a report with the program' },
  monitor:             { tier: 'watch', label: 'Monitor for implementing rules / fees' },
};

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

function bucketFor(days) {
  if (days === null) return 'undated';
  if (days < 0) return 'overdue';
  if (days <= 30) return 'now';
  if (days <= 90) return 'soon';
  return 'later';
}

// Compose one state's pathways + the shared upcoming-deadlines feed into plan items.
function buildStateItems(state, pathways, deadlinesByBill, materials, today) {
  const wantMat = materials && materials.length
    ? new Set(materials.map((m) => m.toLowerCase()))
    : null;

  return pathways
    .map((p) => {
      const spec = ACTIONS[p.action_type];
      if (!spec) return null; // drops action_type 'none'

      const mats = p.material_categories || [];
      if (wantMat && !mats.some((m) => wantMat.has(String(m).toLowerCase()))) return null;

      // Explicit, richly-described deadline rows (from /bills/deadlines/upcoming)
      // beat the pathway's bare next_deadline_date when we have one for this bill.
      // Monitor (watch) laws carry a placeholder next_deadline_date (~today) that
      // isn't a real due date — drop it so they read as "no fixed date yet", not overdue.
      const explicit = deadlinesByBill.get(p.bill_id);
      const deadline = spec.tier === 'watch'
        ? (explicit?.deadline_date || null)
        : (explicit?.deadline_date || p.next_deadline_date || null);
      const days = daysUntil(deadline, today);

      return {
        state,
        bill_id: p.bill_id,
        bill_number: p.bill_number,
        bill_title: p.bill_title,
        materials: mats,
        tier: spec.tier,
        action_type: p.action_type,
        action_label: spec.label,
        action_summary: p.action_summary,
        registration_url: p.entity?.registration_url || p.registration_url || null,
        entity: p.entity ? { name: p.entity.name, type: p.entity.entity_type, url: p.entity.url } : null,
        has_fee: !!p.has_fee,
        deadline_date: deadline,
        deadline_type: explicit?.deadline_type || null,
        deadline_detail: explicit?.description || null,
        days_until: days,
        bucket: bucketFor(days),
      };
    })
    .filter(Boolean);
}

async function buildPlan({ states, materials }) {
  const today = Date.parse(new Date().toISOString().slice(0, 10)); // midnight-UTC of today

  // Shared feed: the soonest explicit deadlines across all states (free-tier teaser
  // returns the 5 nearest; noted as a limitation in the UI). Index by bill_id so we
  // can enrich any pathway that has a matching hard deadline.
  let deadlines = [];
  try { deadlines = await getJSON('/bills/deadlines/upcoming'); } catch { /* non-fatal */ }
  const deadlinesByBill = new Map();
  for (const d of deadlines) if (!deadlinesByBill.has(d.bill_id)) deadlinesByBill.set(d.bill_id, d);

  const perState = await Promise.all(
    states.map(async (st) => {
      const pathways = await getJSON(`/compliance/pathways?state=${encodeURIComponent(st)}`);
      return buildStateItems(st, pathways, deadlinesByBill, materials, today);
    }),
  );

  const items = perState.flat().sort((a, b) => {
    // Dated before undated; earlier deadline first; then acts before watches.
    if (a.deadline_date && !b.deadline_date) return -1;
    if (!a.deadline_date && b.deadline_date) return 1;
    if (a.deadline_date && b.deadline_date && a.deadline_date !== b.deadline_date)
      return a.deadline_date < b.deadline_date ? -1 : 1;
    if (a.tier !== b.tier) return a.tier === 'act' ? -1 : 1;
    return 0;
  });

  const acts = items.filter((i) => i.tier === 'act');
  return {
    generated_for: { states, materials: materials || [] },
    summary: {
      total: items.length,
      act: acts.length,
      watch: items.length - acts.length,
      overdue: items.filter((i) => i.bucket === 'overdue').length,
      within_30: items.filter((i) => i.bucket === 'now').length,
      within_90: items.filter((i) => ['now', 'soon'].includes(i.bucket)).length,
      next_deadline: acts.find((i) => i.deadline_date)?.deadline_date || null,
    },
    items,
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

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (url.pathname === '/' || url.pathname === '/index.html') return serveStatic(res);

  if (url.pathname === '/api/plan') {
    const states = (url.searchParams.get('states') || '')
      .split(',').map((s) => s.trim().toUpperCase()).filter(Boolean);
    const materials = (url.searchParams.get('materials') || '')
      .split(',').map((s) => s.trim()).filter(Boolean);
    if (!states.length) {
      res.writeHead(400, { 'content-type': 'application/json' });
      return res.end(JSON.stringify({ error: 'pass ?states=CA,OR' }));
    }
    try {
      const plan = await buildPlan({ states, materials });
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(JSON.stringify(plan));
    } catch (err) {
      res.writeHead(502, { 'content-type': 'application/json' });
      return res.end(JSON.stringify({ error: String(err.message || err) }));
    }
  }

  res.writeHead(404).end('not found');
});

server.listen(PORT, () => {
  console.log(`\n  Comply by Friday  →  http://localhost:${PORT}`);
  console.log(`  Proxying SignalScout API: ${API}\n`);
});
