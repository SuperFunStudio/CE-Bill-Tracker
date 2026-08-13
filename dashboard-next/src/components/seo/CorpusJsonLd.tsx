import { REGION_CODES, regionLabel } from '@/components/insights/RegionFilter';

const SITE_URL = 'https://www.atlascircular.com';
const API_URL = 'https://api.atlascircular.com';

/**
 * schema.org `Dataset` markup for the homepage — the machine-readable answer to "what IS this site".
 *
 * Individual bill pages already carry `Legislation`, which describes one measure. Nothing described
 * the corpus as a corpus, so a crawler landing on the front door saw an empty shell: the homepage
 * HTML is a ~36 KB frame and every bill is fetched client-side, which means a client that doesn't run
 * JavaScript — most crawlers, and every AI crawler worth reaching — found no content at all. This is
 * what it finds instead.
 *
 * Deliberately NO record counts. "2,493 measures" is true for about a day, and a static page can't
 * refresh it; a stale precise number is worse than none, because it invites a confident wrong
 * citation. `distribution` points at the live endpoints instead, including the per-region coverage
 * one — so anything wanting a figure can fetch the real current figure rather than quote this file.
 *
 * spatialCoverage is derived from REGION_CODES rather than listed by hand, so a new jurisdiction
 * adapter shows up here automatically instead of quietly making this markup wrong.
 */
export function CorpusJsonLd() {
  const dataset = {
    '@context': 'https://schema.org',
    '@type': 'Dataset',
    '@id': `${SITE_URL}/#dataset`,
    name: 'Atlas Circular — circular-economy and EPR legislation corpus',
    description:
      'A continuously-updated, normalised corpus of circular-economy and extended-producer-' +
      'responsibility law: bills and enacted measures with jurisdiction, status, policy instrument ' +
      'type, covered materials, compliance deadlines and producer fee data, each linked to its ' +
      'primary source document. Coverage is not uniform across jurisdictions — see the ' +
      'text-coverage endpoint for real per-region figures before citing completeness.',
    url: SITE_URL,
    sameAs: `${SITE_URL}/methodology/`,
    isAccessibleForFree: true,
    creator: { '@id': `${SITE_URL}/#organization` },
    publisher: { '@id': `${SITE_URL}/#organization` },
    inLanguage: 'en',
    keywords: [
      'extended producer responsibility',
      'EPR',
      'circular economy',
      'packaging legislation',
      'deposit return scheme',
      'right to repair',
      'recycled content',
      'producer fees',
      'compliance deadlines',
      'environmental law',
    ],
    // Country/bloc codes the corpus tracks. Grows with the adapter list, not with an edit here.
    spatialCoverage: REGION_CODES.map(code => ({
      '@type': 'Place',
      name: regionLabel(code),
      identifier: code,
    })),
    distribution: [
      {
        '@type': 'DataDownload',
        name: 'Tracked measures (filterable)',
        encodingFormat: 'application/json',
        contentUrl: `${API_URL}/bills`,
      },
      {
        '@type': 'DataDownload',
        name: 'Full-text search across ingested statute text',
        encodingFormat: 'application/json',
        contentUrl: `${API_URL}/bills/search`,
      },
      {
        '@type': 'DataDownload',
        name: 'Per-region coverage — the honest completeness figures',
        encodingFormat: 'application/json',
        contentUrl: `${API_URL}/bills/text-coverage?by_region=true`,
      },
      {
        '@type': 'DataDownload',
        name: 'Upcoming compliance deadlines',
        encodingFormat: 'application/json',
        contentUrl: `${API_URL}/bills/deadlines/upcoming`,
      },
      {
        '@type': 'DataDownload',
        name: 'Producer fee schedules',
        encodingFormat: 'application/json',
        contentUrl: `${API_URL}/compliance/fee-schedule`,
      },
    ],
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(dataset) }}
    />
  );
}
