'use client';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchBills, fetchBill, fetchBillText, fetchBillSearch, fetchBillTextCoverage, fetchMapSummary, fetchBillLitigationCases, fetchLawsInForce, fetchBillTimeline } from '@/lib/api';
import { resilient, getSnapshot, loadSnapshot } from '@/lib/snapshot';
import { useDebouncedValue } from './useDebouncedValue';
import type { BillParams, BillSummary, StateMapSummary } from '@/lib/types';

const STALE = 5 * 60 * 1000; // 5 min — mirrors Streamlit ttl=300

/** Enacted CE laws in force, grouped by (year, region) — the source the homepage globe shades from.
 *  Shared here so the "Top Regions" ticker ranks by the SAME numbers the globe does (combined
 *  national + sub-national enacted, since a US state law is region="US"). No `regions` → every region. */
export function useLawsInForce(regions?: string) {
  return useQuery({
    queryKey: ['lawsInForce', regions ?? 'all'],
    queryFn: () => fetchLawsInForce(regions ? { regions } : undefined),
    staleTime: STALE,
  });
}

// ── Whole-corpus reads: served from the CDN, not the origin ──────────────────────────────────────
//
// Fourteen call sites ask for `{ce_relevant: true, limit: 5000}` — the homepage, /states, every
// jurisdiction profile, the library, the embed, the Sankey. Each one was a live 2.6 MB round-trip to
// Cloud Run per visitor (355 KB gzipped), for a corpus that changes on an hourly ingestion cadence at
// best. The build already bakes exactly that query to public/data/bills.json for the CDN; it was
// being used only as a FALLBACK, so the expensive path was the default one and the cheap, correct
// path only ran when the API was down.
//
// This inverts it for whole-corpus reads: snapshot first, live only if the file is missing. The API
// stays the source of truth for everything narrower — including any filter the snapshot can't answer.
//
// It also takes browsers off the origin's bulk path, which is the precondition for ever capping bulk
// reads server-side: today an anonymous `limit=5000` cannot be refused, because our own public pages
// are the loudest thing making that request.

/** The corpus snapshot's own shape: ce_relevant, every region (see scripts/build-snapshot.mjs). */
const CORPUS_LIMIT = 1000;

/**
 * Can this query be answered from the baked corpus?
 *
 * Deliberately conservative — it must be a superset question, never a narrower one. `region`/`regions`
 * are allowed because they filter rows the snapshot already holds and are re-applied below; anything
 * else (state, status, instrument_type, dimensions, date ranges…) goes live, because a wrong "yes"
 * here silently returns unfiltered rows rather than an error. `dimensions` in particular CANNOT be
 * answered locally: it filters on compliance_details, which the list payload doesn't carry.
 */
function isCorpusQuery(p?: BillParams): boolean {
  if (!p || p.ce_relevant !== true || (p.limit ?? 0) < CORPUS_LIMIT) return false;
  const answerable = new Set(['ce_relevant', 'limit', 'region', 'regions']);
  return Object.entries(p).every(
    ([k, v]) => v === undefined || v === null || v === '' || answerable.has(k),
  );
}

/**
 * Re-apply the API's region semantics to snapshot rows. Mirrors list_bills in app/api/bills.py:
 * `regions` (CSV) wins when present and "all"/empty means no filter; otherwise a missing `region`
 * means US-ONLY, and an explicit code filters to it. Getting this wrong is how a jurisdiction page
 * shows "0 tracked bills", so it follows the server branch-for-branch.
 */
function applyRegion(rows: BillSummary[], p?: BillParams): BillSummary[] {
  const all = (csv: string) => csv.split(',').map((r) => r.trim().toUpperCase()).filter(Boolean);
  if (p?.regions) {
    const codes = all(p.regions);
    if (!codes.length || codes.includes('ALL')) return rows;
    return rows.filter((b) => codes.includes((b.region ?? '').toUpperCase()));
  }
  if (!p?.region) return rows.filter((b) => (b.region ?? 'US').toUpperCase() === 'US');
  if (p.region.toLowerCase() === 'all') return rows;
  return rows.filter((b) => (b.region ?? '').toUpperCase() === p.region!.toUpperCase());
}

export function useBills(params?: BillParams) {
  const corpus = isCorpusQuery(params);
  return useQuery({
    queryKey: ['bills', params],
    queryFn: async () => {
      if (corpus) {
        // getSnapshot covers the common case (hydrateSnapshots ran at boot); loadSnapshot re-reads
        // the CDN file when this query beats hydration, so a first paint doesn't fall through to a
        // live corpus fetch just because it lost a race.
        const baked = getSnapshot<BillSummary[]>('bills') ?? (await loadSnapshot<BillSummary[]>('bills'));
        if (baked) return applyRegion(baked, params);
      }
      return resilient('bills', () => fetchBills(params));
    },
    placeholderData: () => {
      const baked = getSnapshot<BillSummary[]>('bills');
      return baked ? (corpus ? applyRegion(baked, params) : baked) : undefined;
    },
    staleTime: STALE,
  });
}

/** Live full-text search over persisted bill text. Debounced so it doesn't fire per keystroke;
 *  disabled until the (trimmed) term is ≥2 chars; keepPreviousData avoids flicker between queries.
 *  This is the opt-in "deep search" layer — the instant title/summary filter stays client-side. */
export function useBillTextSearch(query: string, regions?: string) {
  const q = useDebouncedValue(query.trim(), 300);
  return useQuery({
    queryKey: ['billTextSearch', q, regions ?? 'all'],
    queryFn: () => fetchBillSearch(q, 50, regions),
    enabled: q.length >= 2,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

/** Full-text index coverage (indexed vs. total bills) for the deep-search honesty note. Cached long;
 *  on environments where the index isn't populated yet it returns indexed_bills: 0. */
export function useBillTextCoverage() {
  return useQuery({
    queryKey: ['billTextCoverage'],
    queryFn: fetchBillTextCoverage,
    staleTime: STALE,
  });
}

export function useBill(id: number | null) {
  return useQuery({
    queryKey: ['bill', id],
    queryFn: () => fetchBill(id!),
    enabled: id !== null,
    staleTime: STALE,
  });
}

/** A bill's persisted full statute text. Lazy — pass enabled:false until the reader opens the viewer,
 *  so the (potentially large) text isn't fetched just because the modal opened. */
export function useBillText(id: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ['billText', id],
    queryFn: () => fetchBillText(id!),
    enabled: id !== null && enabled,
    staleTime: STALE,
  });
}

/** Per-year × status × region bill counts — a server-side aggregate, so it's cheap enough to ask for
 *  just to count things. The pricing page's coverage ledger sums it rather than hardcoding totals,
 *  which is the only way those figures stay true as the corpus grows. */
export function useBillTimeline(params?: { instrument_type?: string; material_category?: string; regions?: string }) {
  return useQuery({
    queryKey: ['billTimeline', params ?? null],
    queryFn: () => fetchBillTimeline(params),
    staleTime: STALE,
  });
}

export function useMapSummary() {
  return useQuery({
    queryKey: ['mapSummary'],
    queryFn: () => resilient('map-summary', fetchMapSummary),
    placeholderData: () => getSnapshot<StateMapSummary[]>('map-summary') ?? undefined,
    staleTime: STALE,
  });
}

export function useBillLitigationCases(billId: number | null) {
  return useQuery({
    queryKey: ['billLitigationCases', billId],
    queryFn: () => fetchBillLitigationCases(billId!),
    enabled: billId !== null,
    staleTime: STALE,
  });
}
