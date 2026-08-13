import type { Metadata } from 'next';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { PRO, RESEARCH, REGION_COUNT_FALLBACK, STUDENT } from '@/lib/tiers';

/**
 * Prices and tier names below are READ FROM lib/tiers.ts, never typed in. They were typed in once,
 * and the page drifted into describing a product that no longer existed: a free/Pro binary at
 * $400/month with no Student or Researcher tier, Federal Actions listed as free while the pricing
 * page sold it under Professional. The buyer this product courts — the one the methodology page is
 * written for — reads both pages and prices the contradiction into their trust. One source of truth
 * is the only fix that stays fixed. The capability claims mirror PLAN_CAPS in app/api/auth.py.
 */
export const metadata: Metadata = {
  title: 'FAQ — Atlas Circular',
  description:
    `Frequently asked questions about Atlas Circular: what it tracks across ${REGION_COUNT_FALLBACK} ` +
    'jurisdictions, where the data comes from, how the AI classification works, the Student, ' +
    'Researcher and Professional plans, alerts, and the API.',
  alternates: { canonical: '/faq/' },
};

interface QA {
  q: string;
  a: React.ReactNode;
}

interface Group {
  title: string;
  items: QA[];
}

const GROUPS: Group[] = [
  {
    title: 'The basics',
    items: [
      {
        q: 'What is Atlas Circular?',
        a: (
          <>
            Atlas Circular tracks circularity-aligned legislation across {REGION_COUNT_FALLBACK}{' '}
            jurisdictions — all 50 US states, the EU and its member states, and national law from
            Japan to Kenya to Chile,
            plus US federal action — Extended Producer Responsibility (EPR), right-to-repair,
            deposit-return, recycled-content, labeling, disposal bans, and related laws — in one
            place. It turns a firehose of legislative activity into the handful of bills, deadlines,
            and obligations that actually affect you.
          </>
        ),
      },
      {
        q: 'Who is it for?',
        a: (
          <>
            Producers and the teams responsible for staying compliant as EPR spreads — plus
            advocates, nonprofits, researchers, journalists, and students who need to see the
            landscape. The {STUDENT.label} and {RESEARCH.label} tiers are built for the latter;{' '}
            {PRO.label} is built for regulatory, sustainability, and product teams who need every
            deadline and obligation.
          </>
        ),
      },
      {
        q: 'What exactly does it track?',
        a: (
          <>
            Bills and enacted laws touching the circular economy: EPR / producer-responsibility
            programs, right-to-repair, recycled-content mandates, deposit-return / bottle bills,
            labeling and compostability claims, disposal and packaging bans, and financial
            incentives. We also track federal preemption and related federal agency actions via the{' '}
            <a
              href="https://www.federalregister.gov"
              target="_blank"
              rel="noopener noreferrer"
              className="text-green-accent hover:underline"
            >
              Federal Register
            </a>
            .
          </>
        ),
      },
    ],
  },
  {
    title: 'Data & accuracy',
    items: [
      {
        q: 'Where does the data come from?',
        a: (
          <>
            Legislative data is sourced from{' '}
            <a
              href="https://openstates.org"
              target="_blank"
              rel="noopener noreferrer"
              className="text-green-accent hover:underline"
            >
              Open States
            </a>{' '}
            (Plural Policy), and federal actions from the Federal Register. Every bill links back to
            its official primary source so you can verify the original text.
          </>
        ),
      },
      {
        q: 'How does the classification work — and how accurate is it?',
        a: (
          <>
            Every bill is screened against a fixed set of circularity criteria, then auto-classified
            for relevance, policy instrument, and the material streams it touches — each with a
            confidence score. Relevant bills have their compliance details (deadlines, covered
            products, producer obligations) extracted from the bill text, and a growing set is
            spot-reviewed by a human. Each bill shows whether its relevance call is auto-classified
            or reviewed.{' '}
            <strong className="text-text-primary">
              Classifications are automated and can contain errors — always verify against the
              primary source before relying on any result.
            </strong>{' '}
            <Link href="/methodology" className="text-green-accent hover:underline">
              See the full methodology →
            </Link>
          </>
        ),
      },
      {
        q: 'How current is the data?',
        a: (
          <>
            The corpus is refreshed on a regular ingestion cycle that pulls new and updated bills
            from Open States, with bulk backfills for historical coverage. Coverage is most complete
            from roughly 2017 onward and usable back to about 2009; older sessions are sparser.
          </>
        ),
      },
      {
        q: 'Can I rely on this for legal compliance?',
        a: (
          <>
            No. Atlas Circular is an intelligence and research tool, not legal advice. Deadlines
            and obligations are surfaced to help you find what matters faster — but you (and your
            counsel) are responsible for confirming the law that applies to you. See our{' '}
            <Link href="/terms" className="text-green-accent hover:underline">
              Terms of Service
            </Link>
            .
          </>
        ),
      },
    ],
  },
  {
    title: 'Plans & billing',
    items: [
      {
        q: 'What are the plans?',
        a: (
          <>
            Four. <strong>Free</strong> is the Bill Explorer and jurisdiction data — browse the whole
            corpus, no account needed. <strong>{STUDENT.label}</strong> is free on a verified .edu or
            .ac.uk address and adds Ask the Atlas and the Design Guide.{' '}
            <strong>{RESEARCH.label}</strong> ({RESEARCH.monthly.price}
            {RESEARCH.monthly.cadence}, or {RESEARCH.annual.price}
            {RESEARCH.annual.cadence}) adds the impact and bills-over-time analysis for published
            work. <strong>{PRO.label}</strong> adds the deadline calendar, watch lists and alerts,
            the Packaging Studio, and Federal Actions. Enterprise is scoped and invoiced per
            engagement.{' '}
            <Link href="/pricing" className="text-green-accent hover:underline">
              Compare plans →
            </Link>
          </>
        ),
      },
      {
        q: 'What do I get without paying?',
        a: (
          <>
            The Bill Explorer and the jurisdiction data behind it — every measure we track, its
            status, and a link to the source document, across every jurisdiction. Deadlines, alerts,
            watch lists, the full Design Guide, the Packaging Studio and Federal Actions sit on the
            paid tiers; students get most of the research surface free. We&apos;d rather say that
            plainly than describe a free tier that quietly shrinks.
          </>
        ),
      },
      {
        q: `How much does ${PRO.label} cost?`,
        a: (
          <>
            {PRO.monthly.price}
            {PRO.monthly.cadence} or {PRO.annual.price}
            {PRO.annual.cadence} for the first seat, at the founding rate — half the list price of{' '}
            {PRO.monthly.was}
            {PRO.monthly.cadence} / {PRO.annual.was}
            {PRO.annual.cadence}. Additional seats are {PRO.extraSeat.monthly} (
            {PRO.extraSeat.annual} billed annually). The founding rate is capped at 50 seats and
            stays with your seat for as long as you keep it. Cancel anytime.
          </>
        ),
      },
      {
        q: 'Is there a free trial?',
        a: (
          <>
            Yes, and no card is needed to start: a new account gets a 7-day {PRO.label} trial
            immediately. Taking a founding seat at checkout adds a 90-day trial on top, billed only
            when it ends. You can extend access further by referring others.
          </>
        ),
      },
      {
        q: 'How do I cancel or manage my plan?',
        a: (
          <>
            From <Link href="/account" className="text-green-accent hover:underline">your account</Link>,
            open <em>Manage plan</em> to reach the billing portal, where you can update payment
            details or cancel. Cancellation stops future renewals; you keep your plan through the end
            of the period you have paid for.
          </>
        ),
      },
    ],
  },
  {
    title: 'Features',
    items: [
      {
        q: 'What are watch lists and alerts?',
        a: (
          <>
            Watch lists ({PRO.label}) let you and your team follow specific bills and get notified
            when their status or deadlines change. Alerts email you about new and changing
            legislation across every instrument, with custom filters — also {PRO.label}. Separately,
            anyone can subscribe to the free email updates from the sign-up form on any page: pick
            your jurisdictions, materials and topics, confirm the address, and we&apos;ll email you
            when matching legislation moves. You can unsubscribe from any email at any time.
          </>
        ),
      },
      {
        q: 'What is the Design Guide?',
        a: (
          <>
            The Design Guide synthesizes what enacted EPR and circularity law actually requires into
            design-for-compliance principles — so product and packaging teams can act on policy, not
            just read it. Signed-out visitors see the headline imperatives; the complete guide opens
            at {STUDENT.label} and above.
          </>
        ),
      },
      {
        q: 'What is Portfolio Exposure?',
        a: (
          <>
            Portfolio Exposure maps how legislation intersects with a company&apos;s materials and
            geographic footprint to estimate where compliance risk is concentrating. These are
            directional estimates intended to prioritize attention, not precise liability figures.
            Deeper, portfolio-specific exposure mapping is available as a bespoke engagement —{' '}
            <Link href="/pricing" className="text-green-accent hover:underline">
              see pricing →
            </Link>
          </>
        ),
      },
      {
        q: 'Is there an API?',
        a: (
          <>
            Yes — the circularity-legislation dataset (bills, statuses, deadlines, and
            classifications across every jurisdiction we track) is available via API, with a
            rate-limited free developer tier and usage-based paid plans. See the{' '}
            <Link href="/developers" className="text-green-accent hover:underline">
              developer docs
            </Link>
            , or request access from the{' '}
            <Link href="/pricing" className="text-green-accent hover:underline">
              pricing page
            </Link>
            .
          </>
        ),
      },
    ],
  },
  {
    title: 'Account & contact',
    items: [
      {
        q: 'Do I need an account?',
        a: (
          <>
            You can browse the Bill Explorer and map without one, and subscribe to the free email
            updates without one. An account is what carries a plan: {STUDENT.label} for the research
            surface, {PRO.label} for the deadline calendar, watch lists, alerts and export. Sign-in
            is by email or Google.
          </>
        ),
      },
      {
        q: 'Who builds Atlas Circular?',
        a: (
          <>
            It&apos;s developed by{' '}
            <a
              href="https://www.kennyarnold.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-green-accent hover:underline"
            >
              Kenny Arnold Design
            </a>
            , made possible by Open States.{' '}
            <Link href="/about" className="text-green-accent hover:underline">
              More about the project →
            </Link>
          </>
        ),
      },
      {
        q: 'How do I get in touch?',
        a: (
          <>
            Email{' '}
            <a href="mailto:kenny@superfun.studio" className="text-green-accent hover:underline">
              kenny@superfun.studio
            </a>{' '}
            with questions, corrections to a classification, or partnership inquiries.
          </>
        ),
      },
    ],
  },
];

export default function FaqPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 space-y-10">
      <GazetteHeader
        title="FAQ"
        subtitle="What Atlas Circular tracks, how it works, and what you get."
      />

      {GROUPS.map(group => (
        <section key={group.title}>
          <h2 className="font-serif text-text-primary text-xl sm:text-2xl mb-4 border-b border-border-default pb-2">
            {group.title}
          </h2>
          <div className="space-y-6">
            {group.items.map(item => (
              <div key={item.q}>
                <h3 className="font-medium text-text-primary mb-1.5">{item.q}</h3>
                <p className="text-text-secondary leading-relaxed">{item.a}</p>
              </div>
            ))}
          </div>
        </section>
      ))}

      <footer className="border-t border-border-default pt-8 text-sm text-text-muted">
        Still have a question?{' '}
        <a href="mailto:kenny@superfun.studio" className="text-green-accent hover:underline">
          Email us
        </a>
        . See also our{' '}
        <Link href="/terms" className="text-green-accent hover:underline">
          Terms of Service
        </Link>{' '}
        and{' '}
        <Link href="/methodology" className="text-green-accent hover:underline">
          methodology
        </Link>
        .
      </footer>
    </div>
  );
}
