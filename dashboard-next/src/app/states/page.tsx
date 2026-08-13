import type { Metadata } from 'next';
import StatesPage from './StatesPage';

// Server wrapper — see the note in methodology/page.tsx.
export const metadata: Metadata = {
  title: 'Standings — circular-economy law by jurisdiction | Atlas Circular',
  description:
    'Which jurisdictions are actually passing circular-economy law: US states and nations ranked ' +
    'by enacted measures, with the EU bloc broken out by member state. Enacted counts, so the ' +
    'comparison holds across borders.',
  alternates: { canonical: '/states/' },
  openGraph: {
    title: 'Standings — circular-economy law by jurisdiction',
    description: 'US states and nations ranked by enacted circular-economy law.',
    url: '/states/',
  },
};

export default function Page() {
  return <StatesPage />;
}
