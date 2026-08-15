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
  //
  // region=all, added deliberately. This used to omit the region param, which the API reads as
  // US-ONLY — so the "whole corpus" snapshot silently held ~1,535 of ~2,335 relevant bills, and
  // every non-US row was missing from the fallback that the homepage, /states and every
  // jurisdiction profile rely on. Those surfaces all ask the live API for regions=all, so the
  // snapshot has to be the same superset or it is not a fallback, it is a different dataset.
  // It is also now the PRIMARY source for those reads (see hooks/useBills.ts), which makes the
  // completeness load-bearing rather than merely nice.
  { name: 'bills', path: '/bills?ce_relevant=true&region=all&limit=5000' },
  { name: 'map-summary', path: '/bills/map-summary' },
  // Only the ungated deadline COUNTS are baked. The deadline rows are Pro-gated server-side, so we
  // deliberately do NOT snapshot /bills/deadlines/upcoming (an unauthenticated build would only get
  // the public 5-row teaser anyway, and the CDN must not serve the paid calendar). See C-1.
  { name: 'deadlines-summary', path: '/bills/deadlines/summary?days_ahead=1095' },
  // Federal actions and litigation are CAP_FEDERAL. They used to be baked here in full, which quietly
  // made /data/federal-actions.json a public copy of the paid dataset — the frontend lock on /federal
  // was guarding a door next to an open window. Only the ungated counts are snapshotted now, exactly
  // as with deadlines above. The litigation feed has no free surface, so it isn't snapshotted at all.
  { name: 'federal-summary', path: '/federal-actions/summary' },
  { name: 'companies', path: '/companies?limit=200' },
];

const TIMEOUT_MS = 30_000;

// Sanity floors, by snapshot name. A snapshot that comes back implausibly short is WORSE than one
// that fails outright: a failure is logged and the file is skipped (the frontend falls back to live),
// while a short file is written, cached, and served from the CDN as if it were the whole corpus.
// That is the failure mode this guards — e.g. an API-side limit cap, a bad region default, or a
// half-migrated database quietly halving what the homepage shows for a whole deploy cycle.
// 2000 is chosen against the specific regression it has to catch, not as a round number. Dropping
// `region=all` yields the US-only corpus — 1,576 rows against 2,493 for every region, measured on
// prod 2026-08-15 — so a floor below that would sail straight past the exact bug this guards. The
// corpus only grows (37 regions and counting), so the headroom is in the safe direction.
const MIN_ROWS = { bills: 2000 };

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
      const floor = MIN_ROWS[name];
      if (floor !== undefined && (!Array.isArray(data) || data.length < floor)) {
        // Thrown, not warned: this takes the same path as a failed fetch, so the short file is never
        // written and the frontend degrades to live instead of serving a truncated corpus as truth.
        throw new Error(`only ${Array.isArray(data) ? data.length : 'non-array'} rows, expected >= ${floor}`);
      }
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
