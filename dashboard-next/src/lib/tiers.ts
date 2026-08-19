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

/** A feature bullet. Usually a plain string; the object form marks the one bullet in a list that is the
 *  reason to buy the tier, and renders at full text weight against its muted neighbours. Exactly one
 *  emphasised bullet per list — two is none. */
export type Feature = string | { text: string; emphasis: true };
export const featureText = (f: Feature) => (typeof f === 'string' ? f : f.text);
export const featureEmphasis = (f: Feature) => typeof f !== 'string';

// Header — value anchoring above the tier grid. Every number on this page is passed in from live
// corpus data rather than written here: they have been wrong before (they only move when the corpus
// grows, which is exactly when nobody thinks to edit the pricing page). The FALLBACKs cover the first
// paint before that data lands, so no line ever flashes "0 regions".
export const REGION_COUNT_FALLBACK = 37;

// Rendered through the shared GazetteHeader like every other page, so the masthead face, rules and
// italic tagline match /methodology, /states and the rest — hence a plain page title with the pitch as
// the tagline, rather than a bespoke pricing-only headline treatment.
export const PRICING_HEADER = {
  title: 'Pricing',
  tagline:
    'Cheaper than missing a PRO registration deadline, and more valuable than an outdated spreadsheet',
  lede: (regions: number) =>
    `Atlas tracks circular economy law as it moves — bills, enacted statutes, producer fee schedules ` +
    `and compliance dates — across ${regions} regions, national and supranational, including US state law.`,
};

/** Coverage ledger, directly above the tiers: what you are actually buying, in numbers, before a
 *  price is named. Labels only — the counts are summed from /bills/timeline on the page itself. */
export const LEDGER = {
  noteLead: 'Every measure links to the document it came from.',
  noteRest:
    'Public legislative APIs where they exist, hand-collected filings where they do not. Open any ' +
    'citation and read the source yourself.',
};

// Category anchor. Legislative-intelligence platforms are sold to government-affairs teams with
// government-affairs budgets; the point is that every Atlas tier fits inside the rounding error of one
// of those contracts. Stated in prose — the bracket-and-tick diagram this replaced didn't read at a
// glance. The $50k is an approximate published entry price, so the footnote says so rather than
// letting the headline pass it off as surveyed fact.
export const SCALE = {
  eyebrow: 'What this normally costs',
  title:
    'Legislative intelligence can cost over $50,000 a year. We make it accessible for the teams that ' +
    'need it the most.',
  intro:
    'Platforms in this category are sold to government affairs teams with government affairs budgets. ' +
    'Atlas is built for the people who have to comply — designers, consultants, counsel, and ' +
    'sustainability teams — so it is priced against their budget instead. Every tier on this page, from ' +
    'a student seat to a full professional seat, falls between free and $1,800 a year.',
  foot:
    'The comparison figure is an approximate published entry price for the category, shown for scale. ' +
    'Enterprise engagements are scoped separately and sit outside this range.',
};

// Founding window, expressed as seats rather than a countdown clock — a seat count is a number we can
// actually stand behind. The live figure comes from GET /billing/founding-seats (see
// hooks/useFoundingSeats), which counts stamped founding entitlements, so the counter moves on its own
// as seats sell; `total`/`claimed` here are only the fallback for first paint or a failed call.
//
// Stripe now enforces the same window: coupon `FoundingMember50` (50% off, forever) carries
// max_redemptions=47 — 50 seats minus the 3 comped ones, which never pass through Stripe and so can't
// consume a redemption — plus a 2027-12-31 backstop redeem_by in case the seats never sell out. So the
// counter running to 0/50 and checkout stopping at the founding price happen together. If the comp count
// changes, Stripe's cap has to be re-cut: max_redemptions is immutable, so that means a new coupon.
// Seat scarcity is the only close mechanism on this page, so it carries the whole sentence: what the
// window is, what happens after it, and what it costs you to leave. The seat total is interpolated
// rather than typed into the sentence — the counter below it is live, and a hardcoded "50" in the prose
// would contradict the live figure the day the window is re-cut.
export const FOUNDING = {
  total: 50,
  claimed: 0,
  headline: (total: number) =>
    `Founding rate — ${total} seats, then list price. Locked for as long as you stay.`,
  remainingLine: (remaining: number, total: number) => `${remaining} of ${total} remaining`,
};

