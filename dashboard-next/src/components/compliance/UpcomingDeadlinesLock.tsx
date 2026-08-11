'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/auth/AuthContext';
import { startProCheckout } from '@/lib/billing';
import { PRO, upgradeLabel } from '@/lib/tiers';
import { useReferralShare } from '@/hooks/useReferralShare';
import { track, trackGateShown, trackGateHit } from '@/lib/analytics';
import { LockIcon } from '@/components/ui/icons';

/** GA `feature` label for every gate event this card emits — keep in sync with the useProGate callers. */
const FEATURE = 'upcoming_deadlines';

/**
 * The unlock card shown below the free teaser rows (the soonest few deadlines a non-Pro visitor is
 * allowed to see — the full calendar is served only to Pro, server-side). Two ways out: start the
 * 90-day Pro trial, or share a referral link — when a colleague creates a free account through it, the
 * sharer earns a month of Pro (granted server-side; we poll to flip the gate open).
 */
export function UpcomingDeadlinesLock({ lockedCount }: { lockedCount?: number }) {
  const { user, openAuth, getToken, refreshEntitlement } = useAuth();
  // Shared share-to-unlock flow (link load, copy/share, grant polling) — see useReferralShare.
  const { link, copied, shared, copyError, copy, share } = useReferralShare('deadlines_lock');
  const [mounted, setMounted] = useState(false);
  const [trialBusy, setTrialBusy] = useState(false);
  const [trialError, setTrialError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true); // triggers the fade-in transition
    // Impression. deadlines_lock_shown is kept alongside the generic gate_shown purely to preserve the
    // existing time series — new analysis should use gate_shown, which every wall now emits.
    track('deadlines_lock_shown', { feature: FEATURE });
    trackGateShown('pro', FEATURE);
  }, []);

  const startTrial = useCallback(async () => {
    // This card hand-rolls what useProGate does (openAuth vs startProCheckout), so it never emitted
    // gate_hit and stayed invisible in the conversion funnel despite being the highest-volume paywall
    // on the site. Mirror the hook's exact param shape (gate/outcome/feature) so the two are comparable.
    trackGateHit('pro', user ? 'checkout' : 'sign_in', FEATURE);
    track('deadlines_lock_cta', { action: 'trial' });
    if (!user) {
      openAuth();
      return;
    }
    setTrialError(null);
    setTrialBusy(true);
    try {
      await startProCheckout(getToken);
      // On success the browser redirects to Stripe; leave the button in its busy state.
    } catch (e) {
      setTrialError(e instanceof Error ? e.message : 'Could not start checkout. Please try again.');
      setTrialBusy(false);
    }
  }, [user, getToken, openAuth]);

  // The lock card seeds the native share sheet with deadline-specific copy.
  const shareDeadlines = useCallback(
    () =>
      share({
        title: 'Atlas Circular — Upcoming EPR Deadlines',
        text: 'Track every EPR compliance deadline across all 50 states.',
      }),
    [share],
  );

  return (
    <div
      className={`mx-auto w-full max-w-md rounded-panel border border-green-accent bg-bg-secondary p-7 text-center space-y-5 shadow-xl transition-opacity duration-700 ${
        mounted ? 'opacity-100' : 'opacity-0'
      }`}
    >
        <LockIcon className="text-3xl text-green-accent mx-auto" />
        <div>
          <h2 className="font-serif text-xl text-text-primary mb-1">
            {lockedCount && lockedCount > 0
              ? `${lockedCount} more deadline${lockedCount === 1 ? '' : 's'} behind Pro`
              : 'Unlock every Upcoming Deadline'}
          </h2>
          <p className="text-text-secondary text-sm leading-relaxed">
            See every EPR compliance deadline across all 50 states on one timeline, filtered to your
            scope — and never miss a date.
          </p>
        </div>

        {/* Pro path */}
        <div className="space-y-1.5">
          <button
            onClick={startTrial}
            disabled={trialBusy}
            className="w-full rounded-lg bg-green-accent text-bg-primary px-4 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {trialBusy ? 'Starting…' : user ? upgradeLabel() : 'Sign in to continue'}
          </button>
          {trialError && <p className="text-meta text-error">{trialError}</p>}
          <p className="text-meta text-green-accent leading-relaxed">{PRO.foundingNote}</p>
        </div>

        <div className="flex items-center gap-3 text-meta uppercase tracking-wider text-text-muted">
          <span className="h-px flex-1 bg-border-default" /> or <span className="h-px flex-1 bg-border-default" />
        </div>

        {/* Referral path */}
        <div className="space-y-2">
          <p className="text-sm text-text-primary font-medium">Unlock 1 month free</p>
          <p className="text-xs text-text-muted leading-relaxed">
            Share this with a colleague. When they create a free account through your link, you get a
            month of Pro — on us.
          </p>
          {!user ? (
            <button
              onClick={() => {
                // The referral escape hatch is its own gate — a separate feature label keeps it from
                // blending into the trial CTA when comparing which way out of the wall people take.
                trackGateHit('pro', 'sign_in', 'deadlines_referral_link');
                openAuth();
              }}
              className="w-full rounded-lg border border-green-accent bg-green-dark px-4 py-2 text-sm font-medium text-green-accent hover:opacity-90 transition-opacity"
            >
              Sign in to get your link →
            </button>
          ) : shared ? (
            <div className="rounded-lg border border-green-accent/40 bg-green-dark/30 px-3 py-2.5 space-y-1.5">
              <p className="text-xs text-green-accent leading-relaxed">
                {copied ? 'Link copied! ' : 'Shared! '}Your month of Pro unlocks the moment a colleague
                creates their account through your link.
              </p>
              <button onClick={() => refreshEntitlement()} className="text-meta text-green-accent underline">
                Check access now
              </button>
            </div>
          ) : link ? (
            <div className="space-y-2">
              <div className="flex gap-2">
                <input
                  readOnly
                  value={link}
                  onFocus={e => e.currentTarget.select()}
                  className="flex-1 min-w-0 rounded-lg border border-border-default bg-bg-primary px-2 py-2 text-xs text-text-secondary"
                />
                <button
                  onClick={copy}
                  className="shrink-0 rounded-lg bg-green-accent text-bg-primary px-3 py-2 text-xs font-medium hover:opacity-90 transition-opacity"
                >
                  Copy
                </button>
              </div>
              <button
                onClick={shareDeadlines}
                className="w-full rounded-lg border border-green-accent bg-green-dark px-4 py-2 text-sm font-medium text-green-accent hover:opacity-90 transition-opacity"
              >
                Share to a colleague →
              </button>
              {copyError && (
                <p className="text-meta text-text-muted">
                  Couldn&rsquo;t copy automatically — tap the link above to select it, then copy.
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-text-muted">Loading your link…</p>
          )}
        </div>

        <Link
          href="/"
          className="block text-xs text-text-muted hover:text-text-primary transition-colors pt-1"
        >
          ← Back to the Bill Explorer
        </Link>
    </div>
  );
}
