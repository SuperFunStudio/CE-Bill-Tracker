#!/usr/bin/env node
/**
 * Compliance Cliff — the shareable EPR risk card.
 *
 * Hackathon build by "Maya" (design-technologist persona). One screen, no login:
 * type a company, get a screenshot-worthy card of its Extended Producer
 * Responsibility exposure — # of laws, states, nearest deadline, the statutory
 * penalty-per-day, and the annual-fee range — all grounded in the SignalScout API.
 *
 * Zero npm dependencies: Node's built-in http + global fetch (Node 18+).
 * The server is a thin CORS-killing proxy over two PUBLIC SignalScout endpoints:
 *   GET /companies?search=            -> resolve a name to a company id
 *   GET /companies/{id}/obligations   -> the grounded exposure payload (the card)
 *
 * Run:  node server.js        then open http://localhost:8787
 * Env:  SIGNALSCOUT_API_BASE_URL (defaults to prod), PORT (defaults to 8787).
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, extname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT) || 8787;
const API_BASE = (
  process.env.SIGNALSCOUT_API_BASE_URL ||
  "https://signalscout-api-36712717703.us-central1.run.app"
).replace(/\/$/, "");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8",
};

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  res.end(payload);
}

/** Proxy a GET to the SignalScout API and forward JSON (or a clean error). */
async function proxy(res, path) {
  const url = `${API_BASE}${path}`;
  try {
    const upstream = await fetch(url, { headers: { accept: "application/json" } });
    const text = await upstream.text();
    if (!upstream.ok) {
      return sendJson(res, upstream.status, {
        error: `SignalScout API ${upstream.status}`,
        detail: text.slice(0, 400),
      });
    }
    res.writeHead(200, {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    });
    res.end(text);
  } catch (err) {
    sendJson(res, 502, { error: "Upstream fetch failed", detail: String(err) });
  }
}

async function serveStatic(res, urlPath) {
  const rel = urlPath === "/" ? "/index.html" : urlPath;
  const filePath = join(__dirname, "public", rel);
  // Guard against path traversal.
  if (!filePath.startsWith(join(__dirname, "public"))) {
    res.writeHead(403);
    return res.end("Forbidden");
  }
  try {
    const data = await readFile(filePath);
    res.writeHead(200, { "content-type": MIME[extname(filePath)] || "application/octet-stream" });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end("Not found");
  }
}

const server = createServer(async (req, res) => {
  const u = new URL(req.url, `http://localhost:${PORT}`);

  // --- API proxy routes ---
  if (u.pathname === "/api/search") {
    const q = (u.searchParams.get("q") || "").trim();
    if (!q) return sendJson(res, 200, []);
    return proxy(res, `/companies?search=${encodeURIComponent(q)}&limit=8`);
  }
  if (u.pathname === "/api/obligations") {
    const id = (u.searchParams.get("id") || "").trim();
    if (!id) return sendJson(res, 400, { error: "Missing id" });
    // Basic UUID sanity check before hitting upstream.
    if (!/^[0-9a-f-]{36}$/i.test(id)) return sendJson(res, 400, { error: "Bad id" });
    return proxy(res, `/companies/${id}/obligations`);
  }

  // --- static files ---
  return serveStatic(res, u.pathname);
});

server.listen(PORT, () => {
  console.log(`\n  🪨  Compliance Cliff  →  http://localhost:${PORT}`);
  console.log(`      proxying SignalScout API at ${API_BASE}\n`);
});
