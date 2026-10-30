'use client';
import { useEffect } from 'react';
import Link from 'next/link';
import { ReferralUnlock } from '@/components/ui/ReferralUnlock';
import { StarIcon } from '@/components/ui/icons';
import { trackGateHit, track } from '@/lib/analytics';

/**
 * The soft wall on the star past the free limit. A free account follows up to FREE_WATCH_LIMIT bills;
 * past that the star opens this instead of a cold Stripe checkout (which is where people used to
 * leave). It says what happened, that their bills are kept, and offers the free month for sharing
 * before any plan.
 */
export function WatchLimitModal({ limit, onClose }: { limit: number; onClose: () => void }) {
  useEffect(() => {
    trackGateHit('pro', 'soft_prompt', 'watchlist_limit');
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="watch-limit-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md space-y-5 rounded-xl border border-border-default bg-bg-secondary p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="space-y-2">
          <StarIcon className="text-2xl text-green-accent" />
          <h2 id="watch-limit-title" className="font-serif text-xl text-text-primary">
            Your tracker is full
          </h2>
          <p className="text-sm leading-relaxed text-text-secondary">
            Free accounts can follow {limit} bills. The {limit} you&rsquo;ve starred are kept in{' '}
            <Link href="/library" onClick={onClose} className="link-quiet">My Library</Link>, and
            you&rsquo;ll hear when they move. Building a tracker beyond {limit} bills is a Pro feature.
          </p>
        </div>
        <ReferralUnlock
          source="watch_limit"
          gateFeature="watchlist_limit"
          heading="Get a month of Pro free"
          blurb="Share the Atlas with a colleague. When they create a free account through your link, your month of Pro starts. No card needed."
        />
        <div className="flex items-center justify-between text-sm">
          <Link
            href="/pricing"
            onClick={() => { track('cta_click', { entry_source: 'watch_limit_plans' }); onClose(); }}
            className="link-arrow text-text-secondary"
          >
            See plans
          </Link>
          <button type="button" onClick={onClose} className="text-text-muted hover:text-text-primary">
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}
