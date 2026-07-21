// Single source of truth for membership copy (Atlas Circular). Four tiers, framed as membership +
// access to our research tools: Students (verified-edu, free), Researchers (monthly/annual), Pro /
// Professionals (self-serve monthly/annual with the founding offer), Enterprise (invoiced/Bespoke).
// Centralised so price copy lives in ONE place. See app/api/billing.py + app/api/auth.py PLAN_CAPS.
//
// Framing note (2026-07): the header anchors Atlas against $50k+ legislative-intelligence platforms
// and the cost of a single missed EPR registration; the Pro price leads with the founding rate and
// strikes through the post-window price. The 50%-off-for-life coupon is applied server-side to both
// periods and lapses when the founding window closes (billing.py), so the struck-through figure is the
// price new members pay after 30 Nov — the display matches what Stripe actually charges.
export type BillingPeriod = 'monthly' | 'annual';

// Header — value anchoring above the tier grid.
export const PRICING_HEADER = {
  title: 'Circular economy regulation, tracked across 25+ jurisdictions',
  subtitle:
    "Legislative intelligence platforms start around $50,000 a year. Atlas covers what they don't — and costs what a single missed EPR registration would.",
  chips: ['25+ jurisdictions', 'EPR, packaging, right to repair, ESPR', 'Updated daily'],
};

// Student — verified-edu, free. The return to us is distribution, not revenue: students carry Atlas
// into coursework and studio work, and every export ships with an Atlas source line. (Pay-what-you-wish
// retired — the marketing reach is worth more than the token donation.)
export const STUDENT = {
  label: 'Students',
  headline: 'Free',
  sub: 'Verified .edu or .ac.uk email',
  who: 'Full research access for coursework, theses, and studio projects. Exports carry an Atlas source line.',
  features: ['Ask the Atlas', 'Bill explorer and jurisdiction data', 'Design guide'],
};

// Researchers — monthly or annual (annual discounted). Mirrors PRO's two-period shape so the pricing
// toggle drives both cards.
export const RESEARCH = {
  label: 'Researchers',
  monthly: { price: '$30', cadence: '/mo', sub: '1 seat' },
  annual: {
    price: '$240',
    cadence: '/yr',
    sub: '$20/mo, billed annually · 1 seat',
    save: 'Save $120/yr vs monthly',
  },
  who: 'Academics, non-profits, and institutions doing published work.',
  features: ['Everything in Students', 'Track how bills move over time', 'Cite and export with sources'],
};

// Pro / Professionals — self-serve, founding offer. Displayed prices are the founding (50%-off) rate;
// `was` is the post-window price struck through. Both periods carry the coupon (billing.py).
export const PRO = {
  name: 'Pro', // internal/account-page plan name; `label` is the pricing-card chip
  label: 'Professionals',
  badge: 'Most popular',
  monthly: { price: '$200', was: '$400', cadence: '/mo', sub: 'First seat · extra seats billed annually' },
  annual: {
    price: '$1,800',
    was: '$3,600',
    cadence: '/yr',
    sub: 'First seat · $1,200 per additional seat',
    save: 'Save $600/yr vs monthly',
  },
  who: 'Consultants, ESG and legal services, and in-house sustainability teams answering to clients.',
  foundingNote: 'Founding rate, locked for as long as you stay. Closes 30 November.',
  features: [
    'Know which products fall out of compliance, and where',
    'Get told before a deadline, not after',
    'Turn a jurisdiction scan into a client-ready brief',
    'Packaging studio and federal actions',
  ],
};

// Enterprise — invoiced inquiry (lead capture), not a checkout plan.
export const ENTERPRISE = {
  label: 'Enterprise',
  headline: 'Bespoke',
  sub: 'Scoped and invoiced per engagement',
  who: 'For a portfolio too large and too specific to read off a dashboard.',
  features: [
    'Exposure mapped across your own product lines',
    'Modelling built around your material streams',
    'Seats for the whole team, plus onboarding',
  ],
};

/** CTA label for unlocking Pro from an in-app gate. Leads to Checkout, which starts the 90-day trial. */
export function upgradeLabel(): string {
  return 'Start free — 90-day trial →';
}
