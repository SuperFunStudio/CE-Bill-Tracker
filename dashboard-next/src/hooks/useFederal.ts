'use client';
import { useQuery } from '@tanstack/react-query';
import {
  fetchFederalActions,
  fetchFederalSummary,
  fetchPreemptionRisk,
  fetchLitigationCases,
  fetchLitigationCase,
} from '@/lib/api';
import { resilient, getSnapshot } from '@/lib/snapshot';
import { CAP, useAuth } from '@/components/auth/AuthContext';
import type { FederalActionParams, FederalActionStats } from '@/lib/types';

const STALE = 5 * 60 * 1000;

/** The federal action ROWS — CAP_FEDERAL. A caller without it gets a short teaser from the server,
 *  so this hook is only worth mounting behind the /federal page's lock.
 *
 *  No snapshot fallback any more: the CDN used to carry the full list, which is precisely how the
 *  paid dataset ended up publicly readable at /data/federal-actions.json. A gated feed cannot have a
 *  static fallback — the fallback is by definition unauthenticated. */
export function useFederalActions(params?: FederalActionParams) {
  const { hasCapability, getToken } = useAuth();
  const entitled = hasCapability(CAP.FEDERAL);
  return useQuery({
    // Keyed on `entitled`, and NOT routed through the snapshot cache — that store is auth-agnostic,
    // so a Pro seat's full list cached there could surface in a later free session on the same
    // browser. Same reasoning as useDeadlines.
    queryKey: ['federalActions', params, entitled],
    queryFn: async () => fetchFederalActions(params, entitled ? await getToken() : null),
    staleTime: STALE,
  });
}

/** Ungated federal counts for the free surfaces (homepage preemption banner, Standings rollup).
 *  These only ever needed two integers; they were pulling up to 500 gated rows to derive them. */
export function useFederalSummary() {
  return useQuery({
    queryKey: ['federalSummary'],
    queryFn: () => resilient('federal-summary', fetchFederalSummary),
    placeholderData: () => getSnapshot<FederalActionStats>('federal-summary') ?? undefined,
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

/** The bulk litigation feed — CAP_FEDERAL, hard 403 without it. Snapshot fallback removed for the
 *  same reason as the actions list: a static copy of gated data is not a fallback, it's a leak.
 *  Per-bill litigation (useBillLitigationCases) is unaffected and stays free. */
export function useLitigationCases() {
  const { hasCapability, getToken } = useAuth();
  const entitled = hasCapability(CAP.FEDERAL);
  return useQuery({
    queryKey: ['litigationCases', entitled],
    // 403s without the capability, so don't even ask — an unentitled caller only reaches this hook
    // from the /federal page, which is already showing its lock card.
    enabled: entitled,
    queryFn: async () => fetchLitigationCases(await getToken()),
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
