'use client';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchBills, fetchBill, fetchBillText, fetchBillSearch, fetchBillTextCoverage, fetchMapSummary, fetchBillLitigationCases } from '@/lib/api';
import { resilient, getSnapshot } from '@/lib/snapshot';
import { useDebouncedValue } from './useDebouncedValue';
import type { BillParams, BillSummary, StateMapSummary } from '@/lib/types';

const STALE = 5 * 60 * 1000; // 5 min — mirrors Streamlit ttl=300

export function useBills(params?: BillParams) {
  return useQuery({
    queryKey: ['bills', params],
    queryFn: () => resilient('bills', () => fetchBills(params)),
    placeholderData: () => getSnapshot<BillSummary[]>('bills') ?? undefined,
    staleTime: STALE,
  });
}

/** Live full-text search over persisted bill text. Debounced so it doesn't fire per keystroke;
 *  disabled until the (trimmed) term is ≥2 chars; keepPreviousData avoids flicker between queries.
 *  This is the opt-in "deep search" layer — the instant title/summary filter stays client-side. */
export function useBillTextSearch(query: string) {
  const q = useDebouncedValue(query.trim(), 300);
  return useQuery({
    queryKey: ['billTextSearch', q],
    queryFn: () => fetchBillSearch(q, 50),
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
