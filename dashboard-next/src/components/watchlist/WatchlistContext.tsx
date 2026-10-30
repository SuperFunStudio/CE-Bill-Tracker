'use client';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useAuth } from '@/components/auth/AuthContext';
import { getWatchlist, addWatch, removeWatch, WatchLimitError } from '@/lib/userSettings';
import { WatchLimitModal } from './WatchLimitModal';

/** Bills a free account can follow — mirrors FREE_WATCHLIST_LIMIT in app/api/user.py. */
export const FREE_WATCH_LIMIT = 5;

interface WatchlistValue {
  /** Bill ids the signed-in user follows (up to FREE_WATCH_LIMIT on a free account). Empty when anonymous. */
  watched: Set<number>;
  ready: boolean;
  isWatched: (billId: number) => boolean;
  /** Toggle a bill. Routes anonymous users to sign-in; a free account's star past the limit opens the soft prompt. */
  toggle: (billId: number) => Promise<void>;
  refresh: () => Promise<void>;
}

const WatchlistCtx = createContext<WatchlistValue | null>(null);

export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const { user, isPro, openAuth, getToken } = useAuth();
  const [watched, setWatched] = useState<Set<number>>(new Set());
  const [ready, setReady] = useState(false);
  const [limitOpen, setLimitOpen] = useState(false);

  const refresh = useCallback(async () => {
    if (!user) {
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
      const has = watched.has(billId);
      // A free account starts a tracker without paying; the star past the limit explains instead of
      // redirecting to checkout. The server enforces the same limit (caught below).
      if (!has && !isPro && watched.size >= FREE_WATCH_LIMIT) {
        setLimitOpen(true);
        return;
      }
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
      } catch (e) {
        setWatched(prev => {
          const next = new Set(prev);
          if (has) next.add(billId);
          else next.delete(billId);
          return next;
        });
        if (e instanceof WatchLimitError) setLimitOpen(true);
      }
    },
    [user, isPro, watched, openAuth, getToken],
  );

  return (
    <WatchlistCtx.Provider
      value={{ watched, ready, isWatched: id => watched.has(id), toggle, refresh }}
    >
      {children}
      {limitOpen && <WatchLimitModal limit={FREE_WATCH_LIMIT} onClose={() => setLimitOpen(false)} />}
    </WatchlistCtx.Provider>
  );
}

export function useWatchlist(): WatchlistValue {
  const ctx = useContext(WatchlistCtx);
  if (!ctx) throw new Error('useWatchlist must be used within WatchlistProvider');
  return ctx;
}
