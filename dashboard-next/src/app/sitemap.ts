import type { MetadataRoute } from 'next';
import { fetchBills } from '@/lib/api';
import { billHref } from '@/lib/utils';

const SITE_URL = 'https://www.atlascircular.com';

// Public, indexable marketing/product pages. Gated or utility routes (/account, /library, /admin,
// /embed, /beta, redirects) are deliberately omitted — see robots.ts, which disallows them.
const STATIC_PATHS = [
  '/',
  '/about/',
  '/pricing/',
  '/faq/',
  '/methodology/',
  '/compliance/',
  '/insights/',
  '/federal/',
  '/states/',
  '/jurisdictions/',
  '/developers/',
  '/evaluate/',
  '/studio/',
  '/label/',
  '/ask/',
  '/terms/',
  '/privacy/',
];

/**
 * The sitemap is the PRIMARY discovery channel for the ~2,450 bill pages — every ce_relevant bill gets
 * its canonical /bill/[id]/[slug]/ URL here so search engines can crawl the long tail directly, not
 * only via in-app links. Generated at build time (static export), so it hits the prod API once.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();

  const staticEntries: MetadataRoute.Sitemap = STATIC_PATHS.map(path => ({
    url: `${SITE_URL}${path}`,
    lastModified: now,
    changeFrequency: 'weekly',
    priority: path === '/' ? 1 : 0.7,
  }));

  let billEntries: MetadataRoute.Sitemap = [];
  try {
    const bills = await fetchBills({ ce_relevant: true, region: 'all', limit: 5000 });
    billEntries = bills.map(b => ({
      url: `${SITE_URL}${billHref(b)}`,
      lastModified: b.status_date || b.last_action_date || undefined,
      changeFrequency: 'monthly',
      priority: 0.6,
    }));
  } catch {
    // If the API is unreachable at build time, still emit a valid sitemap of the static pages rather
    // than failing the whole build.
    billEntries = [];
  }

  return [...staticEntries, ...billEntries];
}
