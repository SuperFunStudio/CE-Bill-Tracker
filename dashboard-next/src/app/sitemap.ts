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
 * The date the bill pages' rendered CONTENT last materially changed. Bump it by hand whenever we change
 * what these pages actually say — not for styling, and not on every deploy.
 *
 * 2026-08-06: the full compliance record (deadlines, fees, enforcement, dimensions) and the "What you
 * must do" step block started rendering on every bill page.
 *
 * Why this exists: `lastmod` used to be the bill's own status_date — a LEGISLATIVE date. A bill last
 * acted on in 2022 kept lastmod=2022 however much the page's content changed, so a crawler diffing
 * lastmod had no reason to recrawl and a sitemap resubmit signalled nothing. Taking the later of the
 * two makes lastmod mean "when this PAGE last changed", which is what the sitemap spec asks of it.
 */
const CONTENT_REVISION = '2026-08-08';

/** Later of the bill's own date and the page-content revision, as YYYY-MM-DD. Bills with no date at
 *  all (82 of them) now get a lastmod too, where they previously emitted none. */
function pageLastModified(billDate: string | null | undefined): string {
  const d = (billDate ?? '').slice(0, 10);
  return d > CONTENT_REVISION ? d : CONTENT_REVISION;
}

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
      lastModified: pageLastModified(b.status_date || b.last_action_date),
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
