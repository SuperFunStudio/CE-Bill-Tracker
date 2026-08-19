'use client';
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/components/auth/AuthContext';
import { getMyReferralCode, referralLink } from '@/lib/referrals';
import { track } from '@/lib/analytics';

/**
 * Share-to-unlock referral state, extracted so every surface that offers "a free month of Pro" (the
 * global site footer, the Upcoming Deadlines lock card, …) drives the exact same flow: load the
 * signed-in user's link, copy / native-share it, and — once shared — poll entitlement so the grant
 * flips access open the moment a colleague signs up through the link. See app/api/referrals.py.
 */
export interface ReferralShare {
  /** The signed-in user's shareable `?ref=` link, or null while loading / signed out. */
  link: string | null;
  /** True after a successful copy (resets nothing; UI shows a "copied" affordance). */
  copied: boolean;
  /** True once the user has copied or opened the share sheet — flips the UI to the pending state. */
  shared: boolean;
  /** Clipboard write failed (insecure context / blocked) — prompt a manual copy. */
  copyError: boolean;
  /** Copy the link to the clipboard. */
  copy: () => Promise<void>;
  /** Native share sheet where available, else clipboard fallback. `text`/`title` seed the share. */
  share: (opts?: { title?: string; text?: string }) => Promise<void>;
  /** Force an entitlement refresh (the "check access now" affordance). */
  refresh: () => void;
}

const DEFAULT_SHARE = {
  title: 'Atlas Circular — circular-economy law, by jurisdiction',
  text: 'Track EPR, packaging, and right-to-repair law across the globe. Join me on Atlas Circular:',
};

/** `enabled: false` keeps the hook mounted (rules of hooks) but skips the network: for surfaces that
 *  render the referral offer conditionally and are currently hiding it. */
export function useReferralShare(source: string, opts?: { enabled?: boolean }): ReferralShare {
  const enabled = opts?.enabled ?? true;
  const { user, isPro, getToken, refreshEntitlement } = useAuth();
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);
  const [copyError, setCopyError] = useState(false);

  // Load the signed-in user's share link.
  useEffect(() => {
    if (!user || !enabled) {
      setLink(null);
      return;
    }
    let active = true;
    (async () => {
      try {
        const code = await getMyReferralCode(await getToken());
        if (active) setLink(referralLink(code));
      } catch {
        /* leave null — the UI shows a gentle loading state */
      }
    })();
    return () => {
      active = false;
    };
  }, [user, enabled, getToken]);

  // Once they've shared, poll for the grant so access opens the moment the colleague signs up.
  useEffect(() => {
    if (!user || !shared || isPro) return;
    const id = setInterval(() => refreshEntitlement(), 15000);
    return () => clearInterval(id);
  }, [user, shared, isPro, refreshEntitlement]);

  const copy = useCallback(async () => {
    if (!link) return;
    setCopyError(false);
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setShared(true);
      track('referral_share', { method: 'copy', entry_source: source });
    } catch {
      // Clipboard blocked (insecure context / permissions) — tell the user to copy manually.
      setCopyError(true);
    }
  }, [link, source]);

  const share = useCallback(
    async (opts?: { title?: string; text?: string }) => {
      if (!link) return;
      track('referral_share', { method: 'native', entry_source: source });
      setShared(true);
      try {
        if (navigator.share) {
          await navigator.share({
            title: opts?.title ?? DEFAULT_SHARE.title,
            text: opts?.text ?? DEFAULT_SHARE.text,
            url: link,
          });
        } else {
          await navigator.clipboard.writeText(link);
          setCopied(true);
        }
      } catch {
        /* user cancelled the share sheet */
      }
    },
    [link, source],
  );

  const refresh = useCallback(() => refreshEntitlement(), [refreshEntitlement]);

  return { link, copied, shared, copyError, copy, share, refresh };
}
