import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { cache } from 'react';
import { fetchBill, fetchBills } from '@/lib/api';
import type { BillDetail, BillSummary } from '@/lib/types';
import {
  billSlug,
  billHref,
  fixEncoding,
  formatDate,
  formatInstrumentType,
  resolveSourceLink,
} from '@/lib/utils';
import { jurisdictionDisplayName } from '@/lib/jurisdictions';
import { BillComplianceLayers } from '@/components/bills/BillComplianceLayers';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { WatchStar } from '@/components/watchlist/WatchStar';

const SITE_URL = 'https://www.atlascircular.com';

// Only pre-rendered bill paths exist (this is a static export). A URL with the wrong slug simply 404s;
// internal links and the sitemap always use the canonical slug, and the canonical tag dedupes anyway.
export const dynamicParams = false;

/** One bill's detail, deduped so generateMetadata and the page body don't double-fetch it at build. */
const getBill = cache(async (id: number): Promise<BillDetail | null> => {
  try {
    return await fetchBill(id);
  } catch {
    return null;
  }
});

/** The full ce_relevant corpus, fetched once for generateStaticParams. */
const getAllBills = cache(async (): Promise<BillSummary[]> => {
  return fetchBills({ ce_relevant: true, region: 'all', limit: 5000 });
});

export async function generateStaticParams(): Promise<{ id: string; slug: string }[]> {
  const bills = await getAllBills();
  return bills.map(b => ({ id: String(b.id), slug: billSlug(b) }));
}

/**
 * Human-readable jurisdiction ("California", "Italy", "United States (federal)"). Reuses the shared
 * jurisdiction registry so foreign codes resolve to country names and US "DE" (Delaware) never
 * collides with Germany. Federal gets the "(federal)" qualifier for clarity in the page title.
 */
function jurisdictionLabel(bill: { region: string; state: string }): string {
  if (bill.region === 'US' && bill.state === 'US') return 'United States (federal)';
  return jurisdictionDisplayName(bill.region, bill.state);
}

/** Collapse whitespace and clip to a meta-description-friendly length on a word boundary. */
function clip(text: string | null | undefined, max = 160): string {
  if (!text) return '';
  const s = fixEncoding(text).replace(/\s+/g, ' ').trim();
  if (s.length <= max) return s;
  return s.slice(0, s.lastIndexOf(' ', max - 1)).trimEnd() + '…';
}

export async function generateMetadata({
  params,
}: {
  params: { id: string; slug: string };
}): Promise<Metadata> {
  const bill = await getBill(Number(params.id));
  if (!bill) return { title: 'Bill not found — Atlas Circular' };

  const jur = jurisdictionLabel(bill);
  const num = bill.bill_number ? `${bill.bill_number} · ` : '';
  const cleanTitle = fixEncoding(bill.title) || 'Untitled bill';
  const title = `${num}${cleanTitle} — ${jur} | Atlas Circular`;
  const description =
    clip(bill.ai_summary || bill.description) ||
    `${cleanTitle} — circular-economy legislation tracked in ${jur} on Atlas Circular.`;
  const canonical = billHref(bill);

  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      type: 'article',
      url: canonical,
      siteName: 'Atlas Circular',
      title: `${num}${cleanTitle} — ${jur}`,
      description,
      // A page that sets its own openGraph does NOT inherit the root layout's image, so a bill share
      // would be imageless — fall back to the branded site card. (A per-bill generated card is a
      // future enhancement.) metadataBase in layout.tsx resolves this to an absolute URL.
      images: ['/og-image.png?v=3'],
    },
    twitter: { card: 'summary_large_image', title: `${num}${cleanTitle}`, description, images: ['/og-image.png?v=3'] },
  };
}

/** schema.org Legislation record so search engines can treat the page as the legislation it describes. */
function billJsonLd(bill: BillDetail) {
  const canonical = `${SITE_URL}${billHref(bill)}`;
  const instruments = (bill.instrument_types?.length ? bill.instrument_types : bill.instrument_type ? [bill.instrument_type] : [])
    .map(formatInstrumentType);
  const jsonLd: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Legislation',
    name: fixEncoding(bill.title) || 'Untitled bill',
    url: canonical,
    inLanguage: 'en',
    legislationJurisdiction: jurisdictionLabel(bill),
    isBasedOn: bill.source_url || undefined,
    sameAs: bill.source_url || undefined,
  };
  if (bill.bill_number) jsonLd.legislationIdentifier = bill.bill_number;
  if (instruments.length) jsonLd.legislationType = instruments.join(', ');
  if (bill.status) jsonLd.legislationLegalForce = bill.status.toLowerCase() === 'enacted' ? 'InForce' : 'NotInForce';
  const legDate = bill.last_action_date || bill.status_date;
  if (legDate) jsonLd.legislationDate = legDate;
  if (bill.updated_at) jsonLd.dateModified = bill.updated_at.slice(0, 10);
  const desc = clip(bill.ai_summary || bill.description, 300);
  if (desc) jsonLd.description = desc;
  return jsonLd;
}

