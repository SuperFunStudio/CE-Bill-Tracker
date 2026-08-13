import type { Metadata } from 'next';
import PricingPage from './PricingPage';

// Server wrapper — see the note in methodology/page.tsx.
export const metadata: Metadata = {
  title: 'Pricing — Student, Researcher, Professional | Atlas Circular',
  description:
    'Plans for tracking circular-economy and EPR law: free bill explorer, free Student access on a ' +
    'verified .edu address, Researcher from $20/mo, and Professional with the deadline calendar, ' +
    'alerts and watch lists. Founding rate is half list price, capped at 50 seats.',
  alternates: { canonical: '/pricing/' },
  openGraph: {
    title: 'Pricing — Atlas Circular',
    description:
      'What it costs to stop tracking EPR deadlines by hand. Free explorer, free for students, ' +
      'and a founding rate at half list price.',
    url: '/pricing/',
  },
};

export default function Page() {
  return <PricingPage />;
}
