'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchDeadlines, fetchDeadlineStats } from '@/lib/api';
import { resilient, getSnapshot } from '@/lib/snapshot';
import { useAuth } from '@/components/auth/AuthContext';
import type { DeadlineParams, DeadlineSummary, DeadlineStats } from '@/lib/types';

const STALE = 5 * 60 * 1000;

/**
 * The Upcoming Deadlines list. The server gates this: a Pro seat (token attached) gets the full merged
 * calendar, everyone else gets the soonest few rows as a teaser. We key the query on `pro` and DON'T
 * route it through the CDN-snapshot cache — that store is auth-agnostic, so caching a Pro user's full
 * list there could leak it into a later free session on the same browser. Counts come from the
 * ungated useDeadlineStats instead.
 */
export function useDeadlines(params?: DeadlineParams) {
  const { isPro, isAdmin, getToken } = useAuth();
  const pro = isPro || isAdmin;
  return useQuery({
    queryKey: ['deadlines', params, pro],
    queryFn: async () => fetchDeadlines(params, pro ? await getToken() : null),
    staleTime: STALE,
  });
}

/** Ungated aggregate counts — safe to snapshot for instant first paint / offline. */
export function useDeadlineStats(params?: DeadlineParams) {
  return useQuery({
    queryKey: ['deadlineStats', params],
    queryFn: () => resilient('deadlines-summary', () => fetchDeadlineStats(params)),
    placeholderData: () => getSnapshot<DeadlineStats>('deadlines-summary') ?? undefined,
    staleTime: STALE,
  });
}
