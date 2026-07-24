'use client';

import { useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { BillTimelinePoint, BillParams } from '@/lib/types';
import { track } from '@/lib/analytics';
import { formatInstrumentType } from '@/lib/utils';
import { chartAxis, chartGrid, chartTooltip, countAxis, useChartTheme } from '@/lib/charts/theme';
import { BillDrilldownPanel } from './BillDrilldownPanel';

/**
 * "Shots on goal" timeline. Enacted is the headline series (cumulative laws on the books);
 * the upstream statuses are off by default and can be toggled on to show how many bills it
 * takes moving through the pipeline to land each enacted law.
 *
 * Buckets come from /bills/timeline, keyed by year of status_date (date of the most recent
 * status transition). So a bill counts under its CURRENT status in the year it last moved —
 * enacted cumulates cleanly into "laws to date", while the upstream series read as activity.
 */

interface StatusConfig {
  key: string;
  label: string;
  color: string;
  /** "score" = the goal (enacted); "shot" = upstream pipeline activity. */
  kind: 'score' | 'shot';
}

// Order matters: legend/toggle order and stacking read top→bottom of the funnel.
const STATUS_CONFIG: StatusConfig[] = [
  { key: 'enacted', label: 'Enacted (law)', color: '#16a34a', kind: 'score' },
  { key: 'introduced', label: 'Introduced', color: '#3b82f6', kind: 'shot' },
  { key: 'in_committee', label: 'In committee', color: '#f59e0b', kind: 'shot' },
  { key: 'passed_chamber', label: 'Passed a chamber', color: '#8b5cf6', kind: 'shot' },
  { key: 'passed', label: 'Passed both chambers', color: '#14b8a6', kind: 'shot' },
  { key: 'vetoed', label: 'Vetoed', color: '#ef4444', kind: 'shot' },
  { key: 'failed', label: 'Failed / died', color: '#9ca3af', kind: 'shot' },
];

type Mode = 'cumulative' | 'annual';

export function BillTimelineChart({
  points,
  instrument,
}: {
  points: BillTimelinePoint[];
  instrument?: string;
}) {
  const [mode, setMode] = useState<Mode>('cumulative');
  // Enacted is the headline; upstream series start hidden so the page opens clean.
  const [visible, setVisible] = useState<Set<string>>(() => new Set(['enacted']));
  const [drillYear, setDrillYear] = useState<number | null>(null);

  const colors = useChartTheme();

  // Clicking the chart drills the whole year (the timeline is multi-series, so a single point isn't
  // one status); the panel lists every bill active that year with its own status + source link.
  function openDrill(e: { activeLabel?: string | number } | null) {
    const year = e?.activeLabel != null ? Number(e.activeLabel) : NaN;
    if (!Number.isFinite(year)) return;
    setDrillYear(year);
    track('insights_timeline_drilldown', { year, instrument: instrument ?? 'all' });
  }

  const drillParams: BillParams | null =
    drillYear == null ? null : { ce_relevant: true, instrument_type: instrument, year: drillYear };

  // Build one row per year (gap-filled), with each status as a column, optionally cumulated.
  const { rows, statusesPresent } = useMemo(() => {
    if (points.length === 0) return { rows: [], statusesPresent: new Set<string>() };
    const present = new Set(points.map((p) => p.status));
    const byYear = new Map<number, Record<string, number>>();
    let minY = Infinity;
    let maxY = -Infinity;
    for (const p of points) {
      minY = Math.min(minY, p.year);
      maxY = Math.max(maxY, p.year);
      const row = byYear.get(p.year) ?? {};
      row[p.status] = (row[p.status] ?? 0) + p.count;
      byYear.set(p.year, row);
    }
    const running: Record<string, number> = {};
    const out: Array<Record<string, number>> = [];
    for (let y = minY; y <= maxY; y++) {
      const annual = byYear.get(y) ?? {};
      const row: Record<string, number> = { year: y };
      for (const cfg of STATUS_CONFIG) {
        const v = annual[cfg.key] ?? 0;
        running[cfg.key] = (running[cfg.key] ?? 0) + v;
        row[cfg.key] = mode === 'cumulative' ? running[cfg.key] : v;
      }
      out.push(row);
    }
    return { rows: out, statusesPresent: present };
  }, [points, mode]);

  // First year any upstream (non-enacted) status has data. Before this, the only series with data is
  // enacted (reconstructed historically), so upstream lines start mid-axis — without a marker the
  // funnel looks like "more laws than introductions" in early years. Data-driven, so it self-updates.
  const trackingStartYear = useMemo(() => {
    let y = Infinity;
    for (const p of points) if (p.status !== 'enacted') y = Math.min(y, p.year);
    return Number.isFinite(y) ? y : null;
  }, [points]);

  const series = STATUS_CONFIG.filter((c) => statusesPresent.has(c.key));

  // Show the marker only when an upstream series is visible and there are earlier (enacted-only) years.
  const showTrackingStart =
    trackingStartYear != null &&
    rows.length > 0 &&
    (rows[0].year as number) < trackingStartYear &&
    [...visible].some((k) => k !== 'enacted');

  function toggle(key: string) {
    setVisible((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else {
        next.add(key);
        track('insights_timeline_status_toggle', { status: key, mode });
      }
      return next;
    });
  }

  if (rows.length === 0) {
    return <p className="text-text-muted text-sm">No timeline data available yet.</p>;
  }

  return (
    <div className="space-y-4">
      {/* Cumulative vs annual */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="inline-flex rounded-md border border-border-default overflow-hidden text-sm">
          {(['cumulative', 'annual'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                track('insights_timeline_mode', { mode: m });
              }}
              className={`px-3 py-1.5 transition-colors ${
                mode === m
                  ? 'bg-[rgb(var(--green-accent))] text-white'
                  : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
              }`}
            >
              {m === 'cumulative' ? 'Cumulative' : 'Per year'}
            </button>
          ))}
        </div>
        <p className="text-text-muted text-xs">
          {mode === 'cumulative' ? 'Running totals through each year' : 'New bills reaching each status that year'}
        </p>
      </div>

      <div className="h-[360px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={rows}
            margin={{ top: 8, right: 12, bottom: 4, left: -8 }}
            onClick={openDrill}
            className="cursor-pointer"
          >
            <CartesianGrid {...chartGrid(colors)} />
            <XAxis dataKey="year" {...chartAxis(colors)} />
            <YAxis {...chartAxis(colors)} {...countAxis} />
            <Tooltip {...chartTooltip} />
            {showTrackingStart && (
              <ReferenceLine
                x={trackingStartYear!}
                stroke={colors.muted}
                strokeDasharray="4 3"
                label={{
                  value: 'continuous tracking begins',
                  position: 'insideTopLeft',
                  fontSize: 10,
                  fill: colors.muted,
                }}
              />
            )}
            {series
              .filter((c) => visible.has(c.key))
              .map((c) => (
                <Line
                  key={c.key}
                  type="monotone"
                  dataKey={c.key}
                  name={c.label}
                  stroke={c.key === 'enacted' ? colors.status.enacted : c.color}
                  strokeWidth={c.kind === 'score' ? 2.5 : 1.75}
                  dot={false}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Status toggles */}
      <div className="flex flex-wrap gap-2">
        {series.map((c) => {
          const on = visible.has(c.key);
          const chipColor = c.key === 'enacted' ? colors.status.enacted : c.color;
          return (
            <button
              key={c.key}
              onClick={() => toggle(c.key)}
              aria-pressed={on}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors ${
                on
                  ? 'border-border-default bg-bg-secondary text-text-primary'
                  : 'border-border-default bg-bg-primary text-text-muted opacity-60 hover:opacity-100'
              }`}
            >
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: on ? chipColor : 'transparent', border: `1.5px solid ${chipColor}` }}
              />
              {c.label}
            </button>
          );
        })}
      </div>

      <p className="text-text-muted text-xs leading-relaxed">
        Bills are bucketed by the year of their most recent status change, so each bill counts once,
        under its current status. The <span className="text-text-secondary">Enacted</span> line is a true
        running tally of circular-economy laws on the books. Upstream-status data (introduced, in committee, …)
        only begins around 2019, when continuous bill tracking started — earlier years reflect enacted laws
        reconstructed from the historical record.{' '}
        <span className="text-text-secondary">Click any year to see the bills behind it, each linked to its source.</span>
      </p>

      <BillDrilldownPanel
        open={drillYear != null}
        onClose={() => setDrillYear(null)}
        title={drillYear != null ? `Bills active in ${drillYear}` : ''}
        subtitle={instrument ? formatInstrumentType(instrument) : 'All instruments'}
        params={drillParams}
        source="timeline"
      />
    </div>
  );
}
