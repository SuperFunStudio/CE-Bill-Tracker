'use client';

import { useEffect, useMemo, useState } from 'react';
import { fetchInstrumentMaterialMatrix } from '@/lib/api';
import { formatInstrumentType } from '@/lib/utils';
import { formatMaterial } from '@/components/scope/ScopeOnboarding';
import type { InstrumentMaterialCell } from '@/lib/types';

/**
 * Instrument × material coverage heatmap. Each cell is the count of EPR-relevant bills applying a
 * policy instrument (columns) to a material (rows); a bill tagging several materials counts in each.
 * The point is as much the *empty* cells as the full ones — the white space shows where a material
 * has, say, deposit-return precedent but no EPR yet. Confidence floor applied server-side.
 */

// Canonical column order (mirrors INSTRUMENT_TYPES in BillFilters / the classifier enum).
const INSTRUMENT_ORDER = [
  'epr', 'deposit_return', 'recycled_content', 'right_to_repair', 'incentives', 'labeling', 'preemption', 'other',
];

// Cell tint: green-accent at an opacity scaled by count. sqrt compresses the long tail (1..200+)
// so mid-range cells stay distinguishable instead of washing out next to the biggest.
function cellStyle(count: number, max: number): React.CSSProperties {
  if (count === 0 || max === 0) return {};
  const alpha = 0.1 + 0.85 * Math.sqrt(count / max);
  return { background: `rgb(var(--green-accent) / ${alpha.toFixed(3)})` };
}

export function InstrumentMaterialMatrix() {
  const [cells, setCells] = useState<InstrumentMaterialCell[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchInstrumentMaterialMatrix()
      .then((d) => {
        if (!cancelled) setCells(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load matrix.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const { instruments, materials, lookup, max } = useMemo(() => {
    if (!cells || cells.length === 0) {
      return { instruments: [] as string[], materials: [] as string[], lookup: new Map<string, number>(), max: 0 };
    }
    const lookup = new Map<string, number>();
    const matTotals = new Map<string, number>();
    const presentInstruments = new Set<string>();
    let max = 0;
    for (const c of cells) {
      lookup.set(`${c.instrument_type}|${c.material_category}`, c.count);
      matTotals.set(c.material_category, (matTotals.get(c.material_category) ?? 0) + c.count);
      presentInstruments.add(c.instrument_type);
      if (c.count > max) max = c.count;
    }
    // Columns: canonical order, only those present. Rows: materials sorted most-regulated first.
    const instruments = INSTRUMENT_ORDER.filter((i) => presentInstruments.has(i));
    const materials = [...matTotals.keys()].sort((a, b) => (matTotals.get(b) ?? 0) - (matTotals.get(a) ?? 0));
    return { instruments, materials, lookup, max };
  }, [cells]);

  if (error) return <p className="text-sm text-error">{error}</p>;
  if (!cells) return <div className="h-64 w-full animate-pulse rounded-lg bg-bg-tertiary" />;
  if (materials.length === 0) {
    return <p className="text-text-muted text-sm">No classified coverage to chart yet.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-bg-secondary p-2 text-left font-medium text-text-muted">
                Material
              </th>
              {instruments.map((inst) => (
                <th
                  key={inst}
                  className="p-2 text-center font-medium text-text-secondary align-bottom whitespace-nowrap"
                >
                  {formatInstrumentType(inst)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {materials.map((mat) => (
              <tr key={mat}>
                <td className="sticky left-0 z-10 bg-bg-secondary p-2 text-left text-text-secondary whitespace-nowrap">
                  {formatMaterial(mat)}
                </td>
                {instruments.map((inst) => {
                  const count = lookup.get(`${inst}|${mat}`) ?? 0;
                  return (
                    <td
                      key={inst}
                      className="border border-border-default p-2 text-center tabular-nums"
                      style={cellStyle(count, max)}
                      title={`${formatInstrumentType(inst)} × ${formatMaterial(mat)}: ${count} ${
                        count === 1 ? 'bill' : 'bills'
                      }`}
                    >
                      <span className={count > 0 ? 'text-text-primary font-medium' : 'text-text-muted/70'}>
                        {count > 0 ? count : '·'}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-text-muted text-xs leading-relaxed">
        Each cell counts EPR-relevant bills applying that instrument to that material; a bill spanning
        several materials counts in each. Shading is relative, not linear — read the number, not just the
        tint. The blank cells are the live signal — a material with deposit-return precedent but an empty
        EPR column is where the next bills tend to land. Auto-classified at a 0.7 confidence floor.
      </p>
    </div>
  );
}
