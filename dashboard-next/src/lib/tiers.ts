// Single source of truth for membership copy (Atlas Circular). Four tiers, framed as membership +
// access to our research tools: Students (verified-edu, free), Researchers (monthly/annual), Pro /
// Professionals (self-serve monthly/annual with the founding offer), Enterprise (invoiced/Bespoke).
// Centralised so price copy lives in ONE place. See app/api/billing.py + app/api/auth.py PLAN_CAPS.
//
// Framing note (2026-08): the page argues before it lists. The masthead sets the frame (a seat costs
// less than one missed deadline), the ledger shows the corpus, and SCALE anchors the whole price range
// against the ~$50k entry price of the legislative-intelligence category it is sold beside. The Pro
// price leads with the founding rate and strikes through the post-window price; the 50%-off-for-life
// coupon is applied server-side to both periods (billing.py), so the struck-through figure is what new
// members pay once the window closes — the display matches what Stripe actually charges. The window is
// now presented as 50 seats rather than a date; see FOUNDING for the caveat that carries.
export type BillingPeriod = 'monthly' | 'annual';

// Header — value anchoring above the tier grid. Every number on this page is passed in from live
// corpus data rather than written here: they have been wrong before (they only move when the corpus
// grows, which is exactly when nobody thinks to edit the pricing page). The FALLBACKs cover the first
// paint before that data lands, so no line ever flashes "0 regions".
export const REGION_COUNT_FALLBACK = 37;

export const PRICING_HEADER = {
  eyebrow: 'Atlas Circular · Pricing',
  title: 'Every price on this page is smaller than one missed deadline.',
  lede: (regions: number) =>
    `Atlas tracks circular economy law as it moves — bills, enacted statutes, producer fee schedules ` +
    `and compliance dates — across ${regions} regions, national and supranational, including US state ` +
    `law. Start with what's in it, then decide what a seat is worth.`,
};

/** Coverage ledger, directly above the tiers: what you are actually buying, in numbers, before a
 *  price is named. Labels only — the counts are summed from /bills/timeline on the page itself. */
export const LEDGER = {
  noteLead: 'Every measure links to the document it came from.',
  noteRest:
    'Public legislative APIs where they exist, hand-collected filings where they do not. Open any ' +
    'citation and read the source yourself.',
};

// Reference scale — the category-anchoring block. Legislative-intelligence platforms are sold to
// government-affairs teams with government-affairs budgets; the point of the bar is that Atlas's whole
// price range sits inside the rounding error of one of those contracts. The high figure is an
// approximate published entry price, so it is labelled as approximate and footnoted, not asserted.
export const SCALE = {
  eyebrow: 'What this normally costs',
  title: 'Legislative intelligence was built for lobbyists, and priced for them.',
  intro:
    'Platforms in this category are sold to government affairs teams with government affairs budgets. ' +
    'Atlas is built for the people who have to comply — designers, consultants, counsel, and ' +
    'sustainability teams — so it is priced against their budget instead.',
  lowValue: '$0 – $1,800 / yr',
  lowLabel: 'Every Atlas tier, from a student seat to a full professional seat.',
  highValue: '≈ $50,000 / yr',
  highLabel: 'Typical entry price for a legislative intelligence platform.',
  foot:
    'Comparison figure is an approximate published entry price for the category, shown for scale. ' +
    'Enterprise engagements are scoped separately and sit outside this range.',
};

// Founding window, expressed as seats rather than a countdown clock — a seat count is a number we can
// actually stand behind, and it stops being true the moment we inflate it. CLAIMED must be set from the
// real Stripe subscription count before each deploy; until a seat sells we say how many exist rather
// than parading "50 of 50 remaining".
//
// SERVER-SIDE CAVEAT: app/api/billing.py closes the founding offer on the Stripe coupon's redeem-by
// DATE, not on a seat count. Keep the coupon's redeem-by well beyond the window and retire it by hand
// when CLAIMED hits TOTAL, or this copy and what Stripe charges will disagree.
export const FOUNDING = {
  total: 50,
  claimed: 0,
  headline: 'Founding rate. Locked for as long as you stay, whatever the list price does.',
  seatsLine: (remaining: number, total: number) =>
    remaining >= total
      ? `${total} founding seats at this rate`
      : `${total} founding seats — ${remaining} remaining`,
};

// Student — verified-edu, free. The return to us is distribution, not revenue: students carry Atlas
// into coursework and studio work, and every export ships with an Atlas source line. (Pay-what-you-wish
// retired — the marketing reach is worth more than the token donation.)
export const STUDENT = {
  label: 'Student',
  headline: 'Free',
  sub: 'Verified .edu or .ac.uk email',
  who: 'Full research access for coursework, theses, and studio projects.',
  features: [
    'Ask the Atlas — the full search',
    'Bill explorer and jurisdiction data',
    'Design guide',
    'Exports carry an Atlas source line, so your citations travel',
  ],
};