// Student — verified-edu, free. The return to us is distribution, not revenue: students carry Atlas
// into coursework and studio work, and every export ships with an Atlas source line. (Pay-what-you-wish
// retired — the marketing reach is worth more than the token donation.)
export const STUDENT = {
  label: 'Student',
  headline: 'Free',
  sub: 'Verified .edu or .ac.uk email',
  who: 'For coursework, theses, and studio projects.',
  features: [
    'Ask the Atlas — the full search',
    'Bill explorer and jurisdiction data',
    'Design guide',
    'Exports carry an Atlas source line, so your citations travel',
  ],
};

// Researchers — monthly or annual (annual discounted), now self-serve like Pro rather than gated behind
// a written request: the tier needs a legible upgrade over Student more than it needs an approval step,
// and the request form was a stall in front of a $20/mo decision. Verification happens at signup.
// Mirrors PRO's two-period shape so the pricing toggle drives both cards.
export const RESEARCH = {
  label: 'Researcher',
  monthly: { price: '$30', cadence: '/mo', sub: '1 seat' },
  annual: {
    price: '$240',
    cadence: '/yr',
    sub: '$20/mo billed annually · 1 seat',
    save: 'Save $120/yr vs monthly',
  },
  who: 'For published and institutional work — academics, non-profits, think tanks.',
  // Nothing here that the capability model doesn't already grant `research` (app/api/auth.py):
  // no deadline calendar (CAP_DEADLINES) and no alerts (CAP_ALERTS) — both are Pro-only and stay that
  // way, so naming either at this tier would sell a locked page. Exports are described as clean rather
  // than un-watermarked because nothing in the codebase watermarks an export at any tier.
  features: [
    'Everything in Student',
    'Full legislative history: how every measure moved, and when',
    'Clean exports with citations attached',
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
  // The per-seat add-on, stated as its own field rather than left only inside the `sub` strings above.
  // The FAQ quotes it too, and a page that has to parse a display string to find a price is one
  // rewording away from quoting the wrong number — which is exactly how that page drifted before.
  extraSeat: { monthly: '$50/mo', annual: '$600/yr' },
  // The benefit headline leads the card, above the arithmetic: the price only means something once the
  // reader knows what it buys them, and "before your client asks" is the fear the tier actually sells to.
  promise: 'Know your exposure before your client asks.',
  who: 'For consultancies, ESG and legal services, and in-house sustainability teams answering to clients.',
  // Used on in-app upgrade gates too (UpcomingDeadlinesLock, WatchListSection), so it has to read as a
  // whole sentence on its own — the pricing card pairs it with the seat counter (see FOUNDING).
  foundingNote: 'Founding rate, locked for as long as you stay — 50 seats at this price.',
  // "Which laws hit your products" is the ComplianceChecker on /compliance (materials + jurisdictions
  // in, applicable laws out) — deliberately not "know which products fall out of compliance", which
  // would imply a product-portfolio monitor we don't ship (that's Company Impact, gated and post-launch).
  //
  // The fee-exposure bullet — "Fee exposure estimated across enacted EPR schemes — a number your CFO
  // recognizes" — is held back deliberately, not forgotten. It is the must-purchase hook for this tier
  // and it goes in as the emphasised bullet (see Feature) the day a surface actually estimates exposure
  // across schemes. Fee schedules are already in compliance_details; the surface is what's missing.
  features: [
    'Which laws hit your products, by material and jurisdiction',
    'Deadline calendar and alerts: told before, not after',
    'Turn a jurisdiction scan into a client-ready brief',
    'Packaging studio and federal actions',
  ] as Feature[],
  // Trial length as product logic, not generosity: ninety days is one legislative cycle, which is the
  // only honest reason to give away three months next to a half-price founding rate.
  trialNote:
    "No card. Ninety days because legislation doesn't move in fourteen — you'll watch a real cycle before you pay.",
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

// Data — the corpus itself, licensed as a feed. A different buyer from every tier above (a platform,
// not a practitioner), so it sits in its own strip below the grid and sells the corpus rather than the
// interface. Framed as a licensing conversation instead of a link to the API docs: the self-serve
// developer tier is a way in, but the deal that matters here is negotiated.
export const DATA = {
  title: 'Data — build on the Atlas.',
  blurb:
    'The full corpus as a licensed feed: bills, statuses, deadlines, fee schedules, and CE ' +
    'classifications across every tracked jurisdiction, kept current daily. For compliance platforms, ' +
    'ESG tools, LCA software, and research teams that need the data inside their own systems.',
  cta: 'Talk to us about licensing →',
};

// "Fair questions" — the four objections that actually stop a card going in, answered before they're
// asked rather than buried in a FAQ page. Counts are injected from live corpus data (same numbers as
// the ledger) so an answer about scale can't quietly go stale.
export const FAIR_QUESTIONS = {
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
