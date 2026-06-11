'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchBills, fetchBill, fetchMapSummary, fetchBillLitigationCases } from '@/lib/api';
import { resilient, getSnapshot } from '@/lib/snapshot';
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

export function useBill(id: number | null) {
  return useQuery({
    queryKey: ['bill', id],
    queryFn: () => fetchBill(id!),
    enabled: id !== null,
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
