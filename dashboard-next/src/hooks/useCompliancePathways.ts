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
    queryFn: () => fetchCompliancePathways({ state: state as string }),
    enabled: !!state,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Region-scoped compliance pathways for the self-serve "which laws apply to me" checker — every
 * enacted law in a region (US default, EU, or "all"), each with its next-step action + deadline.
 */
export function useRegionPathways(region: string) {
  return useQuery({
    queryKey: ['region-pathways', region],
    queryFn: () => fetchCompliancePathways({ region }),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Pathways scoped by an arbitrary {state | region | regions} shape — the general form used where a
 * caller has a multi-select region choice (the compliance checker) or a non-US jurisdiction (a
 * foreign profile passes {region: <country>}, a US state passes {state: <code>}). Pathways now exist
 * for every region, so this can reach far past the old US/EU-primary that useRegion() collapsed to.
 */
export function usePathwaysScoped(params: { state?: string; region?: string; regions?: string }) {
  return useQuery({
    queryKey: ['pathways-scoped', params.state ?? '', params.region ?? '', params.regions ?? ''],
    queryFn: () => fetchCompliancePathways(params),
    staleTime: 5 * 60 * 1000,
  });
}
