'use client';
import Link from 'next/link';
import { useRegion } from './RegionContext';
import { RegionFilter, regionLabel } from '@/components/insights/RegionFilter';

/**
 * Profile destination for a single selected region. US → its 50-state standings board; the EU and any
 * single country → that jurisdiction's unified profile (/jurisdictions/[code]/[code]/, eu/eu for the
 * EU-wide view). Mirrors the leaf slugs from allJurisdictionParams().
 */
function regionProfileHref(code: string): string {
  if (code === 'US') return '/states/';
  const c = code.toLowerCase();
  return `/jurisdictions/${c}/${c}/`;
}

/**
 * Global jurisdiction filter bar — sits under the nav on every page, replacing the old per-page
 * region toggle. Multi-select (one+ regions or All); drives the bill list + insights site-wide via
 * RegionContext. The state/material/product "Personalize your feed" scope lives separately, on the
 * homepage above the bill table.
 *
 * When exactly one jurisdiction is selected, a contextual link surfaces that jurisdiction's profile
 * page (or the US standings board) — the way into the per-jurisdiction pages from the bill explorer.
 */
export function GlobalRegionBar() {
  const { regions, setRegions } = useRegion();
  const sole = regions.length === 1 ? regions[0] : null;
  return (
    <div className="border-b border-border-default bg-bg-secondary">
      <div className="mx-auto max-w-6xl px-6 py-2 flex items-center gap-3">
        <RegionFilter selected={regions} onChange={setRegions} />
        {sole && (
          <Link
            href={regionProfileHref(sole)}
            className="ml-auto shrink-0 text-sm text-green-accent hover:underline whitespace-nowrap"
          >
            {sole === 'US' ? 'View state standings' : `View ${regionLabel(sole)} page`} &rarr;
          </Link>
        )}
      </div>
    </div>
  );
}
