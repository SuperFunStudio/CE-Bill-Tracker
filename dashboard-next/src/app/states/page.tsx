import type { Metadata } from 'next';
import StatesPage from './StatesPage';

// Server wrapper — see the note in methodology/page.tsx.
export const metadata: Metadata = {
  title: 'Rankings — benchmarking the regions enabling the circular economy | Atlas Circular',
  description:
    'Which regions are enabling the circular economy: countries ranked by circular-economy law in ' +
    'force, the documented outcomes of that law, and what each region’s laws cover. Enacted counts, ' +
    'so the comparison holds across borders.',
  alternates: { canonical: '/states/' },
  openGraph: {
    title: 'Rankings — benchmarking the regions enabling the circular economy',
    description: 'Countries ranked by enacted circular-economy law, with the outcomes it has produced.',
    url: '/states/',
  },
};

export default function Page() {
  return <StatesPage />;
}
