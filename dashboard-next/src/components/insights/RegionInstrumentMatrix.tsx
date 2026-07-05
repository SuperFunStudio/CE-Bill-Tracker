'use client';

import { useEffect, useMemo, useState } from 'react';
import { fetchInstrumentMaterialMatrix } from '@/lib/api';
import { formatInstrumentType } from '@/lib/utils';
import { track } from '@/lib/analytics';
import { BillDrilldownPanel } from './BillDrilldownPanel';
import { regionLabel } from './RegionFilter';
import type { InstrumentMaterialCell } from '@/lib/types';

/**
 * Region × instrument coverage — each region's regulatory "personality" side by side. Rows are the
 * jurisdictions we track (most-active first), columns the policy instruments; a cell is how much that
 * region leans on that tool. Reads the same /bills/instrument-material-matrix feed as the coverage
 * heatmap (grouped by region), summed across materials — so, like that view, a bill spanning several
 * materials is weighted by its material breadth. The signal is the *shape* of each row: EU heavy on
 * ecodesign/other, the US on EPR, France on right-to-repair.
 */

const INSTRUMENT_ORDER = [
  'epr', 'deposit_return', 'recycled_content', 'right_to_repair', 'incentives', 'labeling', 'preemption', 'other',
];

function cellStyle(count: number, max: number): React.CSSProperties {
  if (count === 0 || max === 0) return {};
  const alpha = 0.1 + 0.85 * Math.sqrt(count / max);
  return { background: `rgb(var(--green-accent) / ${alpha.toFixed(3)})` };
}

export function RegionInstrumentMatrix() {
  const [cells, setCells] = useState<InstrumentMaterialCell[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drill, setDrill] = useState<{ region: string; instrument: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchInstrumentMaterialMatrix() // no filter → every region grouped
      .then(d => { if (!cancelled) setCells(d); })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load matrix.'); });
    return () => { cancelled = true; };
  }, []);

  const { regions, instruments, lookup, max } = useMemo(() => {
    if (!cells || cells.length === 0) {
      return { regions: [] as string[], instruments: [] as string[], lookup: new Map<string, number>(), max: 0 };
    }
    const lookup = new Map<string, number>();      // `${region}|${instrument}` -> count
    const regionTotals = new Map<string, number>();
    const present = new Set<string>();
    for (const c of cells) {
      const region = c.region ?? 'US';
      const key = `${region}|${c.instrument_type}`;
      lookup.set(key, (lookup.get(key) ?? 0) + c.count);
      regionTotals.set(region, (regionTotals.get(region) ?? 0) + c.count);
      present.add(c.instrument_type);
    }
    const max = lookup.size ? Math.max(...lookup.values()) : 0;
    const regions = [...regionTotals.keys()].sort((a, b) => (regionTotals.get(b) ?? 0) - (regionTotals.get(a) ?? 0));
    const instruments = INSTRUMENT_ORDER.filter(i => present.has(i));
    return { regions, instruments, lookup, max };
  }, [cells]);

  if (error) return <p className="text-sm text-error">{error}</p>;
  if (!cells) return <div className="h-64 w-full animate-pulse rounded-lg bg-bg-tertiary" />;
  if (regions.length === 0) return <p className="text-text-muted text-sm">No classified coverage to chart yet.</p>;

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-bg-secondary p-2 text-left font-medium text-text-muted">
                Jurisdiction
              </th>
              {instruments.map(inst => (
                <th key={inst} className="p-2 text-center font-medium text-text-secondary align-bottom whitespace-nowrap">
                  {formatInstrumentType(inst)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {regions.map(region => (
              <tr key={region}>
                <td className="sticky left-0 z-10 bg-bg-secondary p-2 text-left text-text-secondary whitespace-nowrap">
                  {regionLabel(region)} <span className="text-text-muted">{region}</span>
                </td>
                {instruments.map(inst => {
                  const count = lookup.get(`${region}|${inst}`) ?? 0;
                  const clickable = count > 0;
                  return (
                    <td
                      key={inst}
                      className={`border border-border-default p-0 text-center tabular-nums ${
                        clickable ? 'cursor-pointer hover:ring-1 hover:ring-inset hover:ring-[rgb(var(--green-accent))]' : ''
                      }`}
                      style={cellStyle(count, max)}
                      title={`${regionLabel(region)} · ${formatInstrumentType(inst)}: ${count}${clickable ? ' — click to see the bills' : ''}`}
                    >
                      {clickable ? (
                        <button
                          type="button"
                          onClick={() => {
                            setDrill({ region, instrument: inst });
                            track('insights_region_instrument_drilldown', { region, instrument: inst });
                          }}
                          className="w-full h-full p-2 text-text-primary font-medium"
                        >
                          {count}
                        </button>
                      ) : (
                        <span className="block p-2 text-text-muted/70">·</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-text-muted text-xs leading-relaxed">
        Read across a row to see a jurisdiction&apos;s regulatory mix. Cells count instrument×material
        coverage (a bill spanning several materials is weighted by its breadth, same as the coverage
        heatmap), so compare the <em>shape</em> of each row rather than raw totals across regions.
        <span className="text-text-secondary"> Click a cell to see the bills.</span>
      </p>

      <BillDrilldownPanel
        open={drill != null}
        onClose={() => setDrill(null)}
        title={drill ? `${regionLabel(drill.region)} · ${formatInstrumentType(drill.instrument)}` : ''}
        subtitle="Bills counted in this cell"
        params={drill ? { ce_relevant: true, instrument_type: drill.instrument, region: drill.region } : null}
        source="region_instrument_matrix"
      />
    </div>
  );
}
