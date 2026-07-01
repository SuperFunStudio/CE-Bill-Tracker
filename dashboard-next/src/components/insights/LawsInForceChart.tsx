'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchLawsInForce } from '@/lib/api';
import { regionLabel } from './RegionFilter';
import type { LawsInForcePoint } from '@/lib/types';

/**
 * "Laws on the books over time" — cumulative count of enacted CE laws by the year each came into
 * force. Unlike the pipeline timeline (introduced→enacted, US-only), this keys on the extracted
 * effective_date, so foreign regulations — which have no legislative pipeline — get a real momentum
 * line. Honors the global region filter: a handful of selected regions render one line each (compare);
 * "All" (too many to read) collapses to a single total line.
 */

const PALETTE = ['#16a34a', '#3b82f6', '#f59e0b', '#8b5cf6', '#14b8a6', '#ef4444', '#ec4899'];
const MAX_SERIES = 7;

function useThemeColors() {
  const [colors, setColors] = useState({ muted: '#6b7280', border: '#dee2e6' });
  useEffect(() => {
    const root = getComputedStyle(document.documentElement);
    const get = (v: string, fb: string) => root.getPropertyValue(v).trim() || fb;
    setColors({ muted: get('--text-muted', '#6b7280'), border: get('--border-default', '#dee2e6') });
  }, []);
  return colors;
}

export function LawsInForceChart({ regions }: { regions?: string } = {}) {
  const [points, setPoints] = useState<LawsInForcePoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const colors = useThemeColors();

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setPoints(null);
    fetchLawsInForce({ regions })
      .then((d) => {
        if (!cancelled) setPoints(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load laws-in-force.');
      });
    return () => {
      cancelled = true;
    };
  }, [regions]);

  const { rows, series, aggregated } = useMemo(() => {
    if (!points || points.length === 0) return { rows: [], series: [], aggregated: false };
    const present = [...new Set(points.map((p) => p.region))];
    const aggregate = present.length > MAX_SERIES;

    // annual[region][year] = count of laws that came into force that year
    const annual: Record<string, Record<number, number>> = {};
    let minY = Infinity;
    let maxY = -Infinity;
    for (const p of points) {
      (annual[p.region] ??= {})[p.year] = (annual[p.region][p.year] ?? 0) + p.count;
      minY = Math.min(minY, p.year);
      maxY = Math.max(maxY, p.year);
    }

    if (aggregate) {
      let run = 0;
      const rows: Array<Record<string, number>> = [];
      for (let y = minY; y <= maxY; y++) {
        for (const r of present) run += annual[r]?.[y] ?? 0;
        rows.push({ year: y, total: run });
      }
      return { rows, series: [{ key: 'total', label: 'All jurisdictions', color: PALETTE[0] }], aggregated: true };
    }

    // One cumulative line per region, ordered by total (biggest first → stable colors + legend).
    const ordered = present
      .map((r) => [r, Object.values(annual[r]).reduce((a, b) => a + b, 0)] as const)
      .sort((a, b) => b[1] - a[1])
      .map(([r]) => r);
    const run: Record<string, number> = {};
    const rows: Array<Record<string, number>> = [];
    for (let y = minY; y <= maxY; y++) {
      const row: Record<string, number> = { year: y };
      for (const r of ordered) {
        run[r] = (run[r] ?? 0) + (annual[r]?.[y] ?? 0);
        row[r] = run[r];
      }
      rows.push(row);
    }
    const series = ordered.map((r, i) => ({ key: r, label: regionLabel(r), color: PALETTE[i % PALETTE.length] }));
    return { rows, series, aggregated: false };
  }, [points]);

  if (error) return <p className="text-sm text-error">{error}</p>;
  if (!points) return <div className="h-[340px] w-full animate-pulse rounded-lg bg-bg-tertiary" />;
  if (rows.length === 0) return <p className="text-text-muted text-sm">No enacted laws to chart yet.</p>;

  return (
    <div className="space-y-3">
      <div className="h-[340px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border} vertical={false} />
            <XAxis dataKey="year" stroke={colors.muted} tick={{ fontSize: 11, fill: colors.muted }} tickLine={false} />
            <YAxis
              stroke={colors.muted}
              tick={{ fontSize: 11, fill: colors.muted }}
              tickLine={false}
              allowDecimals={false}
              width={44}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-default)',
                borderRadius: 8,
                fontSize: 12,
                color: 'var(--text-primary)',
              }}
              labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
            />
            {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
            {series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-text-muted text-xs leading-relaxed">
        Cumulative circular-economy laws on the books, by the year each came into force (extracted
        effective date; US enacted laws fall back to their most recent action date).
        {aggregated && ' Pick specific regions in the filter above to compare their trajectories.'}
      </p>
    </div>
  );
}