// Researchers — monthly or annual (annual discounted). Mirrors PRO's two-period shape so the pricing
// toggle drives both cards.
export const RESEARCH = {
  label: 'Researcher',
  monthly: { price: '$30', cadence: '/mo', sub: '1 seat' },
  annual: {
    price: '$240',
    cadence: '/yr',
    sub: '$20/mo, billed annually · 1 seat',
    save: 'Save $120/yr vs monthly',
  },
  who: 'Academics, non-profits, and institutions doing published work.',
  // No deadline calendar here on purpose: CAP_DEADLINES is Pro-only (app/api/auth.py), so promising it
  // at this tier would sell a locked page.
  features: [
    'Everything in Student',
    'Track how a measure moved, and when',
    'Cite and export with sources attached',
  ],
};

// Pro / Professionals — self-serve, founding offer. Displayed prices are the founding (50%-off) rate;
// `was` is the post-window price struck through. Both periods carry the coupon (billing.py).
export const PRO = {
  name: 'Pro', // internal/account-page plan name; `label` is the pricing-card chip
  label: 'Professional',
  badge: 'Best fit for client work',
  monthly: { price: '$200', was: '$400', cadence: '/mo', sub: 'First seat · $50/mo per additional seat' },
  annual: {
    price: '$1,800',
    was: '$3,600',
    cadence: '/yr',
    sub: 'First seat · $600 per additional seat',
    save: 'Save $600/yr vs monthly',
  },
  who: 'Consultancies, ESG and legal services, and in-house sustainability teams answering to clients.',
  // Used on in-app upgrade gates too (UpcomingDeadlinesLock, WatchListSection), so it has to read as a
  // whole sentence on its own — the pricing card pairs it with the seat counter (see FOUNDING).
  foundingNote: 'Founding rate, locked for as long as you stay — 50 seats at this price.',
  features: [
    'Everything in Researcher',
    'Know which products fall out of compliance, and where',
    'Get told before a deadline, not after',
    'Turn a jurisdiction scan into a client-ready brief',
    'Packaging studio and federal actions',
    'Say which jurisdiction we add next — paying seats set the order',
  ],
};

// Enterprise — invoiced inquiry (lead capture), not a checkout plan.
export const ENTERPRISE = {
  label: 'Enterprise',
  headline: 'Bespoke',
  sub: 'Scoped and invoiced per engagement',
  who:
    'For a portfolio too large and too specific to read off a dashboard. Most Atlas work starts as a ' +
    'conversation like this one.',
  ctaNote: "Tell us the portfolio and the jurisdictions. You'll get a scope back, not a sales sequence.",
  features: [
    'Exposure mapped across your own product lines',
    'Modelling built around your material streams',
    'Seats for the whole team, plus onboarding',
  ],
};

// "Fair questions" — the four objections that actually stop a card going in, answered before they're
// asked rather than buried in a FAQ page. Counts are injected from live corpus data (same numbers as
// the ledger) so an answer about scale can't quietly go stale.
export const FAIR_QUESTIONS = {
  eyebrow: 'Before you decide',
  title: "Fair questions we'd ask too",
  lede:
    'These are the things people want to know before they put a card in, so here they are with the ' +
    'answers up front.',
  items: ({ measures, regions }: { measures: string; regions: number }) => [
    {
      q: `Can a team this size really cover ${regions} regions?`,
      a:
        `It's a mix: public legislative APIs where a jurisdiction publishes one, and filings collected ` +
        `individually where it doesn't. That's why the corpus is ${measures} measures rather than a claim ` +
        `of totality — and why every one of them carries a link back to its source document. Check any of ` +
        `them against the record before you trust the rest.`,
    },
    {
      q: 'Is this a language model making things up?',
      a:
        'The database computes; the model only writes. Counts, dates and aggregates come out of the ' +
        'database as exact queries. The model summarises passages from measures the search has already ' +
        "matched, and it can't report that nothing exists when the matched set isn't empty. Every claim " +
        'it makes deep-links to the filing it came from.',
    },
    {
      q: 'What happens when the founding rate ends?',
      a:
        'Nothing, for you. The founding rate stays with your seat for as long as you keep it, whatever ' +
        'the list price does afterwards. Any change comes with notice first, and your saved research, ' +
        'alerts and exports come with you if you leave.',
    },
    {
      q: "What if the jurisdiction I need isn't in there?",
      a:
        `Tell us and it goes in the queue. Coverage went from US-only to ${regions} regions in a matter of ` +
        `months, so the constraint is priority rather than capability — and paying seats set the priority. ` +
        `If the gap is a dealbreaker, say so before you subscribe and we'll tell you honestly how long it ` +
        `would take.`,
    },
  ],
};

/** CTA label for unlocking Pro from an in-app gate. Leads to Checkout, which starts the 90-day trial. */
export function upgradeLabel(): string {
  return 'Start free — 90-day trial →';
}
