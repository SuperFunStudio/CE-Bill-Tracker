import type { Metadata } from 'next';
import CircularEconomyPage from './CircularEconomyPage';

// Server wrapper for metadata. The page is public on purpose: it is the shareable, visual front door to
// the corpus (the Insights Butterfly tab it grew out of stays Pro-gated with the rest of Insights).
export const metadata: Metadata = {
  title: 'Circular Economy Policies — compare every region, step by step | Atlas Circular',
  description:
    'The circular-economy law of 50+ jurisdictions on one diagram: which steps of the loop each region ' +
    'regulates (repair, reuse, recycling, recycled content, EPR collection, composting) and where the gaps ' +
    'are. Compare two regions and filter by material.',
  alternates: { canonical: '/circular-economy/' },
  openGraph: {
    title: 'Circular Economy Policies — where does your region close the loop?',
    description: 'Compare any two regions on the circular-economy butterfly, by material. See the gaps.',
    url: '/circular-economy/',
  },
};

export default function Page() {
  return <CircularEconomyPage />;
}
