'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchDeadlines } from '@/lib/api';
import type { DeadlineParams } from '@/lib/types';

export function useDeadlines(params?: DeadlineParams) {
  return useQuery({
    queryKey: ['deadlines', params],
    queryFn: () => fetchDeadlines(params),
    staleTime: 5 * 60 * 1000,
  });
}
