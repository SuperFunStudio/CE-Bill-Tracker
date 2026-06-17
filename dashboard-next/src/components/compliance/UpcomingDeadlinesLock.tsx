'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/auth/AuthContext';
import { startProCheckout } from '@/lib/billing';
import { PRO, upgradeLabel } from '@/lib/tiers';
import { getMyReferralCode, referralLink } from '@/lib/referrals';
import { track } from '@/lib/analytics';
import { LockIcon } from '@/components/ui/icons';

/**
 * The lock that fades in over the Upcoming Deadlines preview after the free timer runs out. Two ways
 * out: start the 90-day Pro trial, or share a referral link — when a colleague creates a free account
 * through it, the sharer earns a month of Pro (granted server-side; we poll to flip the gate open).
 */
export function UpcomingDeadlinesLock() {
  const { user, isPro, openAuth, getToken, refreshEntitlement } = useAuth();
  const [mounted, setMounted] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);

  useEffect(() => {
    setMounted(true); // triggers the fade-in transition
    track('deadlines_lock_shown');
  }, []);

  // Load the signed-in user's share link.
  useEffect(() => {
    if (!user) {
      setLink(null);
      return;
    }
    let active = true;
    (async () => {
      try {
        const code = await getMyReferralCode(await getToken());
        if (active) setLink(referralLink(code));
      } catch {
        /* leave null — UI shows a gentle loading state */
      }
    })();
    return () => {
      active = false;
    };
  }, [user, getToken]);

  // Once they've shared, poll for the grant so the gate opens the moment the colleague signs up.
  useEffect(() => {
    if (!user || !shared || isPro) return;
    const id = setInterval(() => {
      refreshEntitlement();
    }, 15000);
    return () => clearInterval(id);
  }, [user, shared, isPro, refreshEntitlement]);

  const startTrial = useCallback(() => {
    track('deadlines_lock_cta', { action: 'trial' });
    if (user) startProCheckout(getToken);
    else openAuth();
  }, [user, getToken, openAuth]);

  const copy = useCallback(async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setShared(true);
      track('referral_share', { method: 'copy' });
    } catch {
      /* clipboard blocked */
    }
  }, [link]);

  const share = useCallback(async () => {
    if (!link) return;
    track('referral_share', { method: 'native' });
    setShared(true);
    try {
      if (navigator.share) {
        await navigator.share({
          title: 'SignalScout — Upcoming EPR Deadlines',
          text: 'Track every EPR compliance deadline across all 50 states.',
          url: link,
        });
      } else {
        await navigator.clipboard.writeText(link);
        setCopied(true);
      }
    } catch {
      /* user cancelled the share sheet */
    }
  }, [link]);

  return (
    <div
      className={`fixed inset-0 z-30 flex items-center justify-center p-6 bg-bg-primary/70 backdrop-blur-sm transition-opacity duration-700 ${
        mounted ? 'opacity-100' : 'opacity-0'
      }`}
    >
      <div className="w-full max-w-md rounded-2xl border border-green-accent bg-bg-secondary p-7 text-center space-y-5 shadow-xl">
        <LockIcon className="text-3xl text-green-accent mx-auto" />
        <div>
          <h2 className="font-serif text-xl text-text-primary mb-1">That was a peek at Upcoming Deadlines</h2>
          <p className="text-text-secondary text-sm leading-relaxed">
            See every EPR compliance deadline across all 50 states on one timeline, filtered to your
            scope — and never miss a date.
          </p>
        </div>

        {/* Pro path */}
        <div className="space-y-1.5">
          <button
            onClick={startTrial}
            className="w-full rounded-lg bg-green-accent text-bg-primary px-4 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity"
          >
            {user ? upgradeLabel() : 'Sign in to continue'}
          </button>
          <p className="text-[11px] text-green-accent leading-relaxed">{PRO.foundingNote}</p>
        </div>

        <div className="flex items-center gap-3 text-[11px] uppercase tracking-wider text-text-muted">
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
              onClick={openAuth}
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
              <button onClick={() => refreshEntitlement()} className="text-[11px] text-green-accent underline">
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
                onClick={share}
                className="w-full rounded-lg border border-green-accent bg-green-dark px-4 py-2 text-sm font-medium text-green-accent hover:opacity-90 transition-opacity"
              >
                Share to a colleague →
              </button>
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
    </div>
  );
}
