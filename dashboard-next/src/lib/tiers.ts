// Single source of truth for membership copy (Atlas Circular). Four tiers, framed as membership +
// access to our research tools: Student (pay-what-you-wish, verified-edu), Founding Supporter /
// Research (annual), Pro (self-serve monthly/annual with the founding offer), Enterprise (invoiced).
// Centralised so price copy lives in ONE place. See app/api/billing.py + app/api/auth.py PLAN_CAPS.
export type BillingPeriod = 'monthly' | 'annual';

// Student — pay-what-you-wish, gated to a verified educational email. Free floor, suggested $15/mo.
export const STUDENT = {
  name: 'Student',
  price: 'Pay what you wish',
  suggested: 'Suggested $15/mo · $0 floor',
  eduNote: 'Verified .edu / .ac.uk (or similar) email required',
  who: 'Students exploring the circular economy.',
};

// Founding Supporter / Research — monthly or annual (annual discounted), for researchers, institutions,
// and non-profits. Mirrors PRO's two-period shape so the pricing toggle drives both cards.
export const RESEARCH = {
  name: 'Founding Supporter',
  monthly: { price: '$30', cadence: '/mo' },
  annual: {
    price: '$240',
    cadence: '/yr',
    perMonth: '$20/mo, billed annually',
    save: 'Save $120/yr vs monthly',
  },
  who: 'Researchers, institutions, and non-profits.',
};

export const PRO = {
  name: 'Pro',
  monthly: { price: '$400', cadence: '/mo' },
  annual: {
    price: '$3,600',
    cadence: '/yr',
    perMonth: '$300/mo, billed annually',
    save: 'Save $1,200/yr — 3 months free',
  },
  seatsNote: 'Seats for your whole regulatory team',
  foundingNote: 'Founding members lock in 50% off for life. Try free for 90 days. Early access closes Nov 30.',
};

/** CTA label for unlocking Pro from an in-app gate. Leads to Checkout, which starts the 90-day trial. */
export function upgradeLabel(): string {
  return 'Start free — 90-day trial →';
}
