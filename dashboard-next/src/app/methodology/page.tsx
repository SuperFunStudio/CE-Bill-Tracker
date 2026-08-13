import type { Metadata } from 'next';
import MethodologyPage from './MethodologyPage';

/**
 * Server wrapper around the client page, which exists ONLY so this file can export `metadata`.
 * A 'use client' module cannot: Next drops any metadata export from one silently, which is why nine
 * pages — including the three strongest trust artifacts on the site — all shipped with the root
 * layout's generic title. The pattern is the same for each: page.tsx owns the head, the sibling
 * component owns the render.
 */
export const metadata: Metadata = {
  title: 'Methodology — how the Atlas is built | Atlas Circular',
  description:
    'How circular-economy legislation is collected, classified, and checked: our sources, what the ' +
    'AI classifier does and does not decide, confidence scores, human review, and the errors we ' +
    'know about. The fair questions a diligence-minded reader would ask.',
  alternates: { canonical: '/methodology/' },
  openGraph: {
    title: 'Methodology — how the Atlas is built',
    description:
      'Sources, classification, confidence, human review, and known limitations — how Atlas ' +
      'Circular decides what counts as circular-economy law.',
    url: '/methodology/',
  },
};

export default function Page() {
  return <MethodologyPage />;
}
