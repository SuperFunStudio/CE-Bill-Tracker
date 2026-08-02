import type { MetadataRoute } from 'next';

const SITE_URL = 'https://www.atlascircular.com';

/**
 * Allow crawling of the public site, point crawlers at the sitemap (which lists every bill page), and
 * keep gated/utility routes out of the index: account/library/admin (auth-gated), embed (iframe
 * fragments), and the /r and /p share-link surfaces (per-token, not canonical content).
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/account/', '/library/', '/company/', '/admin/', '/embed/', '/r/', '/p/'],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
