'use client';
import { useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { CheckIcon } from '@/components/ui/icons';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { useAuth } from '@/components/auth/AuthContext';
import { startProCheckout } from '@/lib/billing';
import { track } from '@/lib/analytics';
import type { PlanInterest } from '@/lib/api';

interface Tier {
  id: PlanInterest | 'free';
  name: string;
  price: string;
  cadence?: string;
  who: string;
  features: string[];
  cta: string;
  highlight?: boolean;
}

// Pro shows one confident price ($39) and is self-serve: its CTA goes straight to Stripe Checkout.
// Free is $0; Enterprise (and API, below the grid) have no self-serve price, so they keep the
// "Request access & pricing" lead-capture modal. See app/api/billing.py + app/api/access.py.
const TIERS: Tier[] = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
    cadence: 'always',
    who: 'For advocates, nonprofits, researchers, journalists, and students.',
    features: [
      'Full Bill Explorer, map & timeline',
      'National deadline dashboard',
      'Federal Actions tracker',
      'Design Guide — headline imperatives',
      'Personalize your feed (free account)',
    ],
    cta: 'Get free updates',
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '$39',
    cadence: '/mo · per seat',
    who: 'For sustainability and compliance managers, and solo consultants.',
    features: [
      'Everything in Free, plus:',
      'Personal watch lists',
      'Portfolio exposure',
      'Complete Design Guide',
      'CSV export (bills & deadlines)',
    ],
    cta: 'Subscribe — $39/mo',
    highlight: true,
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 'Custom',
    who: 'For large producers, law firms, and PROs that need to prove coverage across an organization.',
    features: [
      'Everything in Pro, plus:',
      'Seats for your whole team',
      'API & data-feed access',
      'Custom bill classifications',
      'Organization-wide exposure reporting',
      'SSO & white-glove onboarding',
      'SLA & priority support',
    ],
    cta: 'Talk to us',
  },
];

export default function PricingPage() {
  const { isPro, user, openAuth, getToken } = useAuth();
  const [modal, setModal] = useState<{ plan: PlanInterest; label: string } | null>(null);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  // The CTA click that opens the request-access modal — the step *before* request_access submit. The
  // gap between this and request_access is your modal drop-off.
  function openPlan(plan: PlanInterest, label: string) {
    track('pricing_cta', { plan, plan_label: label });
    setModal({ plan, label });
  }

  // Pro is self-serve: send the visitor to Stripe Checkout. Checkout needs an authenticated user
  // (the backend keys the Stripe customer off the verified email), so prompt sign-in first if needed.
  async function startPro() {
    track('pricing_cta', { plan: 'pro', plan_label: 'Pro' });
    setCheckoutError(null);
    if (!user) {
      openAuth();
      return;
    }
    setCheckoutBusy(true);
    try {
      await startProCheckout(getToken);
    } catch (e) {
      setCheckoutError(e instanceof Error ? e.message : 'Could not start checkout.');
      setCheckoutBusy(false);
    }
  }

  return (
    <div className="p-6 space-y-8 max-w-6xl mx-auto">
      <GazetteHeader
        title="Pricing"
        subtitle="Start free. Upgrade when a missed deadline would cost you more than a subscription."
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-stretch">
        {TIERS.map(tier => (
          <div
            key={tier.id}
            className={`flex flex-col rounded-xl border p-5 ${
              tier.highlight
                ? 'border-green-accent bg-green-dark/20'
                : 'border-border-default bg-bg-secondary'
            }`}
          >
            {tier.highlight && (
              <span className="self-start mb-2 text-[10px] uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
                Most popular
              </span>
            )}
            <h2 className="font-serif text-xl text-text-primary">{tier.name}</h2>
            <div className="mt-1 mb-3">
              <span className="text-2xl font-bold text-text-primary">{tier.price}</span>
              {tier.cadence && <span className="text-text-muted text-sm"> {tier.cadence}</span>}
            </div>
            <p className="text-text-muted text-xs mb-4">{tier.who}</p>
            <ul className="space-y-2 mb-5 flex-1">
              {tier.features.map(f => (
                <li key={f} className="flex items-start gap-2 text-sm text-text-secondary">
                  <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            {tier.id === 'pro' && isPro ? (
              // Already subscribed — show a purchased badge that routes to account management
              // instead of the request-access CTA.
              <Link
                href="/account"
                className="flex items-center justify-center gap-2 rounded-lg bg-green-accent text-bg-primary px-4 py-2 font-medium text-sm hover:opacity-90 transition-opacity"
              >
                <CheckIcon className="text-xs" />
                Purchased
              </Link>
            ) : tier.id === 'free' ? (
              <Link
                href="/#get-updates"
                onClick={() => track('pricing_cta', { plan: 'free', plan_label: 'Free' })}
                className="block text-center rounded-lg border border-green-accent bg-green-dark px-4 py-2 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
              >
                {tier.cta}
              </Link>
            ) : tier.id === 'pro' ? (
              <div className="space-y-2">
                <button
                  onClick={startPro}
                  disabled={checkoutBusy}
                  className="w-full rounded-lg bg-green-accent text-bg-primary px-4 py-2 font-medium text-sm transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {checkoutBusy ? 'Starting…' : `${tier.cta} →`}
                </button>
                {checkoutError && <p className="text-red-400 text-xs">{checkoutError}</p>}
              </div>
            ) : (
              <button
                onClick={() => openPlan(tier.id as PlanInterest, tier.name)}
                className={`rounded-lg px-4 py-2 font-medium text-sm transition-opacity hover:opacity-90 ${
                  tier.highlight
                    ? 'bg-green-accent text-bg-primary'
                    : 'border border-green-accent bg-green-dark text-green-accent'
                }`}
              >
                {tier.cta} →
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Developers strip — its own section below the grid (different buyer, usage-based metric) */}
      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="max-w-2xl">
          <h3 className="font-serif text-lg text-text-primary mb-1">Developers — build on the data.</h3>
          <p className="text-text-secondary text-sm leading-relaxed">
            Tap the circularity-legislation dataset directly: bills, statuses, deadlines, and
            classifications across all 50 states, kept current. Free developer tier (rate-limited) ·
            paid plans by usage.
          </p>
        </div>
        <button
          onClick={() => openPlan('api', 'API')}
          className="shrink-0 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          Request API access & pricing →
        </button>
      </section>

      {/* Consulting line — footer of the pricing page */}
      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <p className="text-text-secondary text-sm leading-relaxed max-w-2xl">
          Tracking the deadline is step one. Turning it into a compliance and design roadmap is the work.
        </p>
        <a
          href="https://calendar.app.google/QPXh1qXWhNWxXo9n6"
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          Get in touch →
        </a>
      </section>

      {modal && (
        <RequestAccessModal
          plan={modal.plan}
          planLabel={modal.label}
          source="pricing"
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
