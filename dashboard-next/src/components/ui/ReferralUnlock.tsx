'use client';
import { useCallback } from 'react';
import { useAuth } from '@/components/auth/AuthContext';
import { useReferralShare } from '@/hooks/useReferralShare';
import { trackGateHit } from '@/lib/analytics';

/**
 * The "share the Atlas, get a month of Pro" block, shared by every surface that offers it as a way
 * past a wall (the Upcoming Deadlines lock, the litigation case spotlight a alert email lands on).
 *
 * Extracted rather than copied: the four states this block moves through — signed out, link
 * loading, link ready, shared-and-waiting — are the fiddly part, and a second hand-rolled copy is
 * how one surface quietly stops polling for the grant or stops emitting `gate_hit`. Callers supply
 * only the copy and the two analytics labels.
 */
export function ReferralUnlock({
  source,
  gateFeature,
  heading = 'Unlock 1 month free',
  blurb = 'Share this with a colleague. When they create a free account through your link, you get a month of Pro — on us.',
  shareTitle,
  shareText,
}: {
  /** `entry_source` on the referral_share events — which surface the share came from. */
  source: string;
  /** `feature` on the gate_hit event the signed-out path emits, so this escape hatch stays
   *  distinguishable from the card's primary upgrade CTA in the funnel. */
  gateFeature: string;
  heading?: string;
  blurb?: string;
  /** Seed the native share sheet with copy specific to what the reader is looking at. */
  shareTitle?: string;
  shareText?: string;
}) {
  const { user, openAuth, refreshEntitlement } = useAuth();
  const { link, copied, shared, copyError, copy, share } = useReferralShare(source);

  const onShare = useCallback(
    () => share({ title: shareTitle, text: shareText }),
    [share, shareTitle, shareText],
  );

  return (
    <div className="space-y-2">
      <p className="text-sm text-text-primary font-medium">{heading}</p>
      <p className="text-xs text-text-muted leading-relaxed">{blurb}</p>
      {!user ? (
        <button
          onClick={() => {
            trackGateHit('pro', 'sign_in', gateFeature);
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
            onClick={onShare}
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
  );
}
