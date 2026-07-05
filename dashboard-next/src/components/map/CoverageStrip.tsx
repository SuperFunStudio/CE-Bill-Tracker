'use client';
import { regionLabel } from '@/components/insights/RegionFilter';

// Shown in place of a map when no single region is selected ("All regions"). A world overview of
// sparse, mixed-granularity coverage reads poorly; a ranked bar list is the honest at-a-glance —
// real counts (Tufte: integrate text + value, no bubble-area guessing), sorted, and each row selects
// that region (the Regions dropdown stays the primary control; this mirrors it).
interface CoverageStripProps {
  /** Region code → law/bill count, e.g. { US: 412, EU: 38, JP: 6 }. */
  data: Record<string, number>;
  onSelect: (code: string) => void;
}

export function CoverageStrip({ data, onSelect }: CoverageStripProps) {
  const rows = Object.entries(data)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);

  // No data (e.g. local dev with the API blocked) — render nothing; the bill table below carries it.
  if (!rows.length) return null;

  const max = rows[0][1];

  return (
    <div className="rounded-lg border border-border-default bg-bg-secondary/40 p-4">
      <div className="mb-3 text-meta uppercase tracking-wider text-text-muted">
        Coverage · laws tracked by region
      </div>
      <div className="space-y-1.5">
        {rows.map(([code, n]) => (
          <button
            key={code}
            type="button"
            onClick={() => onSelect(code)}
            aria-label={`${regionLabel(code)}: ${n} laws — explore`}
            className="group flex w-full items-center gap-3 text-left"
          >
            <span className="w-40 shrink-0 truncate text-sm text-text-secondary group-hover:text-text-primary">
              {regionLabel(code)}
            </span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-bg-primary">
              <span
                className="block h-full rounded-full bg-green-accent/70 transition-colors group-hover:bg-green-accent"
                style={{ width: `${Math.max(4, (n / max) * 100)}%` }}
              />
            </span>
            <span className="w-10 shrink-0 text-right text-sm tabular-nums text-text-primary">{n}</span>
          </button>
        ))}
      </div>
      <div className="mt-3 text-meta text-text-muted">
        Pick a region above — or click one here — to open its map &amp; bills.
      </div>
    </div>
  );
}
