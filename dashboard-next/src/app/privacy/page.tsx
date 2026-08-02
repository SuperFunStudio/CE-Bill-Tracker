import type { Metadata } from 'next';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';

export const metadata: Metadata = {
  title: 'Privacy Policy — Atlas Circular',
  description:
    'How Atlas Circular collects, uses, and protects your data — accounts, billing, analytics, ' +
    'email, and your rights.',
  alternates: { canonical: '/privacy/' },
};

// NOTE FOR REVIEW (Kenny): have counsel review before treating this as final. The entity, governing
// state, effective year, and the third-party processors listed below reflect the actual stack in this
// repo (Firebase Auth, Stripe, Google Analytics 4, SendGrid) — keep this list in sync if that changes.
const EFFECTIVE_DATE = '2026';
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

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 space-y-8">
      <GazetteHeader
        title="Privacy Policy"
        subtitle="What we collect, why, and the choices you have."
      />

      <p className="text-text-muted text-sm">Effective date: {EFFECTIVE_DATE}</p>

      <p className="text-text-secondary leading-relaxed">
        This Privacy Policy explains how {ENTITY} collects, uses, and shares information when you use
        Atlas Circular — including the website, dashboards, alerts, and API (the &quot;Service&quot;).
        It should be read alongside our{' '}
        <Link href="/terms" className="text-green-accent hover:underline">
          Terms of Service
        </Link>
        . By using the Service, you agree to the practices described here.
      </p>

      <Section n={1} title="Information we collect">
        <p>We collect only what we need to run the Service:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>
            <span className="text-text-primary font-medium">Account information</span> — your email
            address and authentication identifiers, handled through our authentication provider when
            you sign up or sign in. We do not store your password.
          </li>
          <li>
            <span className="text-text-primary font-medium">Subscription &amp; billing information</span>{' '}
            — plan, subscription status, and billing records. Card details are collected and stored by
            our payment processor, not by us.
          </li>
          <li>
            <span className="text-text-primary font-medium">Product data you create</span> — the bills
            you follow (your watch list), alert preferences, saved packaging specifications, saved
            research, and any company-profile details you enter to estimate exposure.
          </li>
          <li>
            <span className="text-text-primary font-medium">Usage &amp; device data</span> — pages
            viewed, features used, approximate location derived from IP, browser and device type, and
            similar analytics, collected to understand and improve the Service.
          </li>
          <li>
            <span className="text-text-primary font-medium">Communications</span> — messages you send
            us (for example, support or access requests) and your email engagement, so we can respond
            and manage the emails you receive.
          </li>
        </ul>
      </Section>

      <Section n={2} title="How we use information">
        <p>We use the information above to:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>provide, maintain, and secure the Service and your account;</li>
          <li>process subscriptions, trials, and billing, and prevent fraud and abuse;</li>
          <li>
            send transactional and subscription email — sign-in, deadline and new-bill alerts you
            opt into, billing notices, the periodic digest, and account notices;
          </li>
          <li>understand usage, debug problems, and improve features and content;</li>
          <li>comply with legal obligations and enforce our Terms.</li>
        </ul>
        <p>
          We do <span className="text-text-primary font-medium">not</span> sell your personal
          information, and we do not use your saved watch list, company profile, or research to train
          third-party models.
        </p>
      </Section>

      <Section n={3} title="Cookies & local storage">
        <p>
          We use cookies and browser local storage for essential functions (keeping you signed in,
          remembering your theme and preferences) and for analytics. Analytics cookies help us measure
          which pages and features are used. You can block or delete cookies in your browser; some
          parts of the Service may not work correctly if you do. We honor browser &quot;Do Not
          Track&quot; where legally required.
        </p>
      </Section>

      <Section n={4} title="Third-party processors">
        <p>
          We share information with a small set of service providers that process it on our behalf,
          under their own terms and safeguards:
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li>
            <span className="text-text-primary font-medium">Google Firebase</span> — account
            authentication.
          </li>
          <li>
            <span className="text-text-primary font-medium">Stripe</span> — subscription payments and
            billing. Card data is handled entirely by Stripe.
          </li>
          <li>
            <span className="text-text-primary font-medium">Google Analytics</span> — product usage
            analytics.
          </li>
          <li>
            <span className="text-text-primary font-medium">SendGrid (Twilio)</span> — transactional
            and subscription email delivery.
          </li>
          <li>
            <span className="text-text-primary font-medium">Google Cloud Platform</span> — hosting and
            infrastructure.
          </li>
        </ul>
        <p>
          We may also disclose information if required by law, to protect our rights or the safety of
          others, or in connection with a merger, acquisition, or sale of assets.
        </p>
      </Section>

      <Section n={5} title="Data retention">
        <p>
          We keep account and product data for as long as your account is active, and for a limited
          period afterward as needed to comply with legal, tax, and accounting obligations, resolve
          disputes, and enforce our agreements. When you close your account we delete or de-identify
          your personal information within a reasonable period, except where retention is required by
          law. Analytics data is retained on a rolling basis.
        </p>
      </Section>

      <Section n={6} title="Your choices & rights">
        <ul className="list-disc pl-6 space-y-1">
          <li>
            <span className="text-text-primary font-medium">Email</span> — every non-essential email
            includes a one-click unsubscribe, and you can manage alert preferences from{' '}
            <Link href="/library" className="text-green-accent hover:underline">
              My Library
            </Link>
            . We still send essential account and billing notices.
          </li>
          <li>
            <span className="text-text-primary font-medium">Access, correction &amp; deletion</span> —
            you may request a copy of your personal information, ask us to correct it, or ask us to
            delete your account and data by emailing us.
          </li>
          <li>
            <span className="text-text-primary font-medium">Regional rights</span> — depending on
            where you live (for example, the EU/UK or California), you may have additional rights over
            your personal data. We honor valid requests as required by applicable law and will not
            discriminate against you for exercising them.
          </li>
        </ul>
      </Section>

      <Section n={7} title="Security">
        <p>
          We use industry-standard measures — encryption in transit, access controls, and trusted
          infrastructure providers — to protect your information. No method of transmission or storage
          is completely secure, so we cannot guarantee absolute security.
        </p>
      </Section>

      <Section n={8} title="International transfers">
        <p>
          We operate in the United States, and our providers may process data in the United States and
          other countries. Where required, we rely on appropriate safeguards for cross-border transfers
          of personal information.
        </p>
      </Section>

      <Section n={9} title="Children's privacy">
        <p>
          The Service is intended for business use by adults and is not directed to children under 18.
          We do not knowingly collect personal information from children. If you believe a child has
          provided us information, contact us and we will delete it.
        </p>
      </Section>

      <Section n={10} title="Changes to this policy">
        <p>
          We may update this Privacy Policy from time to time. The updated version takes effect when
          posted, and we will update the effective date above. Material changes will be communicated
          where appropriate.
        </p>
      </Section>

      <Section n={11} title="Governing law">
        <p>
          This Policy is governed by the laws of the State of {GOVERNING_STATE}, without regard to its
          conflict-of-laws rules.
        </p>
      </Section>

      <Section n={12} title="Contact">
        <p>
          Questions or requests about your privacy? Email{' '}
          <a href="mailto:kenny@superfun.studio" className="text-green-accent hover:underline">
            kenny@superfun.studio
          </a>
          .
        </p>
      </Section>

      <footer className="border-t border-border-default pt-8 text-sm text-text-muted">
        See also our{' '}
        <Link href="/terms" className="text-green-accent hover:underline">
          Terms of Service
        </Link>
        .
      </footer>
    </div>
  );
}
