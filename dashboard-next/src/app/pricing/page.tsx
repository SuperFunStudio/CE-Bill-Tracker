'use client';
import { useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { CheckIcon } from '@/components/ui/icons';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
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

// Prices are hypotheses to validate — the "Request access & pricing" clicks (who, what org, which
// tier) set the real numbers before any billing is built. See app/api/access.py.
const TIERS: Tier[] = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
    cadence: 'always',
    who: 'Advocates, nonprofits, researchers, journalists, students',
    features: [
      'Full Bill Explorer, map & timeline',
      'National deadline dashboard',
      'Topic & jurisdiction email alerts',
      'CSV export',
    ],
    cta: 'Get free updates',
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '$29–49',
    cadence: '/mo',
    who: 'Sustainability / compliance managers, solo consultants',
    features: [
      'Everything in Free',
      'Personal watch lists & saved views',
      'Portfolio-scoped deadline dashboard',
      'Bill change-tracking & diffs',
      'Priority deadline alerts',
    ],
    cta: 'Request access & pricing',
    highlight: true,
  },
  {
    id: 'team',
    name: 'Team',
    price: '$199–399',
    cadence: '/mo',
    who: 'Small compliance, legal & consulting teams',
    features: [
      'Everything in Pro',
      'Multi-seat, shared watch lists',
      'Weekly team exposure digest',
      'Advanced filters',
    ],
    cta: 'Request access & pricing',
  },
  {
    id: 'enterprise',
    name: 'Enterprise / API',
    price: 'Custom',
    who: 'Large producers, law firms, PROs',
    features: [
      'API / data feed access',
      'Custom classifications',
      'SSO & white-glove onboarding',
      'SLA & priority support',
    ],
    cta: 'Request access & pricing',
  },
];

export default function PricingPage() {
  const [modal, setModal] = useState<{ plan: PlanInterest; label: string } | null>(null);

  return (
    <div className="p-6 space-y-8 max-w-6xl mx-auto">
      <GazetteHeader
        title="Pricing"
        subtitle="Start free. Upgrade when a missed deadline would cost you more than a subscription."
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-stretch">
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
            {tier.id === 'free' ? (
              <Link
                href="/#get-updates"
                className="block text-center rounded-lg border border-green-accent bg-green-dark px-4 py-2 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
              >
                {tier.cta}
              </Link>
            ) : (
              <button
                onClick={() => setModal({ plan: tier.id as PlanInterest, label: tier.name })}
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

      {/* API standalone note + the headline experiment CTA */}
      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="max-w-2xl">
          <h3 className="font-serif text-lg text-text-primary mb-1">Building on SignalScout?</h3>
          <p className="text-text-secondary text-sm leading-relaxed">
            A rate-limited free dev tier for non-commercial use, with paid commercial tiers by volume.
            The data feed covers bills, deadlines, classifications, and federal actions.
          </p>
        </div>
        <button
          onClick={() => setModal({ plan: 'api', label: 'API' })}
          className="shrink-0 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          Request API access & pricing →
        </button>
      </section>

      <p className="text-text-muted text-xs text-center">
        Prices shown are early-access estimates while we finalize plans — your request helps set them.
      </p>

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
