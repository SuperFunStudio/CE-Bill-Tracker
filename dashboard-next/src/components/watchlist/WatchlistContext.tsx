'use client';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useAuth } from '@/components/auth/AuthContext';
import { startProCheckout, billingErrorMessage } from '@/lib/billing';
import { getWatchlist, addWatch, removeWatch } from '@/lib/userSettings';

interface WatchlistValue {
  /** Bill ids the signed-in Pro user follows. Empty for anonymous / Free. */
  watched: Set<number>;
  ready: boolean;
  isWatched: (billId: number) => boolean;
  /** Toggle a bill. Routes anonymous users to sign-in and Free users to the Pro upgrade. */
  toggle: (billId: number) => Promise<void>;
  refresh: () => Promise<void>;
}

const WatchlistCtx = createContext<WatchlistValue | null>(null);

export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const { user, isPro, openAuth, getToken, showToast } = useAuth();
  const [watched, setWatched] = useState<Set<number>>(new Set());
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    if (!user || !isPro) {
      setWatched(new Set());
      setReady(true);
      return;
    }
    try {
      const ids = await getWatchlist(await getToken());
      setWatched(new Set(ids));
    } catch {
      setWatched(new Set());
    } finally {
      setReady(true);
    }
  }, [user, isPro, getToken]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggle = useCallback(
    async (billId: number) => {
      if (!user) {
        openAuth();
        return;
      }
      if (!isPro) {
        // Watch lists are a Pro feature — send them to checkout. Toast on failure so the star
        // click isn't a dead end if checkout can't start.
        try {
          await startProCheckout(getToken);
        } catch (e) {
          showToast(billingErrorMessage(e));
        }
        return;
      }
      const has = watched.has(billId);
      // Optimistic update, reconcile on failure.
      setWatched(prev => {
        const next = new Set(prev);
        if (has) next.delete(billId);
        else next.add(billId);
        return next;
      });
      try {
        const token = await getToken();
        if (has) await removeWatch(token, billId);
        else await addWatch(token, billId);
      } catch {
        setWatched(prev => {
          const next = new Set(prev);
          if (has) next.add(billId);
          else next.delete(billId);
          return next;
        });
      }
    },
    [user, isPro, watched, openAuth, getToken, showToast],
  );

  return (
    <WatchlistCtx.Provider
      value={{ watched, ready, isWatched: id => watched.has(id), toggle, refresh }}
    >
      {children}
    </WatchlistCtx.Provider>
  );
}

export function useWatchlist(): WatchlistValue {
  const ctx = useContext(WatchlistCtx);
  if (!ctx) throw new Error('useWatchlist must be used within WatchlistProvider');
  return ctx;
}
