import type { Metadata } from 'next';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { SubscribeSection } from '@/components/about/SubscribeSection';

export const metadata: Metadata = {
  title: 'About — Battle of the Bills',
  description:
    'Battle of the Bills tracks circularity-aligned legislation across all 50 states — Extended ' +
    'Producer Responsibility, right-to-repair, deposit-return, recycled-content, and labeling — so ' +
    'producers and advocates can see where policy and market opportunity are building.',
};

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-serif text-text-primary text-xl sm:text-2xl mb-3">{children}</h2>
  );
}

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 space-y-10">
      <GazetteHeader
        title="About"
        subtitle="Who's behind Battle of the Bills, and how it's built."
      />

      {/* Mission — product voice */}
      <section>
        <SectionTitle>Why this exists</SectionTitle>
        <p className="text-text-secondary leading-relaxed">
          Battle of the Bills tracks circularity-aligned legislation across all 50 states. By
          following Extended Producer Responsibility, right-to-repair, deposit-return,
          recycled-content, labeling, and related laws in one place, it makes visible where the
          policy momentum — and the market opportunity for a{' '}
          <span className="text-text-primary font-medium">circular economy</span> — is building, and
          turns a firehose of legislative activity into the handful of bills and deadlines that
          actually affect you.
        </p>
      </section>

      {/* Transparency */}
      <section>
        <SectionTitle>How the analysis works</SectionTitle>
        <p className="text-text-secondary leading-relaxed">
          Every bill is screened against a fixed set of circularity criteria, then auto-classified
          for relevance, policy instrument, and the material streams it touches — with a confidence
          score on each call. Relevant bills get their compliance details (deadlines, covered
          products, producer obligations) extracted from the bill text, and a growing set is
          spot-reviewed by a human. Each bill shows whether its relevance call is auto-classified or
          reviewed, so you always know what you&apos;re looking at.
        </p>
        <p className="text-text-secondary leading-relaxed mt-3">
          Legislative data is sourced from{' '}
          <a
            href="https://openstates.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-accent hover:underline"
          >
            Open States
          </a>{' '}
          (Plural Policy). Classifications are automated and may contain errors; always verify
          against the primary source before relying on any result.{' '}
          <Link href="/methodology" className="text-green-accent hover:underline">
            See the full methodology →
          </Link>
        </p>
      </section>

      {/* Free updates sign-up */}
      <SubscribeSection className="border-t border-border-default pt-8" />

      {/* Plans — replaces the old donation ask now that pricing exists */}
      <section className="border-t border-border-default pt-8">
        <SectionTitle>Plans</SectionTitle>
        <p className="text-text-secondary leading-relaxed mb-4">
          The bill explorer, map, deadline dashboard, and email alerts are free, and they stay free.
          Paid plans — personal watch lists, portfolio-scoped exposure, team features, and API
          access — are how the project stays independent and keeps improving.
        </p>
        <Link
          href="/pricing"
          className="inline-flex items-center gap-2 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          See plans &amp; pricing →
        </Link>
      </section>

      {/* Footer byline */}
      <footer className="border-t border-border-default pt-8 text-center text-sm text-text-muted">
        <p className="mb-3 space-x-3">
          <Link href="/faq" className="text-green-accent hover:underline">FAQ</Link>
          <span>·</span>
          <Link href="/terms" className="text-green-accent hover:underline">Terms of Service</Link>
          <span>·</span>
          <Link href="/methodology" className="text-green-accent hover:underline">Methodology</Link>
        </p>
        Developed by{' '}
        <a
          href="https://www.kennyarnold.com"
          target="_blank"
          rel="noopener noreferrer"
          className="text-green-accent hover:underline"
        >
          Kenny Arnold Design
        </a>{' '}
        and made possible by{' '}
        <a
          href="https://openstates.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-green-accent hover:underline"
        >
          Open States
        </a>
        .
      </footer>
    </div>
  );
}
