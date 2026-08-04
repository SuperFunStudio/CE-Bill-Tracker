'use client';
import { useEffect, useState } from 'react';
import { track } from '@/lib/analytics';

/**
 * A small, self-dismissing toast shown to Homepage B visitors: tells them we're trying a new look and
 * asks for a 👍 / 👎. The vote fires `home_variant_vote` to GA4 (paired with the sticky variant) and is
 * asked at most twice per device (once voted, never again). Appears a few seconds after load so it
 * doesn't compete with the page settling; auto-dismisses after ~14s if untouched.
 */
const VOTED_KEY = 'ac_home_vote';    // set once the visitor votes → never ask again
const SEEN_KEY = 'ac_home_vote_seen'; // times shown without voting (cap so we don't nag)
const MAX_SEEN = 2;
const APPEAR_MS = 3500;
const AUTO_HIDE_MS = 14000;

export function HomeVariantVote() {
  const [phase, setPhase] = useState<'hidden' | 'in' | 'thanks'>('hidden');

  useEffect(() => {
    let seen = 0;
    try {
      if (localStorage.getItem(VOTED_KEY)) return;      // already voted → done forever
      seen = Number(localStorage.getItem(SEEN_KEY) || '0');
      if (seen >= MAX_SEEN) return;
    } catch { return; }

    const appear = setTimeout(() => {
      setPhase('in');
      try { localStorage.setItem(SEEN_KEY, String(seen + 1)); } catch { /* ignore */ }
      track('home_variant_vote_shown', { variant: 'b' });
    }, APPEAR_MS);
    return () => clearTimeout(appear);
  }, []);

  // Auto-dismiss once shown (unless the visitor voted, which unmounts via the thanks timeout).
  useEffect(() => {
    if (phase !== 'in') return;
    const t = setTimeout(() => setPhase('hidden'), AUTO_HIDE_MS);
    return () => clearTimeout(t);
  }, [phase]);

  function vote(v: 'up' | 'down') {
    track('home_variant_vote', { variant: 'b', vote: v });
    try { localStorage.setItem(VOTED_KEY, v); } catch { /* ignore */ }
    setPhase('thanks');
    setTimeout(() => setPhase('hidden'), 2200);
  }

  if (phase === 'hidden') return null;

  return (
    <div
      role="dialog"
      aria-label="New homepage feedback"
      className="fixed bottom-4 right-4 z-50 max-w-[min(340px,calc(100vw-2rem))] rounded-xl border border-border-default bg-bg-secondary shadow-panel p-4 animate-[voteIn_.35s_ease-out]"
    >
      {phase === 'thanks' ? (
        <p className="text-sm text-text-primary">Thanks — noted. 🙏</p>
      ) : (
        <>
          <button
            onClick={() => setPhase('hidden')}
            aria-label="Dismiss"
            className="absolute top-2.5 right-3 text-text-muted hover:text-text-primary text-lg leading-none"
          >
            &times;
          </button>
          <p className="text-sm text-text-primary font-medium pr-5">We&apos;re trying out a new look</p>
          <p className="text-xs text-text-secondary mt-1">Exploring every bill as one interactive map. What do you think?</p>
          <div className="mt-3 flex items-center gap-2">
            <button
              onClick={() => vote('up')}
              className="flex-1 rounded-lg border border-green-accent/40 bg-green-hero text-text-primary text-sm font-medium py-2 hover:border-green-accent transition-colors"
            >
              👍 Like it
            </button>
            <button
              onClick={() => vote('down')}
              className="flex-1 rounded-lg border border-border-default bg-bg-primary text-text-secondary text-sm font-medium py-2 hover:text-text-primary transition-colors"
            >
              👎 Prefer the old one
            </button>
          </div>
        </>
      )}
    </div>
  );
}
