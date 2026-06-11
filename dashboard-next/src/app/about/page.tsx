import type { Metadata } from 'next';
import { SubscribeSection } from '@/components/about/SubscribeSection';
import { HeartIcon } from '@/components/ui/icons';

export const metadata: Metadata = {
  title: 'About — Battle of the Bills',
  description:
    'Battle of the Bills tracks circularity-aligned legislation across the United States, ' +
    'designed by Kenny Arnold to make supportive markets for a circular economy visible.',
};

// TODO: replace with the real donation URL once available.
const DONATE_URL = '#';

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-serif text-text-primary text-xl sm:text-2xl mb-3">{children}</h2>
  );
}

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 space-y-10">
      {/* Intro */}
      <header className="space-y-3">
        <h1 className="font-serif uppercase tracking-[0.06em] text-text-primary text-3xl sm:text-4xl">
          About 
        </h1>
      </header>

      {/* Mission */}
      <section>
        <SectionTitle>Why this exists</SectionTitle>
        <p className="text-text-secondary leading-relaxed">
          Battle of the Bills is a tool designed by{' '}
          <span className="text-text-primary font-medium"> <a
            href="https://www.kennyarnold.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-accent hover:underline"
          >
            Kenny Arnold
          </a> </span> to make it visible
          where there are supportive markets for enabling a{' '}
          <span className="text-text-primary font-medium">circular economy</span> in the United
          States. By tracking Extended Producer Responsibility, right-to-repair, deposit-return,
          recycled-content, labeling, and related legislation across all 50 states, it surfaces
          where the policy momentum and the market opportunity is building.
        </p>
      </section>

      {/* Data credit */}
      <section>
        <SectionTitle>Made possible by OpenStates</SectionTitle>
        <p className="text-text-secondary leading-relaxed">
          Legislative data is sourced from{' '}
          <a
            href="https://openstates.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-accent hover:underline"
          >
            OpenStates
          </a>{' '}
          (Plural Policy). This project is built on their publicly available{' '}
          <a
            href="https://open.pluralpolicy.com/data/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-accent hover:underline"
          >
            bulk legislative dataset
          </a>
          , without which none of this would be possible.
        </p>
      </section>

      {/* Transparency */}
      <section>
        <SectionTitle>How the analysis works</SectionTitle>
        <p className="text-text-secondary leading-relaxed">
          In the interest of transparency: bills are classified for relevance and policy
          instrument using{' '}
          <span className="text-text-primary font-medium">Claude Haiku</span>, and compliance
          details are extracted with Claude Sonnet. This project was created in collaboration with{' '}
          <span className="text-text-primary font-medium">Claude Opus 4.6</span> and, to date, has
          cost approximately{' '}
          <span className="text-text-primary font-medium">4,000,000 tokens</span> of AI analysis.
          Classifications are automated and may contain errors; always verify against the primary
          source before relying on any result.
        </p>
      </section>

      {/* Free updates sign-up */}
      <SubscribeSection className="border-t border-border-default pt-8" />

      {/* Support */}
      <section className="border-t border-border-default pt-8">
        <SectionTitle>Support this project</SectionTitle>
        <p className="text-text-secondary leading-relaxed mb-4">
          Battle of the Bills is independently built and maintained. If it&apos;s useful to you,
          consider donating to cover costs to help keep it running.
        </p>
        <a
          href={DONATE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          <HeartIcon className="text-base" /> Donate to support this project!
        </a>
      </section>
    </div>
  );
}
