import type { Metadata } from 'next';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';

export const metadata: Metadata = {
  title: 'Terms of Service — Atlas Circular',
  description:
    'The terms governing use of Atlas Circular — the circularity-legislation intelligence ' +
    'service: accounts, subscriptions, acceptable use, data, disclaimers, and liability.',
};

// NOTE FOR REVIEW (Kenny): have counsel review before treating this as final, but the entity,
// governing-law state, and effective year below are confirmed.
const EFFECTIVE_DATE = '2024';
const ENTITY = 'SUPERFUN STUDIO LLC ("we," "us," or "the Company")';
const GOVERNING_STATE = 'New York';

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-serif text-text-primary text-lg sm:text-xl mb-2">
        {n}. {title}
      </h2>
      <div className="space-y-3 text-text-secondary leading-relaxed">{children}</div>
    </section>
  );
}

export default function TermsPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 space-y-8">
      <GazetteHeader
        title="Terms of Service"
        subtitle="The agreement between you and Atlas Circular."
      />

      <p className="text-text-muted text-sm">Effective date: {EFFECTIVE_DATE}</p>

      <p className="text-text-secondary leading-relaxed">
        These Terms of Service (the &quot;Terms&quot;) govern your access to and use of Atlas
        Circular, including the website,
        dashboards, alerts, and API (collectively, the &quot;Service&quot;), operated by {ENTITY}. By
        accessing or using the Service, or by creating an account, you agree to be bound by these
        Terms. If you do not agree, do not use the Service.
      </p>

      <Section n={1} title="The Service">
        <p>
          Atlas Circular is an intelligence and research tool that aggregates, classifies, and
          summarizes legislation and regulatory actions related to the circular economy — including
          Extended Producer Responsibility, right-to-repair, recycled-content, deposit-return,
          labeling, and federal preemption — across U.S. jurisdictions. We may add, change, or remove
          features at any time.
        </p>
      </Section>

      <Section n={2} title="Not legal advice; no reliance">
        <p>
          The Service does not provide legal, regulatory, financial, or professional advice, and no
          attorney-client or advisory relationship is created by your use of it. Content — including
          relevance classifications, deadlines, covered-product determinations, producer
          obligations, exposure estimates, and design guidance — is generated in part by automated
          systems (including large language models) and may be incomplete, out of date, or
          incorrect.
        </p>
        <p className="text-text-primary font-medium">
          You must independently verify any information against the official primary source before
          relying on it, and you should consult qualified counsel regarding your specific compliance
          obligations. You are solely responsible for your compliance decisions.
        </p>
      </Section>

      <Section n={3} title="Eligibility & accounts">
        <p>
          You must be at least 18 years old and able to form a binding contract to use the Service.
          When you create an account you agree to provide accurate information and to keep your
          credentials secure. You are responsible for all activity under your account. We may suspend
          or terminate accounts that violate these Terms.
        </p>
      </Section>

      <Section n={4} title="Subscriptions, trials & billing">
        <p>
          The Service offers a free tier and paid subscriptions (&quot;Pro&quot;), as described on
          our{' '}
          <Link href="/pricing" className="text-green-accent hover:underline">
            pricing page
          </Link>
          . Paid plans are billed in advance on a monthly or annual basis through our third-party
          payment processor. Pricing, including any founding-member or promotional offer, is governed
          by the terms presented at the time of purchase.
        </p>
        <p>
          Paid plans may begin with a free trial. If you do not cancel before the trial ends, the
          plan converts to a paid subscription and your payment method is charged. Subscriptions
          renew automatically until cancelled.
        </p>
        <p>
          You may cancel at any time from your account&apos;s billing portal. Cancellation stops
          future renewals; you retain access through the end of the period already paid for. Except
          where required by law, payments are non-refundable and partial periods are not prorated. We
          may change prices on renewal with reasonable notice.
        </p>
      </Section>

      <Section n={5} title="Acceptable use">
        <p>You agree not to:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>
            scrape, harvest, or bulk-extract data from the Service except through the API in
            accordance with its documented limits;
          </li>
          <li>
            resell, redistribute, sublicense, or build a competing product from the Service&apos;s
            data or output without our written permission;
          </li>
          <li>
            circumvent access controls, rate limits, or paywalls, or share credentials beyond the
            seats covered by your plan;
          </li>
          <li>
            interfere with, overload, or attempt to gain unauthorized access to the Service or its
            infrastructure;
          </li>
          <li>use the Service for any unlawful purpose or in violation of any third-party rights.</li>
        </ul>
      </Section>

      <Section n={6} title="API terms">
        <p>
          If you access the API, you agree to stay within the rate limits and usage tier associated
          with your key, to keep your key confidential, and to attribute data sources where required.
          We may revoke API access for abuse or to protect the Service. API access is provided
          &quot;as is&quot; under the same disclaimers and limitations in these Terms.
        </p>
      </Section>

      <Section n={7} title="Intellectual property & data sources">
        <p>
          The Service&apos;s software, design, classifications, syntheses, and compilations are owned
          by the Company and protected by intellectual-property laws. Subject to these Terms, we grant
          you a limited, non-exclusive, non-transferable right to use the Service for your internal
          business or personal purposes.
        </p>
        <p>
          Underlying legislative data is sourced from{' '}
          <a
            href="https://openstates.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-accent hover:underline"
          >
            Open States
          </a>{' '}
          (Plural Policy) and the U.S. Federal Register, and remains subject to their respective terms
          and licenses. We do not claim ownership of the underlying public legislative records.
        </p>
      </Section>

      <Section n={8} title="Third-party services">
        <p>
          The Service relies on third-party providers for authentication, payments, email, hosting,
          and data (for example, identity and payment processors and the data sources above). Your
          use of those features may be subject to the third party&apos;s terms, and we are not
          responsible for their acts or omissions.
        </p>
      </Section>

      <Section n={9} title="Privacy">
        <p>
          We collect and process account and usage information to operate the Service, including email
          for authentication and alerts. We do not sell your personal information. You may unsubscribe
          from non-essential emails at any time. For questions about data handling, contact{' '}
          <a href="mailto:kenny@superfun.studio" className="text-green-accent hover:underline">
            kenny@superfun.studio
          </a>
          .
        </p>
      </Section>

      <Section n={10} title="Disclaimer of warranties">
        <p className="uppercase text-sm tracking-wide">
          The Service is provided &quot;as is&quot; and &quot;as available,&quot; without warranties
          of any kind, whether express, implied, or statutory, including any implied warranties of
          merchantability, fitness for a particular purpose, accuracy, or non-infringement. We do not
          warrant that the Service will be uninterrupted, error-free, or that any classification,
          deadline, or other output is complete or correct.
        </p>
      </Section>

      <Section n={11} title="Limitation of liability">
        <p className="uppercase text-sm tracking-wide">
          To the maximum extent permitted by law, the Company and its contributors will not be liable
          for any indirect, incidental, special, consequential, or punitive damages, or for any loss
          of profits, data, goodwill, or for any compliance penalties, fines, or missed deadlines,
          arising out of or relating to your use of the Service. Our total aggregate liability for any
          claim relating to the Service will not exceed the greater of the amounts you paid us in the
          twelve months before the claim, or USD $100.
        </p>
      </Section>

      <Section n={12} title="Indemnification">
        <p>
          You agree to indemnify and hold harmless the Company from any claims, damages, liabilities,
          and expenses (including reasonable legal fees) arising from your use of the Service, your
          violation of these Terms, or your violation of any law or third-party right.
        </p>
      </Section>

      <Section n={13} title="Changes & termination">
        <p>
          We may modify these Terms from time to time; the updated version takes effect when posted,
          and your continued use constitutes acceptance. We may suspend or terminate the Service or
          your access at any time, with or without cause. You may stop using the Service and close
          your account at any time.
        </p>
      </Section>

      <Section n={14} title="Governing law">
        <p>
          These Terms are governed by the laws of the State of {GOVERNING_STATE}, without regard to
          its conflict-of-laws rules. Any dispute will be brought exclusively in the state or federal
          courts located in {GOVERNING_STATE}, and you consent to their jurisdiction.
        </p>
      </Section>

      <Section n={15} title="Contact">
        <p>
          Questions about these Terms? Email{' '}
          <a href="mailto:kenny@superfun.studio" className="text-green-accent hover:underline">
            kenny@superfun.studio
          </a>
          .
        </p>
      </Section>

      <footer className="border-t border-border-default pt-8 text-sm text-text-muted">
        See also our{' '}
        <Link href="/faq" className="text-green-accent hover:underline">
          FAQ
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
