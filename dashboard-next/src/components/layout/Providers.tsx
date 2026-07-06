'use client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { ThemeProvider } from './ThemeContext';
import { RegionProvider } from './RegionContext';
import { ScopeProvider } from '@/components/scope/ScopeContext';
import { AuthProvider } from '@/components/auth/AuthContext';
import { AuthModal } from '@/components/auth/AuthModal';
import { FarewellModal } from '@/components/auth/FarewellModal';
import { Toast } from '@/components/ui/Toast';
import { WatchlistProvider } from '@/components/watchlist/WatchlistContext';
import { BetaProvider } from '@/components/settings/BetaContext';
import { hydrateSnapshots, markClientReady } from '@/lib/snapshot';

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,
        retry: 1,
      },
    },
  }));

  // Bump once on mount to re-render the tree the instant snapshot reads become safe (below), so the
  // now-unlocked placeholderData paints last-known data without waiting on the live fetch.
  const [, setMounted] = useState(false);

  // Pull the CDN-baked snapshots into memory/localStorage so list views paint
  // last-known data instantly instead of flashing "0" during the API call. The snapshot getter stays
  // locked until after this first client render so hydration matches the empty server HTML (React
  // #418/#423); we unlock it here and force one re-render to restore the instant paint.
  useEffect(() => {
    markClientReady();
    setMounted(true);
    hydrateSnapshots();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <WatchlistProvider>
            <BetaProvider>
              <RegionProvider>
                <ScopeProvider>
                  {children}
                </ScopeProvider>
              </RegionProvider>
            </BetaProvider>
          </WatchlistProvider>
          <AuthModal />
          <FarewellModal />
          <Toast />
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
