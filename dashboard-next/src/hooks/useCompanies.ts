'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchCompanies, fetchCompany, fetchExposureRanking, fetchExposureBrief, fetchCompanyObligations } from '@/lib/api';
import { resilient, getSnapshot } from '@/lib/snapshot';
import { useAuth } from '@/components/auth/AuthContext';
import type { CompanySummary } from '@/lib/types';

const STALE = 5 * 60 * 1000;

export function useCompanies(search?: string) {
  return useQuery({
    queryKey: ['companies', search],
    // Only the unfiltered list is snapshotted; a search term needs the live API.
    queryFn: () =>
      search
        ? fetchCompanies({ search, limit: 200 })
        : resilient('companies', () => fetchCompanies({ limit: 200 })),
    placeholderData: () => (search ? undefined : getSnapshot<CompanySummary[]>('companies') ?? undefined),
    staleTime: STALE,
  });
}

export function useCompany(id: string | null) {
  return useQuery({
    queryKey: ['company', id],
    queryFn: () => fetchCompany(id!),
    enabled: id !== null,
    staleTime: STALE,
  });
}

export function useExposureRanking(billId?: number, limit = 50) {
  return useQuery({
    queryKey: ['exposureRanking', billId, limit],
    queryFn: () => fetchExposureRanking(billId, limit),
    enabled: billId !== undefined,
    staleTime: STALE,
  });
}

export function useCompanyObligations(companyId: string | null) {
  return useQuery({
    queryKey: ['companyObligations', companyId],
    queryFn: () => fetchCompanyObligations(companyId!),
    enabled: companyId !== null,
    staleTime: STALE,
  });
}

export function useExposureBrief(companyId: string | null, billId: number | null) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ['exposureBrief', companyId, billId],
    queryFn: async () => fetchExposureBrief(companyId!, billId!, await getToken()),
    enabled: companyId !== null && billId !== null,
    staleTime: 10 * 60 * 1000, // 10 min — briefs are expensive to generate
  });
}
