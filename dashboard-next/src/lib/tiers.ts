// Single source of truth for paid-tier copy. One self-serve tier (Pro) with two billing periods —
// monthly and annual. Annual is the cheaper-per-month option we nudge toward. The founding launch
// offer (50% off the first year + a 90-day free trial) is applied automatically at Checkout for
// either period (see app/api/billing.py). Centralised so price copy lives in ONE place.
export type BillingPeriod = 'monthly' | 'annual';

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
