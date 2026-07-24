'use client';

import { useEffect, useMemo, useState } from 'react';
import { fetchInstrumentMaterialMatrix } from '@/lib/api';
import { formatInstrumentType } from '@/lib/utils';
import { formatMaterial } from '@/components/scope/ScopeOnboarding';
import { track } from '@/lib/analytics';
import { sequentialFill } from '@/lib/charts/theme';
import { BillDrilldownPanel } from './BillDrilldownPanel';
import { EnactedOnlyToggle } from './EnactedOnlyToggle';
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

export function InstrumentMaterialMatrix({ regions }: { regions?: string } = {}) {
  const [cells, setCells] = useState<InstrumentMaterialCell[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Clicking a cell drills into the bills it counts. region for the drill: a single selected region
  // narrows to it; All / multi-select falls back to "all" (the bills list endpoint is single-region
  // today — the global multi-region filter refines this). Each drilled bill shows its own region.
  const [drill, setDrill] = useState<{ instrument: string; material: string } | null>(null);
  // Default to enacted-only: US regions carry a large introduced-bill pipeline that would otherwise
  // dwarf foreign/EU regions we track only once they're law. Toggle off to include the full pipeline.
  const [enactedOnly, setEnactedOnly] = useState(true);
  const selectedRegions = (regions ?? '').split(',').map((s) => s.trim()).filter(Boolean);
  const regionForDrill = selectedRegions.length === 1 ? selectedRegions[0] : 'all';

  useEffect(() => {
    let cancelled = false;
    fetchInstrumentMaterialMatrix({ regions, status: enactedOnly ? 'enacted' : undefined })
      .then((d) => {
        if (!cancelled) setCells(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load matrix.');
      });
    return () => {
      cancelled = true;
    };
  }, [regions, enactedOnly]);

  const { instruments, materials, lookup, max } = useMemo(() => {
    if (!cells || cells.length === 0) {
      return { instruments: [] as string[], materials: [] as string[], lookup: new Map<string, number>(), max: 0 };
    }
    const lookup = new Map<string, number>();
    const matTotals = new Map<string, number>();
    const presentInstruments = new Set<string>();
    // Sum (not overwrite): the endpoint groups by region too, so one (instrument, material) cell can
    // arrive as several region rows — aggregate them into a single cell.
    for (const c of cells) {
      const key = `${c.instrument_type}|${c.material_category}`;
      lookup.set(key, (lookup.get(key) ?? 0) + c.count);
      matTotals.set(c.material_category, (matTotals.get(c.material_category) ?? 0) + c.count);
      presentInstruments.add(c.instrument_type);
    }
    const max = lookup.size ? Math.max(...lookup.values()) : 0;
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
      <EnactedOnlyToggle
        enactedOnly={enactedOnly}
        onChange={(v) => {
          setEnactedOnly(v);
          track('insights_coverage_enacted_only', { enacted_only: v });
        }}
      />

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
                  const clickable = count > 0;
                  return (
                    <td
                      key={inst}
                      className={`border border-border-default p-0 text-center tabular-nums ${
                        clickable ? 'cursor-pointer hover:ring-1 hover:ring-inset hover:ring-[rgb(var(--green-accent))]' : ''
                      }`}
                      style={sequentialFill(count, max)}
                      title={`${formatInstrumentType(inst)} × ${formatMaterial(mat)}: ${count} ${
                        count === 1 ? 'bill' : 'bills'
                      }${clickable ? ' — click to see them' : ''}`}
                    >
                      {clickable ? (
                        <button
                          type="button"
                          onClick={() => {
                            setDrill({ instrument: inst, material: mat });
                            track('insights_coverage_drilldown', { instrument: inst, material: mat, regions: regionForDrill });
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
        Each cell counts EPR-relevant bills applying that instrument to that material; a bill spanning
        several materials counts in each. Shading is relative, not linear — read the number, not just the
        tint. The blank cells are the live signal — a material with deposit-return precedent but an empty
        EPR column is where the next bills tend to land. Auto-classified at a 0.7 confidence floor.
        <span className="text-text-secondary"> Click any cell to see the bills counted in it.</span>
      </p>

      <BillDrilldownPanel
        open={drill != null}
        onClose={() => setDrill(null)}
        title={drill ? `${formatInstrumentType(drill.instrument)} × ${formatMaterial(drill.material)}` : ''}
        subtitle="Bills counted in this cell"
        params={
          drill
            ? {
                ce_relevant: true,
                instrument_type: drill.instrument,
                material_category: drill.material,
                region: regionForDrill,
                ...(enactedOnly ? { status: 'enacted' } : {}),
              }
            : null
        }
        source="coverage_matrix"
      />
    </div>
  );
}
