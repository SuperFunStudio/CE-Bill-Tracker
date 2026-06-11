'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchDeadlines } from '@/lib/api';
import { resilient, getSnapshot } from '@/lib/snapshot';
import type { DeadlineParams, DeadlineSummary } from '@/lib/types';

export function useDeadlines(params?: DeadlineParams) {
  return useQuery({
    queryKey: ['deadlines', params],
    queryFn: () => resilient('deadlines', () => fetchDeadlines(params)),
    placeholderData: () => getSnapshot<DeadlineSummary[]>('deadlines') ?? undefined,
    staleTime: 5 * 60 * 1000,
  });
}
