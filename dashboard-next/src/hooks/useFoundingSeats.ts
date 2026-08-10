'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchFoundingSeats } from '@/lib/api';
import { FOUNDING } from '@/lib/tiers';

/**
 * The founding-seat counter behind the pricing page's "N/50 remaining" line. Counted server-side from
 * stamped founding entitlements (GET /billing/founding-seats), so the number moves on its own as seats
 * sell instead of waiting for someone to edit a constant.
 *
 * Falls back to FOUNDING.claimed if the call fails — a pricing page that renders no seat line at all is
 * worse than one showing the last figure we knew to be true. Short stale time: this is the one number on
 * the page a visitor may watch, and it is a single COUNT(*).
 */
export function useFoundingSeats() {
  const { data } = useQuery({
    queryKey: ['foundingSeats'],
    queryFn: fetchFoundingSeats,
    staleTime: 60 * 1000,
  });
  const total = data?.total ?? FOUNDING.total;
  const claimed = Math.min(data?.claimed ?? FOUNDING.claimed, total);
  return { total, claimed, remaining: Math.max(total - claimed, 0) };
}
