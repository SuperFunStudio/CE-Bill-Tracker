'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthContext';
import { useReferralShare } from '@/hooks/useReferralShare';
import { track } from '@/lib/analytics';
import { GiftIcon, CheckIcon } from '@/components/ui/icons';
import { SITE_NAME, SITE_TAGLINE } from '@/lib/brand';

/**
 * Global site footer — rendered at the bottom of every (non-embed) page by AppShell. Its centrepiece is
 * the share-to-unlock referral offer, promoted out of the buried Upcoming Deadlines lock card and made
 * the standing end-of-funnel CTA: share your link, and when a colleague creates a free account through
 * it you earn a month of Pro (granted server-side; the hook polls entitlement to flip access open). See
 * useReferralShare + app/api/referrals.py. Below the CTA sits the standard link/brand rail.
 *
 * Exception: /pricing suppresses the referral band. That page closes on one mechanism — the founding
 * seat counter — and a "get a free month" offer sitting under the price argues the opposite way, reading
 * as a discount stacked on a discount. The referral offer belongs post-signup, where it converts.
 */
const REFERRAL_HIDDEN = ['/pricing'];

export function SiteFooter() {
  const pathname = usePathname();
  const { user, isPro, openAuth } = useAuth();
  const showReferral = !REFERRAL_HIDDEN.some(p => pathname === p || pathname?.startsWith(`${p}/`));
  const { link, copied, shared, copyError, copy, share, refresh } = useReferralShare('footer', {
    enabled: showReferral,
  });

  // Pro members still benefit — a referral extends their membership by a month — but the copy shifts
  // from "get" to "give / extend" so it reads honestly to someone who already subscribes.
  const heading = isPro ? 'Get a month of Pro on us' : 'Get a free month of Pro';
  const blurb = isPro
    ? 'Share Atlas with a colleague. When they create a free account through your link, a month of Pro is added to your membership — on us.'
    : 'Share Atlas with a colleague. When they create a free account through your link, you get a full month of Pro — no card, on us.';

  return (
    <footer className="mt-16 border-t border-border-default bg-bg-secondary">
      {/* Referral CTA band — the central end of the funnel. The id is the deep-link target for the
          referral note in the email footer (app/alerts/email_shell.py), so a recipient lands on the
          offer rather than the top of the page. Renaming it breaks those links silently. */}
      {showReferral && (
      <section id="refer" className="scroll-mt-24 border-b border-border-default px-4 py-12">
        <div className="mx-auto max-w-2xl text-center space-y-5">
          <div className="inline-flex items-center gap-2 rounded-full border border-green-accent/40 bg-green-dark/30 px-3 py-1 text-meta uppercase tracking-wider text-green-accent">
            <GiftIcon className="text-sm" />
            Refer a colleague
          </div>
          <h2 className="font-serif text-2xl sm:text-3xl text-text-primary">{heading}</h2>
          <p className="mx-auto max-w-lg text-sm leading-relaxed text-text-secondary">{blurb}</p>

          {!user ? (
            <div className="space-y-2">
              <button
                onClick={() => {
                  track('referral_cta', { entry_source: 'footer', action: 'sign_in' });
                  openAuth();
                }}
                className="rounded-lg bg-green-accent px-6 py-2.5 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90"
              >
                Sign in to get your link →
              </button>
              <p className="text-meta text-text-muted">A free account is all it takes to start sharing.</p>
            </div>
          ) : shared ? (
            <div className="mx-auto max-w-md rounded-panel border border-green-accent/40 bg-green-dark/30 px-4 py-3 space-y-1.5">
              <p className="flex items-center justify-center gap-2 text-sm text-green-accent">
                <CheckIcon /> {copied ? 'Link copied.' : 'Shared.'} Your month of Pro unlocks the moment a
                colleague signs up.
              </p>
              <button onClick={refresh} className="text-meta text-green-accent underline">
                Check access now
              </button>
            </div>
          ) : link ? (
            <div className="mx-auto max-w-md space-y-2">
              <div className="flex gap-2">
                <input
                  readOnly
                  value={link}
                  onFocus={e => e.currentTarget.select()}
                  aria-label="Your referral link"
                  className="min-w-0 flex-1 rounded-lg border border-border-default bg-bg-primary px-3 py-2.5 text-xs text-text-secondary"
                />
                <button
                  onClick={copy}
                  className="shrink-0 rounded-lg bg-green-accent px-4 py-2.5 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90"
                >
                  Copy
                </button>
              </div>
              <button
                onClick={() => share()}
                className="w-full rounded-lg border border-green-accent bg-green-dark px-4 py-2.5 text-sm font-medium text-green-accent transition-opacity hover:opacity-90"
              >
                Share with a colleague →
              </button>
              {copyError && (
                <p className="text-meta text-text-muted">
                  Couldn&rsquo;t copy automatically — tap the link to select it, then copy.
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-text-muted">Loading your link…</p>
          )}
        </div>
      </section>
      )}

      {/* Link + brand rail. */}
      <div className="mx-auto flex max-w-5xl flex-col items-center gap-4 px-4 py-8 text-center sm:flex-row sm:justify-between sm:text-left">
        <div className="text-text-muted">
          <p className="font-serif text-base text-text-primary">{SITE_NAME}</p>
          {/* The brand tagline lives here (and in the page metadata) rather than under the nav
              wordmark, where the bar's fixed height forced it too small to read. */}
          <p className="text-meta">{SITE_TAGLINE} · Beta</p>
        </div>
        <nav className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-text-secondary">
          <Link href="/about" className="transition-colors hover:text-text-primary">About</Link>
          <Link href="/pricing" className="transition-colors hover:text-text-primary">Pricing</Link>
          <Link href="/faq" className="transition-colors hover:text-text-primary">FAQ</Link>
          <Link href="/methodology" className="transition-colors hover:text-text-primary">Methodology</Link>
          <Link href="/terms" className="transition-colors hover:text-text-primary">Terms</Link>
          <Link href="/privacy" className="transition-colors hover:text-text-primary">Privacy</Link>
        </nav>
      </div>
    </footer>
  );
}
