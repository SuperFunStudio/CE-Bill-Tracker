'use client';
import { useEffect, useMemo, useState } from 'react';
import { useBills } from '@/hooks/useBills';
import { BillTable } from '@/components/bills/BillTable';
import {
  BillFilters,
  DEFAULT_FILTERS,
  applyBillFilters,
  type BillFilterState,
} from '@/components/bills/BillFilters';
import { AlertBanner } from '@/components/ui/AlertBanner';

/**
 * Chrome-free Bill Explorer for embedding in a host site (e.g. a Squarespace Code
 * Block) via an <iframe>. The view is configured entirely through URL query params
 * so the same static build can power many differently-scoped embeds:
 *
 *   ?theme=dark         force dark mode (default: light)
 *   ?state=CA           preset the State filter (still interactive)
 *   ?status=enacted     preset the Status filter
 *   ?instrument=epr     preset the Instrument filter
 *   ?material=plastic_packaging   preset the Material filter
 *   ?search=foam        preset the search box
 *   ?filters=0          hide the filter bar (locked, read-only view)
 *   ?heading=0          hide the small "N bills" heading + "open full tracker" link
 *   ?rows=8             rows per page (default 8)
 *
 * It also posts its content height to the parent window so the host can auto-resize
 * the iframe — see the snippet in dashboard-next/EMBED.md.
 */

interface EmbedConfig {
  theme: 'light' | 'dark';
  preset: Partial<BillFilterState>;
  showFilters: boolean;
  showHeading: boolean;
  rows: number;
}

function readConfig(): EmbedConfig {
  const p = new URLSearchParams(window.location.search);
  const preset: Partial<BillFilterState> = {};
  if (p.get('state')) preset.state = p.get('state')!.toUpperCase();
  if (p.get('status')) preset.status = p.get('status')!;
  if (p.get('instrument')) preset.instrumentType = p.get('instrument')!;
  if (p.get('material')) preset.materialCategory = p.get('material')!;
  if (p.get('search')) preset.search = p.get('search')!;

  const rows = Number.parseInt(p.get('rows') ?? '', 10);

  return {
    theme: p.get('theme') === 'dark' ? 'dark' : 'light',
    preset,
    showFilters: p.get('filters') !== '0',
    showHeading: p.get('heading') !== '0',
    rows: Number.isFinite(rows) && rows > 0 ? rows : 8,
  };
}

export default function EmbedPage() {
  // Config is null until mounted (query params are only available client-side).
  const [config, setConfig] = useState<EmbedConfig | null>(null);
  const [filters, setFilters] = useState<BillFilterState>(DEFAULT_FILTERS);
  const [siteRoot, setSiteRoot] = useState('/');

  // Resolve query-param config once, on mount.
  useEffect(() => {
    const c = readConfig();
    setConfig(c);
    setFilters({ ...DEFAULT_FILTERS, ...c.preset });
    document.documentElement.classList.toggle('dark', c.theme === 'dark');
    setSiteRoot(window.location.origin + '/');
  }, []);

  const { data: bills = [], isLoading, error } = useBills({ epr_relevant: true, limit: 5000 });

  const tableBills = useMemo(() => applyBillFilters(bills, filters), [bills, filters]);

  // Tell the parent window how tall we are, so it can size the iframe to fit.
  // Posts on every layout change (filter results shrink/grow the table).
  useEffect(() => {
    const post = () => {
      const height = document.documentElement.scrollHeight;
      window.parent?.postMessage({ type: 'signalscout-embed-height', height }, '*');
    };
    post();
    const ro = new ResizeObserver(post);
    ro.observe(document.documentElement);
    return () => ro.disconnect();
  }, [tableBills.length, isLoading, config]);

  if (!config) return null;

  return (
    <div className="bg-bg-primary text-text-primary p-4 sm:p-5 space-y-4">
      {config.showHeading && (
        <div className="flex items-baseline justify-between gap-3">
          <div className="flex items-baseline gap-2">
            <h2 className="font-serif text-lg text-text-primary">Bill Explorer</h2>
            <span className="text-text-muted text-sm tabular-nums">{tableBills.length} bills</span>
          </div>
          <a
            href={siteRoot}
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-accent text-xs hover:underline shrink-0"
          >
            Open full tracker ↗
          </a>
        </div>
      )}

      {config.showFilters && <BillFilters filters={filters} onChange={setFilters} />}

      {error && (
        <AlertBanner variant="red" message="Could not load bill data. Please try again shortly." />
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-bg-secondary rounded animate-pulse" />
          ))}
        </div>
      ) : (
        <BillTable bills={tableBills} autoPageSize={config.rows} />
      )}

      <div className="text-text-muted text-[11px] text-right pt-1">
        Powered by{' '}
        <a href={siteRoot} target="_blank" rel="noopener noreferrer" className="hover:underline">
          Battle of the Bills
        </a>
      </div>
    </div>
  );
}
