import type { Metadata } from 'next';
import FederalPage from './FederalPage';

// Server wrapper — see the note in methodology/page.tsx.
export const metadata: Metadata = {
  title: 'Federal Actions — US agency activity & preemption | Atlas Circular',
  description:
    'US federal action on the circular economy: Federal Register rules, notices and agency ' +
    'proceedings touching EPR, recycled content and labeling — including the measures that would ' +
    'preempt state programs, flagged by preemption risk.',
  alternates: { canonical: '/federal/' },
  openGraph: {
    title: 'Federal Actions — US agency activity & preemption',
    description:
      'Federal Register activity on the circular economy, including what would preempt state EPR law.',
    url: '/federal/',
  },
};

export default function Page() {
  return <FederalPage />;
}
