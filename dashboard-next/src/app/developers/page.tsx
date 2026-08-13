import type { Metadata } from 'next';
import DevelopersPage from './DevelopersPage';

// Server wrapper — see the note in methodology/page.tsx.
export const metadata: Metadata = {
  title: 'API & developer docs | Atlas Circular',
  description:
    'The Atlas Circular API: read endpoints for circular-economy bills, statuses, compliance ' +
    'deadlines and classifications across every jurisdiction we track, with rate limits, response ' +
    'shapes, and how to request higher-volume access.',
  alternates: { canonical: '/developers/' },
  openGraph: {
    title: 'Atlas Circular API',
    description:
      'Query circular-economy legislation, deadlines and classifications programmatically.',
    url: '/developers/',
  },
};

export default function Page() {
  return <DevelopersPage />;
}
