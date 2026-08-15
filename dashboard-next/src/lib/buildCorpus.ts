import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fetchBills } from '@/lib/api';
import type { BillSummary } from '@/lib/types';

/**
 * The whole ce_relevant corpus, for BUILD-TIME consumers only (sitemap generation and the bill
 * pages' generateStaticParams). Server-side: this imports node:fs and must never reach a client
 * bundle.
 *
 * Reads public/data/bills.json off disk in preference to calling the API. cloudbuild.yaml runs
 * scripts/build-snapshot.mjs immediately before `npm run build` in the same step, so by the time
 * Next evaluates these the file is already there — written from the exact same query. Both callers
 * were separately re-fetching the full 2.6 MB corpus from Cloud Run during the build, which made
 * three identical whole-corpus requests per deploy and put the build on the critical path of an API
 * that had just been redeployed and was likely cold.
 *
 * Falls back to the live API when the file is absent (a local `next build` with no snapshot step, or
 * a build where the snapshot failed), so this is a shortcut, never a new dependency. Both callers
 * already tolerate an empty result — the sitemap degrades to static paths, and generateStaticParams
 * to no pre-rendered bill pages.
 */
export async function loadBuildCorpus(): Promise<BillSummary[]> {
  const file = resolve(process.cwd(), 'public', 'data', 'bills.json');
  try {
    const raw = await readFile(file, 'utf8');
    const rows = JSON.parse(raw) as BillSummary[];
    if (Array.isArray(rows) && rows.length) {
      console.log(`[build] corpus from snapshot: ${rows.length} bills (${file})`);
      return rows;
    }
    console.warn('[build] snapshot present but empty — falling back to the live API');
  } catch {
    console.warn('[build] no bills snapshot on disk — falling back to the live API');
  }
  return fetchBills({ ce_relevant: true, region: 'all', limit: 5000 });
}
