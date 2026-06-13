'use client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { ThemeProvider } from './ThemeContext';
import { ScopeProvider } from '@/components/scope/ScopeContext';
import { AuthProvider } from '@/components/auth/AuthContext';
import { AuthModal } from '@/components/auth/AuthModal';
import { WatchlistProvider } from '@/components/watchlist/WatchlistContext';
import { hydrateSnapshots } from '@/lib/snapshot';

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,
        retry: 1,
      },
    },
  }));

  // Pull the CDN-baked snapshots into memory/localStorage so list views paint
  // last-known data instantly instead of flashing "0" during the API call.
  useEffect(() => {
    hydrateSnapshots();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <WatchlistProvider>
            <ScopeProvider>
              {children}
            </ScopeProvider>
          </WatchlistProvider>
          <AuthModal />
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
