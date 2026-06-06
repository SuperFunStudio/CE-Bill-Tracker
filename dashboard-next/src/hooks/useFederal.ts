'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchFederalActions, fetchPreemptionRisk, fetchLitigationCases, fetchLitigationCase } from '@/lib/api';
import type { FederalActionParams } from '@/lib/types';

const STALE = 5 * 60 * 1000;

export function useFederalActions(params?: FederalActionParams) {
  return useQuery({
    queryKey: ['federalActions', params],
    queryFn: () => fetchFederalActions(params),
    staleTime: STALE,
  });
}

export function usePreemptionRisk() {
  return useQuery({
    queryKey: ['preemptionRisk'],
    queryFn: fetchPreemptionRisk,
    staleTime: STALE,
  });
}

export function useLitigationCases() {
  return useQuery({
    queryKey: ['litigationCases'],
    queryFn: fetchLitigationCases,
    staleTime: STALE,
  });
}

export function useLitigationCase(id: number | null) {
  return useQuery({
    queryKey: ['litigationCase', id],
    queryFn: () => fetchLitigationCase(id!),
    enabled: id !== null,
    staleTime: STALE,
  });
}
