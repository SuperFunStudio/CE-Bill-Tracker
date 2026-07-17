import type { Metadata } from 'next';
import { SharedResearch } from './SharedResearch';

// Public read-only view of a shared "Ask the Bills" thread. The token rides in the query string
// (/r/?token=…) because the dashboard is a static export — a single static route reads it client-side,
// the same way bill deep links use /?bill=<id>. noindex: share links are unlisted, not public content.
export const metadata: Metadata = {
  title: 'Shared research — Atlas Circular',
  robots: { index: false, follow: false },
};

export default function SharedResearchPage() {
  return <SharedResearch />;
}