export default async function BillPage({ params }: { params: { id: string; slug: string } }) {
  const bill = await getBill(Number(params.id));
  if (!bill) notFound();

  const jur = jurisdictionLabel(bill);
  const cleanTitle = fixEncoding(bill.title) || 'Untitled bill';
  const nativeTitle = bill.title_native && bill.title_native !== bill.title ? fixEncoding(bill.title_native) : null;
  const instruments = (bill.instrument_types?.length ? bill.instrument_types : bill.instrument_type ? [bill.instrument_type] : [])
    .map(formatInstrumentType);
  const link = resolveSourceLink(bill);

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      {/* JSON-LD so a crawler reads the page AS the legislation it describes */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(billJsonLd(bill)) }}
      />

      {/* Breadcrumb / back into the app */}
      <nav className="mb-6 text-sm text-text-muted" aria-label="Breadcrumb">
        <Link href="/compliance" className="text-green-accent hover:underline">
          Legislation
        </Link>
        <span className="mx-1.5">/</span>
        <span>{jur}</span>
      </nav>

      <article className="bg-bg-secondary border border-border-default rounded-lg p-5 sm:p-6 space-y-4">
        {/* ── Identity ── */}
        <header>
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2 flex-wrap mb-2">
              <span className="text-green-accent font-mono font-bold text-sm">{bill.state}</span>
              {bill.bill_number && (
                <span className="text-text-muted font-mono text-sm">{bill.bill_number}</span>
              )}
              <StatusBadge status={bill.status} showCaption dashWhenEmpty={false} />
            </div>
            <WatchStar billId={bill.id} className="text-lg shrink-0" />
          </div>
          <h1 lang="en" className="text-text-primary text-xl sm:text-2xl font-bold leading-snug">
            {cleanTitle}
          </h1>
          {/* Original-language title alongside the English one, with the correct lang/dir so screen
              readers and search engines treat it as the native title it is. Hidden until populated. */}
          {nativeTitle && (
            <p
              lang={bill.title_native_lang || undefined}
              dir="auto"
              className="mt-1 text-text-secondary text-base leading-snug"
            >
              {nativeTitle}
            </p>
          )}
        </header>

        {/* Metadata row */}
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-text-muted border-t border-border-default pt-3">
          <div>
            <dt className="inline">Jurisdiction: </dt>
            <dd className="inline text-text-secondary">{jur}</dd>
          </div>
          <div>
            <dt className="inline">Type: </dt>
            <dd className="inline text-text-secondary">{instruments.join(' · ') || '—'}</dd>
          </div>
          <div>
            <dt className="inline">Last action: </dt>
            <dd className="inline text-text-secondary">{formatDate(bill.last_action_date || bill.status_date)}</dd>
          </div>
        </dl>

        {/* Material category pills */}
        {bill.material_categories && bill.material_categories.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {bill.material_categories.map(cat => (
              <span key={cat} className="bg-bg-primary border border-border-default rounded px-2 py-0.5 text-xs text-green-light">
                {cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
              </span>
            ))}
          </div>
        )}

        {/* AI summary */}
        {bill.ai_summary && (
          <div className="bg-bg-primary rounded p-3 text-body text-text-secondary leading-relaxed">
            {fixEncoding(bill.ai_summary)}
          </div>
        )}

        {/* Compliance content — shared with the in-app detail panel */}
        <BillComplianceLayers cd={bill.compliance_details} />

        {/* Source link */}
        {link && (
          <div className="border-t border-border-default pt-3 space-y-1">
            <a
              href={link.href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-green-accent text-sm hover:underline"
            >
              {link.label}
            </a>
            {link.note && <p className="text-xs text-text-muted">{link.note}</p>}
          </div>
        )}
      </article>

      <p className="mt-6 text-sm text-text-muted">
        Explore more circular-economy legislation on the{' '}
        <Link href="/compliance" className="text-green-accent hover:underline">
          Atlas Circular legislation tracker
        </Link>
        .
      </p>
    </main>
  );
}
