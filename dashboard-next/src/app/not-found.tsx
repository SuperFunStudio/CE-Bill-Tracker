import type { Metadata } from 'next';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';

/**
 * The real 404. Until now this file didn't exist and it wouldn't have mattered if it had: Firebase
 * Hosting rewrote every unmatched path to /index.html, so an unknown URL returned the homepage with a
 * 200. That is a soft 404, and the cost was concrete — paths from the domain's previous life kept
 * returning a live page, so search engines went on indexing content this product never served and the
 * tracker shared its search identity with a retired project. Removing the catch-all rewrite in
 * firebase.json is what makes this page reachable; Next emits it as out/404.html, which Firebase
 * serves (with a 404 status) for any path that doesn't match a file.
 *
 * noindex on top of the status code: a 404 shouldn't need it, but the pages that led here were
 * indexed under a 200 and belt-and-braces costs nothing while that backlog clears.
 */
export const metadata: Metadata = {
  title: 'Page not found — Atlas Circular',
  robots: { index: false, follow: true },
};

const DESTINATIONS = [
  { href: '/', label: 'Explore the tracker', desc: 'Every circular-economy bill we track, by jurisdiction.' },
  { href: '/states/', label: 'Standings', desc: 'Which jurisdictions are moving, ranked.' },
  { href: '/methodology/', label: 'Methodology', desc: 'What we track, how it is classified, and what we get wrong.' },
  { href: '/about/', label: 'About', desc: 'Who builds the Atlas and why.' },
];

export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 space-y-8">
      <GazetteHeader
        title="Page not found"
        subtitle="That address isn't part of the Atlas."
      />
      <p className="text-text-secondary text-body leading-relaxed">
        The page you asked for doesn&apos;t exist here — it may have moved, or the link may be from an
        older site that used this domain. Here&apos;s where most people are heading:
      </p>
      <ul className="space-y-3">
        {DESTINATIONS.map(d => (
          <li key={d.href} className="border-b border-border-default pb-3">
            <Link href={d.href} className="text-green-accent hover:underline font-medium">
              {d.label} <span aria-hidden>→</span>
            </Link>
            <p className="text-text-muted text-sm mt-0.5">{d.desc}</p>
          </li>
        ))}
      </ul>
      <p className="text-text-muted text-sm">
        Landed here from a link we published? Tell us at{' '}
        <a href="mailto:hello@atlascircular.com" className="underline hover:text-text-secondary">
          hello@atlascircular.com
        </a>{' '}
        and we&apos;ll fix it.
      </p>
    </div>
  );
}
