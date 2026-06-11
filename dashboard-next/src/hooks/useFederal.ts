'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchFederalActions, fetchPreemptionRisk, fetchLitigationCases, fetchLitigationCase } from '@/lib/api';
import { resilient, getSnapshot } from '@/lib/snapshot';
import type { FederalActionParams, FederalActionSummary, LitigationCaseSummary } from '@/lib/types';

const STALE = 5 * 60 * 1000;

export function useFederalActions(params?: FederalActionParams) {
  return useQuery({
    queryKey: ['federalActions', params],
    queryFn: () => resilient('federal-actions', () => fetchFederalActions(params)),
    placeholderData: () => getSnapshot<FederalActionSummary[]>('federal-actions') ?? undefined,
    staleTime: STALE,
  });
}

export function usePreemptionRisk() {
  // No snapshot: /federal-actions/preemption-risk isn't a real backend route (this hook
  // is currently unused). Left as a plain live call rather than baking a 404 into the CDN.
  return useQuery({
    queryKey: ['preemptionRisk'],
    queryFn: fetchPreemptionRisk,
    staleTime: STALE,
  });
}

export function useLitigationCases() {
  return useQuery({
    queryKey: ['litigationCases'],
    queryFn: () => resilient('litigation-cases', fetchLitigationCases),
    placeholderData: () => getSnapshot<LitigationCaseSummary[]>('litigation-cases') ?? undefined,
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
