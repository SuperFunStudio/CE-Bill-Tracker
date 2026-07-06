'use client';
import { useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { CheckIcon } from '@/components/ui/icons';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { useAuth } from '@/components/auth/AuthContext';
import { startProCheckout } from '@/lib/billing';
import { PRO, type BillingPeriod } from '@/lib/tiers';
import { track } from '@/lib/analytics';
import type { PlanInterest } from '@/lib/api';

interface Tier {
  id: 'free' | 'pro' | 'bespoke';
  kind: 'free' | 'checkout' | 'inquiry';
  eyebrow?: string; // small label above the name (e.g. "Most Popular", "Kenny Arnold Design")
  name: string;
  price?: string; // static price (free / bespoke); Pro's price is period-dependent (rendered live)
  cadence?: string;
  who: string;
  features: string[];
  cta: string;
  highlight?: boolean;
  inquiryPlan?: PlanInterest; // for kind === 'inquiry' — which plan the lead-capture modal records
}

// One self-serve paid tier (Pro — monthly or annual, with the founding 90-day-free offer applied at
// Checkout, see app/api/billing.py) plus Bespoke, a consulting engagement lead-captured via the request
// modal. Price copy lives in @/lib/tiers. The Developers (API) strip below the grid is a separate buyer.
const TIERS: Tier[] = [
  {
    id: 'free',
    kind: 'free',
    eyebrow: 'Open access',
    name: 'Free',
    price: '$0',
    cadence: 'always',
    who: 'For advocates, nonprofits, researchers, journalists, and students who need to see the landscape.',
    features: [
      'Full Bill Explorer & map — all 50 states',
      'State snapshots — market conditions, producer obligations & pending regulations',
      'Federal Actions tracker',
      'Design Guide — headline imperatives',
      'Personalize your feed + a limited alerts filter (free account)',
    ],
    cta: 'Get free updates',
  },
  {
    id: 'pro',
    kind: 'checkout',
    eyebrow: 'Recommended',
    name: PRO.name,
    who: "For the teams that want to stay ahead of EPR across every product and state — where a missed registration means penalties, a product line you can't sell in-state, and certifications signed under penalty of perjury.",
    features: [
      'Every obligation date, extracted from every bill',
      'Full timeline & deadline dashboard — all 50 states',
      'Personal & shared watch lists for your team',
      'Alerts across every instrument, custom filters',
      'Complete Design Guide',
      'CSV export (bills & deadlines)',
    ],
    cta: 'Claim founding access',
    highlight: true,
  },
  {
    id: 'bespoke',
    kind: 'inquiry',
    eyebrow: 'Kenny Arnold Design',
    name: 'Bespoke',
    price: 'By inquiry',
    cadence: 'a scoped engagement, mapped to your needs + complimentary subscription',
    who: 'For producers who need to know their own exposure, and what to redesign to reduce it.',
    features: [
      'A custom exposure map for your portfolio',
      'Material- and design-level redesign strategy',
      'Built from your volume & material data',
      'Direct work with Kenny Arnold Design',
      'Pro access included for your team',
    ],
    cta: 'Start a conversation',
    inquiryPlan: 'bespoke',
  },
];

export default function PricingPage() {
  const { isPro, user, openAuth, getToken } = useAuth();
  const [period, setPeriod] = useState<BillingPeriod>('annual');
  const [modal, setModal] = useState<{ plan: PlanInterest; label: string } | null>(null);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  // The CTA click that opens the request-access modal — the step *before* request_access submit. The
  // gap between this and request_access is your modal drop-off.
  function openPlan(plan: PlanInterest, label: string) {
    track('pricing_cta', { plan, plan_label: label });
    setModal({ plan, label });
  }

  // Pro is self-serve: send the visitor to Stripe Checkout for the chosen period (the founding offer is
  // applied server-side). Checkout needs an authenticated user (the backend keys the Stripe customer
  // off the verified email), so prompt sign-in first if needed.
  async function startPro() {
    track('pricing_cta', { plan: 'pro', plan_label: 'Pro', period });
    setCheckoutError(null);
    if (!user) {
      openAuth();
      return;
    }
    setCheckoutBusy(true);
    try {
      await startProCheckout(getToken, period);
    } catch (e) {
      setCheckoutError(e instanceof Error ? e.message : 'Could not start checkout.');
      setCheckoutBusy(false);
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <GazetteHeader
        title="Pricing"
        subtitle="Start free. We read every bill and pull out the dates, so the day a deadline would have slipped past you is the day this pays for itself."
      />

      {/* Billing-period toggle — annual is the default (cheaper per month). */}
      <div className="flex items-center justify-center gap-3">
        <div className="inline-flex rounded-lg border border-border-default bg-bg-secondary p-1">
          {(['annual', 'monthly'] as BillingPeriod[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors ${
                period === p ? 'bg-green-accent text-bg-primary' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <span className="text-meta text-green-accent">{PRO.annual.save}</span>
      </div>

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
            {tier.eyebrow && (
              <span className="self-start mb-2 text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
                {tier.eyebrow}
              </span>
            )}
            <h2 className="font-serif text-xl text-text-primary">{tier.name}</h2>
            <div className="mt-1 mb-3">
              {tier.id === 'pro' ? (
                period === 'annual' ? (
                  <>
                    <span className="text-2xl font-bold text-text-primary">{PRO.annual.price}</span>
                    <span className="text-text-muted text-sm"> {PRO.annual.cadence}</span>
                    <p className="text-text-muted text-meta mt-0.5">
                      {PRO.annual.perMonth} · {PRO.seatsNote}
                    </p>
                  </>
                ) : (
                  <>
                    <span className="text-2xl font-bold text-text-primary">{PRO.monthly.price}</span>
                    <span className="text-text-muted text-sm"> {PRO.monthly.cadence}</span>
                    <p className="text-text-muted text-meta mt-0.5">{PRO.seatsNote}</p>
                  </>
                )
              ) : (
                <>
                  <span className="text-2xl font-bold text-text-primary">{tier.price}</span>
                  {tier.cadence && <span className="text-text-muted text-sm"> {tier.cadence}</span>}
                </>
              )}
            </div>
            {tier.id === 'pro' && (
              <p className="mb-3 rounded-lg border border-green-accent/40 bg-green-dark/30 px-3 py-2 text-meta leading-relaxed text-green-accent">
                {PRO.foundingNote}
              </p>
            )}
            <p className="text-text-muted text-meta mb-4">{tier.who}</p>
            <ul className="space-y-2 mb-5 flex-1">
              {tier.features.map(f => (
                <li key={f} className="flex items-start gap-2 text-sm text-text-secondary">
                  <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            {tier.kind === 'free' ? (
              <Link
                href="/#get-updates"
                onClick={() => track('pricing_cta', { plan: 'free', plan_label: 'Free' })}
                className="block text-center rounded-lg border border-green-accent bg-green-dark px-4 py-2 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
              >
                {tier.cta} →
              </Link>
            ) : tier.kind === 'checkout' ? (
              isPro ? (
                // Already subscribed — route to account management instead of checkout.
                <Link
                  href="/account"
                  className="flex items-center justify-center gap-2 rounded-lg bg-green-accent text-bg-primary px-4 py-2 font-medium text-sm hover:opacity-90 transition-opacity"
                >
                  <CheckIcon className="text-xs" />
                  Manage plan
                </Link>
              ) : (
                <div className="space-y-2">
                  {/* Self-serve: 90-day trial checkout, cancel anytime. The single primary action. */}
                  <button
                    onClick={startPro}
                    disabled={checkoutBusy}
                    className="w-full rounded-lg bg-green-accent text-bg-primary px-4 py-2 font-medium text-sm transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    {checkoutBusy ? 'Starting…' : `${tier.cta} →`}
                  </button>
                  <p className="text-meta text-text-muted text-center">90-day free trial · cancel anytime</p>
                  {/* Assisted path demoted to a text link so the self-serve CTA clearly wins. */}
                  <p className="text-meta text-text-muted text-center">
                    Prefer a guided setup?{' '}
                    <button
                      onClick={() => openPlan('pro', 'Pro — walkthrough')}
                      className="text-green-accent hover:underline"
                    >
                      Book a walkthrough →
                    </button>
                  </p>
                </div>
              )
            ) : (
              <button
                onClick={() => openPlan(tier.inquiryPlan ?? 'enterprise', tier.name)}
                className="block w-full text-center rounded-lg border border-green-accent bg-green-dark px-4 py-2 font-serif font-medium text-green-accent transition-opacity hover:opacity-90"
              >
                {tier.cta} →
              </button>
            )}
          </div>
        ))}
      </div>

      {checkoutError && <p className="text-red-400 text-sm text-center">{checkoutError}</p>}

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
        <Link
          href="/developers"
          onClick={() => track('cta_click', { plan: 'api', source: 'pricing_developers' })}
          className="shrink-0 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          View API docs →
        </Link>
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
