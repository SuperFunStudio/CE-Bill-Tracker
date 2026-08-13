import type { Metadata } from 'next';
import InsightsPage from './InsightsPage';

// Server wrapper — see the note in methodology/page.tsx. The page itself is membership-gated, but the
// URL is public and sitemapped: the gate is what sells, so it needs a description that says what is
// behind it rather than inheriting a generic one.
export const metadata: Metadata = {
  title: 'Insights — where circular-economy law is moving | Atlas Circular',
  description:
    'Analysis across the corpus: momentum by year and jurisdiction, laws in force worldwide, ' +
    'instrument-by-material coverage, the gaps between states, and the documented real-world ' +
    'outcomes of enacted circular-economy law.',
  alternates: { canonical: '/insights/' },
  openGraph: {
    title: 'Insights — where circular-economy law is moving',
    description:
      'Momentum, coverage and outcomes across the circular-economy legislation corpus.',
    url: '/insights/',
  },
};

export default function Page() {
  return <InsightsPage />;
}
