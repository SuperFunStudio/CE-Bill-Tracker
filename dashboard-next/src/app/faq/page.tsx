import type { Metadata } from 'next';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';

export const metadata: Metadata = {
  title: 'FAQ — Battle of the Bills',
  description:
    'Frequently asked questions about Battle of the Bills: what it tracks, where the data comes ' +
    'from, how the AI classification works, what is free vs. Pro, pricing, alerts, and the API.',
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
        q: 'What is Battle of the Bills?',
        a: (
          <>
            Battle of the Bills tracks circularity-aligned legislation across all 50 states and at
            the federal level — Extended Producer Responsibility (EPR), right-to-repair,
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
            landscape. The free tier is built for the latter; the Pro tier is built for regulatory,
            sustainability, and product teams who need every deadline and obligation.
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
            No. Battle of the Bills is an intelligence and research tool, not legal advice. Deadlines
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
        q: 'What is free, and what needs Pro?',
        a: (
          <>
            Free includes the full Bill Explorer and map across all 50 states, state snapshots, the
            Federal Actions tracker, the headline Design Guide imperatives, a personalized feed, and
            a limited alerts filter. Pro adds every extracted obligation date, the full timeline and
            deadline dashboard, personal and shared watch lists, alerts across every instrument with
            custom filters, the complete Design Guide, and CSV export.{' '}
            <Link href="/pricing" className="text-green-accent hover:underline">
              Compare plans →
            </Link>
          </>
        ),
      },
      {
        q: 'How much does Pro cost?',
        a: (
          <>
            Pro is $400/month, or $3,600/year (billed annually — $300/mo, three months free).
            Founding members who join during early access lock in 50% off for life and get a 90-day
            free trial. Cancel anytime.
          </>
        ),
      },
      {
        q: 'Is there a free trial?',
        a: (
          <>
            Yes — Pro starts with a 90-day free trial, no charge until it ends, cancel anytime. New
            accounts also get a short self-serve trial on signup, and you can extend access by
            referring others.
          </>
        ),
      },
      {
        q: 'How do I cancel or manage my plan?',
        a: (
          <>
            From <Link href="/account" className="text-green-accent hover:underline">your account</Link>,
            open <em>Manage plan</em> to reach the billing portal, where you can update payment
            details or cancel. Cancellation stops future renewals; you keep Pro access through the end
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
            Watch lists (Pro) let you and your team follow specific bills and get notified when their
            status or deadlines change. Alerts email you about new and changing legislation; free
            accounts get a limited filter, Pro gets alerts across every instrument with custom
            filters. You can unsubscribe from any email at any time.
          </>
        ),
      },
      {
        q: 'What is the Design Guide?',
        a: (
          <>
            The Design Guide synthesizes what enacted EPR and circularity law actually requires into
            design-for-compliance principles — so product and packaging teams can act on policy, not
            just read it. Free shows the headline imperatives; Pro unlocks the complete guide.
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
            classifications across all 50 states) is available via API, with a rate-limited free
            developer tier and usage-based paid plans. Request access from the{' '}
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
            You can browse the free Bill Explorer and map without one. A free account unlocks a
            personalized feed and alerts; a Pro subscription unlocks the full deadline dashboard,
            watch lists, and export. Sign-in is by email or Google.
          </>
        ),
      },
      {
        q: 'Who builds Battle of the Bills?',
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
        subtitle="What Battle of the Bills tracks, how it works, and what you get."
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
