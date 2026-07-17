import type { Metadata } from 'next';
import { PublishedArticle } from './PublishedArticle';

// Instant self-hosted permalink for a published article (the edited post, not the raw research thread).
// Token rides in the query string (/p/?token=…) because the dashboard is a static export. noindex FOR
// NOW: this client-rendered link is the shareable copy; the future build-time /articles/<slug> library
// is the canonical, indexable one — keeping this out of the index avoids duplicate content later.
export const metadata: Metadata = {
  title: 'Article — Battle of the Bills',
  robots: { index: false, follow: false },
};

export default function PublishedArticlePage() {
  return <PublishedArticle />;
}
