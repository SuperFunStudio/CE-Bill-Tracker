#!/usr/bin/env node
/**
 * EPR Nutrition Label — hackathon entry by "Priya" (design 55 / business 30 / dev 15).
 *
 * Zero-dependency Node server:
 *   - serves the static label UI from ./public
 *   - GET /api/label?materials=a,b&states=CA,CO&regions=EU  → aggregated "Regulation Facts"
 *
 * The browser can't call the SignalScout API directly (CORS allows only the dashboard
 * origins), so this proxies server-side. One pathways call per jurisdiction — the
 * pathways response doesn't carry state/region, so per-jurisdiction calls are how we
 * know which obligations belong where.
 *
 * Run:    node server.js          → http://localhost:4747
 * Config: SIGNALSCOUT_API_BASE_URL (defaults to prod), PORT
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

const API_BASE = (
  process.env.SIGNALSCOUT_API_BASE_URL ||
  "https://signalscout-api-36712717703.us-central1.run.app"
).replace(/\/$/, "");
const PORT = Number(process.env.PORT || 4747);
const PUBLIC_DIR = path.join(__dirname, "public");

// ---------------------------------------------------------------- API client

async function fetchJson(apiPath, params) {
  const url = new URL(API_BASE + apiPath);
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`SignalScout ${res.status} on ${apiPath}${body ? `: ${body.slice(0, 200)}` : ""}`);
  }
  return res.json();
}

/**
 * Prod (pre multi-region promotion) ignores the `region` query param and returns every
 * pathway — which would silently attribute US obligations to EU/FR/JP. Probe once:
 * a region-aware API returns [] for an impossible region; a legacy one returns everything.
 */
let regionAwareProbe = null;
function apiIsRegionAware() {
  regionAwareProbe ??= fetchJson("/compliance/pathways", { region: "ZZ" })
    .then((rows) => rows.length === 0)
    .catch(() => false);
  return regionAwareProbe;
}

// ------------------------------------------------------------- label builder

/** Same material-overlap rule as the compliance-copilot MCP, plus the "ALL" wildcard. */
function overlaps(billMats, wanted) {
  if (!wanted.length) return true;
  if (!billMats || !billMats.length) return false;
  const set = new Set(billMats.map((s) => s.toLowerCase()));
  if (set.has("all")) return true;
  return wanted.some((m) => set.has(m.toLowerCase()));
}

const ACTION_PHRASES = {
  join_pro: "PRO registration",
  file_individual_plan: "individual compliance plan",
  register_with_state: "state registration",
  monitor: "regulatory monitoring",
};

function daysUntil(iso) {
  const d = new Date(iso + "T00:00:00Z");
  return Math.ceil((d.getTime() - Date.now()) / 86400000);
}

async function buildLabel(query) {
  const csv = (s) => (s || "").split(",").map((t) => t.trim()).filter(Boolean);
  const materials = csv(query.materials).map((m) => m.toLowerCase());
  const states = csv(query.states).map((s) => s.toUpperCase());
  const regions = csv(query.regions).map((r) => r.toUpperCase());

  const jurisdictions = [
    ...states.map((s) => ({ code: s, kind: "state", params: { state: s } })),
    ...regions.map((r) => ({ code: r, kind: "region", params: { region: r } })),
  ];
  if (!jurisdictions.length) throw Object.assign(new Error("Pick at least one market."), { status: 400 });
  if (jurisdictions.length > 30) throw Object.assign(new Error("30 markets max."), { status: 400 });

  const regionAware = regions.length ? await apiIsRegionAware() : true;

  const settled = await Promise.allSettled(
    jurisdictions.map((j) =>
      j.kind === "region" && !regionAware
        ? Promise.resolve(null) // legacy API: don't attribute the unfiltered firehose to this region
        : fetchJson("/compliance/pathways", j.params),
    ),
  );

  const perJurisdiction = [];
  const allDeadlines = [];
  const contains = new Set();
  const entities = new Set();
  let totalObligations = 0;
  let feeCount = 0;

  jurisdictions.forEach((j, i) => {
    const s = settled[i];
    if (s.status === "fulfilled" && s.value === null) {
      perJurisdiction.push({ code: j.code, kind: j.kind, unsupported: true, obligations: 0, actions: [] });
      return;
    }
    if (s.status !== "fulfilled") {
      perJurisdiction.push({ code: j.code, kind: j.kind, error: true, obligations: 0, actions: [] });
      return;
    }
    const pathways = s.value
      .filter((p) => overlaps(p.material_categories, materials))
      .sort((a, b) => {
        if (a.next_deadline_date === b.next_deadline_date) return 0;
        if (!a.next_deadline_date) return 1;
        if (!b.next_deadline_date) return -1;
        return a.next_deadline_date < b.next_deadline_date ? -1 : 1;
      });

    let jFees = 0;
    for (const p of pathways) {
      totalObligations += 1;
      if (p.has_fee) { jFees += 1; feeCount += 1; contains.add("producer fees"); }
      if (ACTION_PHRASES[p.action_type]) contains.add(ACTION_PHRASES[p.action_type]);
      if (p.entity?.name) entities.add(p.entity.name);
      if (p.next_deadline_date && daysUntil(p.next_deadline_date) >= 0) {
        allDeadlines.push({ date: p.next_deadline_date, code: j.code, bill: p.bill_number });
      }
    }

    perJurisdiction.push({
      code: j.code,
      kind: j.kind,
      obligations: pathways.length,
      fees: jFees,
      nextDeadline: pathways.find((p) => p.next_deadline_date)?.next_deadline_date || null,
      actions: pathways.slice(0, 3).map((p) => ({
        actionType: p.action_type,
        summary: p.action_summary,
        bill: p.bill_number,
        entity: p.entity?.name || null,
        registrationUrl: p.registration_url || p.entity?.registration_url || null,
        deadline: p.next_deadline_date,
        hasFee: p.has_fee,
      })),
    });
  });

  allDeadlines.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const soonest = allDeadlines[0] || null;

  return {
    generatedAt: new Date().toISOString(),
    apiBase: API_BASE,
    materials,
    totals: {
      obligations: totalObligations,
      jurisdictions: jurisdictions.length,
      jurisdictionsWithObligations: perJurisdiction.filter((j) => j.obligations > 0).length,
      fees: feeCount,
      deadlinesWithin30: allDeadlines.filter((d) => daysUntil(d.date) <= 30).length,
      deadlinesWithin90: allDeadlines.filter((d) => daysUntil(d.date) <= 90).length,
      soonestDeadline: soonest && { ...soonest, daysAway: daysUntil(soonest.date) },
    },
    contains: [...contains].sort(),
    entities: [...entities].sort(),
    jurisdictions: perJurisdiction,
  };
}

// ---------------------------------------------------------------- web server

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png" };

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === "/api/label") {
    try {
      const label = await buildLabel(Object.fromEntries(url.searchParams));
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(label));
    } catch (err) {
      res.writeHead(err.status || 502, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  // static files (default to index.html; refuse path traversal)
  const rel = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  const file = path.join(PUBLIC_DIR, rel);
  if (!file.startsWith(PUBLIC_DIR)) { res.writeHead(403); res.end(); return; }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end("Not found"); return; }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`EPR Nutrition Label → http://localhost:${PORT}  (API: ${API_BASE})`);
});
