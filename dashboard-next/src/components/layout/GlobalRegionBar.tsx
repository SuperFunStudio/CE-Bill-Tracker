'use client';
import { useRegion } from './RegionContext';
import { RegionFilter } from '@/components/insights/RegionFilter';

/**
 * Global jurisdiction filter bar — sits under the nav on every page, replacing the old per-page
 * region toggle. Multi-select (one+ regions or All); drives the bill list + insights site-wide via
 * RegionContext. The state/material/product "Personalize your feed" scope lives separately, on the
 * homepage above the bill table.
 */
export function GlobalRegionBar() {
  const { regions, setRegions } = useRegion();
  return (
    <div className="border-b border-border-default bg-bg-secondary">
      <div className="mx-auto max-w-6xl px-6 py-2 flex items-center gap-3">
        <RegionFilter selected={regions} onChange={setRegions} />
      </div>
    </div>
  );
}
