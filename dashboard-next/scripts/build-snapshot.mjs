// Pre-renders the read-heavy list endpoints to static JSON under public/data/.
// These ship inside the Next static export and are served from the CDN, so the
// dashboard's first paint (and all client-side bill search) never waits on the
// Cloud Run API and never shows "0 bills". The live API still backs detail pages,
// company search, and exposure briefs — this only covers the summary lists.
//
// Run from the dashboard-next/ directory:
//   NEXT_PUBLIC_API_BASE_URL=https://…run.app node scripts/build-snapshot.mjs
//
// A failed endpoint is logged and skipped (its JSON simply isn't written) rather
// than aborting — the frontend degrades to live + localStorage for anything missing.

import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.SNAPSHOT_API_URL ?? 'http://localhost:8000';
const OUT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'data');

// name → API path. `name` is also the localStorage key and the snapshot file the
// frontend reads (lib/snapshot.ts SNAPSHOTS must list the same names).
const ENDPOINTS = [
  // The bills list no longer carries compliance_details (the paid extraction) — this is just the
  // public Bill Explorer metadata, safe to bake to the CDN.
  { name: 'bills', path: '/bills?epr_relevant=true&limit=5000' },
  { name: 'map-summary', path: '/bills/map-summary' },
  // Only the ungated deadline COUNTS are baked. The deadline rows are Pro-gated server-side, so we
  // deliberately do NOT snapshot /bills/deadlines/upcoming (an unauthenticated build would only get
  // the public 5-row teaser anyway, and the CDN must not serve the paid calendar). See C-1.
  { name: 'deadlines-summary', path: '/bills/deadlines/summary?days_ahead=1095' },
  { name: 'federal-actions', path: '/federal-actions?limit=100' },
  { name: 'litigation-cases', path: '/litigation-cases' },
  { name: 'companies', path: '/companies?limit=200' },
];

const TIMEOUT_MS = 30_000;

async function fetchJson(path) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API}${path}`, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  console.log(`[snapshot] source API: ${API}`);

  const counts = {};
  let ok = 0;

  for (const { name, path } of ENDPOINTS) {
    try {
      const data = await fetchJson(path);
      await writeFile(resolve(OUT_DIR, `${name}.json`), JSON.stringify(data));
      counts[name] = Array.isArray(data) ? data.length : null;
      ok += 1;
      console.log(`[snapshot] ✓ ${name}: ${counts[name] ?? 'object'} -> public/data/${name}.json`);
    } catch (err) {
      console.warn(`[snapshot] ✗ ${name} (${path}): ${err.message} — skipping`);
    }
  }

  // meta drives the "showing saved data as of …" hint in the UI.
  await writeFile(
    resolve(OUT_DIR, 'meta.json'),
    JSON.stringify({ generated_at: new Date().toISOString(), counts }),
  );

  console.log(`[snapshot] wrote ${ok}/${ENDPOINTS.length} endpoints + meta.json`);
  if (ok === 0) {
    // Nothing fetched — surface a non-zero exit so the build log flags it, but the
    // cloudbuild step swallows it with `|| true` so the deploy still proceeds.
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(`[snapshot] fatal: ${err.message}`);
  process.exitCode = 1;
});
