'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchCollectionTargetBasis } from '@/lib/api';
import type { CollectionTargetBasisPoint } from '@/lib/types';

/**
 * "How collection targets are measured" — a horizontal bar chart of the measurement basis across
 * EPR-relevant bills. Directly answers the recurring question: do bills set collection/recovery
 * targets by weight (tonnage), or by value recovered (critical metals), or per-unit? Basis is
 * unnested server-side from compliance_details.collection_targets.targets; this view sums across
 * regions (the `regions` filter narrows which regions contribute).
 */

const BASIS_LABELS: Record<string, string> = {
  weight: 'Weight (tonnage)',
  value_recovered: 'Value recovered (e.g. critical metals)',
  units: 'Units / count',
  material_specific: 'Material-specific',
  unspecified: 'Unspecified',
};
// Weight/value_recovered are the poles of the question, so they get the accent; the rest are neutral.
const BASIS_ACCENT = new Set(['weight', 'value_recovered']);

function useThemeColors() {
  const [colors, setColors] = useState({ accent: '#16a34a', muted: '#9ca3af', border: '#dee2e6' });
  useEffect(() => {
    const root = getComputedStyle(document.documentElement);
    const get = (v: string, fb: string) => root.getPropertyValue(v).trim() || fb;
    setColors({
      accent: get('--green-accent', '#16a34a'),
      muted: get('--text-muted', '#9ca3af'),
      border: get('--border-default', '#dee2e6'),
    });
  }, []);
  return colors;
}

export function CollectionTargetBasisChart({ regions }: { regions?: string } = {}) {
  const [points, setPoints] = useState<CollectionTargetBasisPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const colors = useThemeColors();

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setPoints(null);
    fetchCollectionTargetBasis({ regions })
      .then((d) => { if (!cancelled) setPoints(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load target basis.'); });
    return () => { cancelled = true; };
  }, [regions]);

  // Sum counts per basis across regions, ordered most→least common.
  const rows = useMemo(() => {
    if (!points) return [];
    const totals = new Map<string, number>();
    for (const p of points) totals.set(p.basis, (totals.get(p.basis) ?? 0) + p.count);
    return [...totals.entries()]
      .map(([basis, count]) => ({ basis, label: BASIS_LABELS[basis] ?? basis, count }))
      .sort((a, b) => b.count - a.count);
  }, [points]);

  if (error) return <p className="text-sm text-error">{error}</p>;
  if (!points) return <div className="h-[280px] w-full animate-pulse rounded-lg bg-bg-tertiary" />;
  if (rows.length === 0) {
    return (
      <p className="text-sm text-text-muted">
        No collection-target basis data for the selected regions yet.
      </p>
    );
  }

  const total = rows.reduce((s, r) => s + r.count, 0);

  return (
    <div className="space-y-3">
      <ResponsiveContainer width="100%" height={Math.max(180, rows.length * 52)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
          <CartesianGrid horizontal={false} stroke={colors.border} strokeOpacity={0.4} />
          <XAxis type="number" tick={{ fill: colors.muted, fontSize: 12 }} allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="label"
            width={190}
            tick={{ fill: colors.muted, fontSize: 12 }}
          />
          <Tooltip
            cursor={{ fill: colors.border, fillOpacity: 0.15 }}
            formatter={(value) => [`${Number(value)} target${Number(value) === 1 ? '' : 's'}`, 'Count']}
            contentStyle={{ background: 'rgb(var(--bg-secondary))', border: `1px solid ${colors.border}`, borderRadius: 8, fontSize: 12 }}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {rows.map((r) => (
              <Cell key={r.basis} fill={BASIS_ACCENT.has(r.basis) ? colors.accent : colors.muted} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="text-xs text-text-muted">
        {total} measured target{total === 1 ? '' : 's'} across in-scope bills. Weight and value-recovered
        are highlighted as the two poles of the question — most targets are set by weight, but a minority
        (recovered value, e.g. critical metals) and material-specific mandates exist alongside them.
      </p>
    </div>
  );
}
