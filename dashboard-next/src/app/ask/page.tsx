import type { Metadata } from 'next';
import AskPage from './AskPage';

// Server wrapper — see the note in methodology/page.tsx.
export const metadata: Metadata = {
  title: 'Ask the Atlas — research circular-economy law | Atlas Circular',
  description:
    'Ask a question about EPR, right-to-repair, deposit-return or recycled-content law and get an ' +
    'answer built from the measures themselves — every claim deep-linked to the filing it came ' +
    'from, so you can check it against the record.',
  alternates: { canonical: '/ask/' },
  openGraph: {
    title: 'Ask the Atlas',
    description:
      'Research circular-economy legislation by question, with every answer linked back to the ' +
      'source filings.',
    url: '/ask/',
  },
};

export default function Page() {
  return <AskPage />;
}
