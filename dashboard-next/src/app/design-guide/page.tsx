import type { Metadata } from 'next';
import DesignGuidePage from './DesignGuidePage';

// Server wrapper — see the note in methodology/page.tsx. This is the richest statically-rendered
// page on the site (the full lever set ships in the export), so it has the most to gain from a
// title and description that actually describe it.
export const metadata: Metadata = {
  title: 'Design for EPR — what the law requires of a product | Atlas Circular',
  description:
    'Design-for-compliance principles synthesized from enacted EPR and circularity law: the ' +
    'material, labeling, recyclability and recycled-content levers legislation actually pulls, ' +
    'each one flipping to the statutes it came from.',
  alternates: { canonical: '/design-guide/' },
  openGraph: {
    title: 'Design for EPR — what the law requires of a product',
    description:
      'The design levers enacted circular-economy law actually pulls, each traceable to the ' +
      'statutes behind it.',
    url: '/design-guide/',
  },
};

export default function Page() {
  return <DesignGuidePage />;
}
