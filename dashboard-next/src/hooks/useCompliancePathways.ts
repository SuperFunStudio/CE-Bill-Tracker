'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchCompliancePathways } from '@/lib/api';

/**
 * Per-state compliance pathways (one per enacted EPR law). Not part of the baked snapshot
 * layer — it's small and state-scoped — so an unreachable API just yields an empty section
 * rather than a stale fallback. `enabled` lets the caller hold off until a state is known.
 */
export function useCompliancePathways(state: string | undefined) {
  return useQuery({
    queryKey: ['compliance-pathways', state],
    queryFn: () => fetchCompliancePathways(state as string),
    enabled: !!state,
    staleTime: 5 * 60 * 1000,
  });
}
