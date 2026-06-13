'use client';
import { useState } from 'react';
import { useWatchlist } from './WatchlistContext';
import { useAuth } from '@/components/auth/AuthContext';
import { StarIcon } from '@/components/ui/icons';

/** A follow/unfollow star for a bill. Stops row-click propagation; routes anon→sign-in, non-Pro→upgrade. */
export function WatchStar({ billId, className }: { billId: number; className?: string }) {
  const { isWatched, toggle } = useWatchlist();
  const { user, isPro } = useAuth();
  const [busy, setBusy] = useState(false);
  const watched = isWatched(billId);

  const title = watched
    ? 'Unwatch'
    : !user
      ? 'Sign in to watch bills'
      : isPro
        ? 'Watch this bill'
        : 'Watch lists are a Pro feature — upgrade';

  return (
    <button
      type="button"
      onClick={async e => {
        e.stopPropagation();
        setBusy(true);
        try {
          await toggle(billId);
        } finally {
          setBusy(false);
        }
      }}
      disabled={busy}
      title={title}
      aria-label={title}
      aria-pressed={watched}
      className={`p-1 leading-none transition-colors disabled:opacity-50 ${
        watched ? 'text-green-accent' : 'text-text-muted/50 hover:text-green-accent'
      } ${className ?? ''}`}
    >
      <StarIcon className="text-sm" />
    </button>
  );
}
