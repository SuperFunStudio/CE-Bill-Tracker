'use client';
import { useQuery } from '@tanstack/react-query';
import { fetchCompanies, fetchCompany, fetchExposureRanking, fetchExposureBrief } from '@/lib/api';

const STALE = 5 * 60 * 1000;

export function useCompanies(search?: string) {
  return useQuery({
    queryKey: ['companies', search],
    queryFn: () => fetchCompanies({ search, limit: 200 }),
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

export function useExposureBrief(companyId: string | null, billId: number | null) {
  return useQuery({
    queryKey: ['exposureBrief', companyId, billId],
    queryFn: () => fetchExposureBrief(companyId!, billId!),
    enabled: companyId !== null && billId !== null,
    staleTime: 10 * 60 * 1000, // 10 min — briefs are expensive to generate
  });
}
