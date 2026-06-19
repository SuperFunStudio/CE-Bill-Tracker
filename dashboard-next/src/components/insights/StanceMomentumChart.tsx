'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchStanceMomentum } from '@/lib/api';
import { formatInstrumentType } from '@/lib/utils';
import { track } from '@/lib/analytics';
import { BillDrilldownPanel } from './BillDrilldownPanel';
import type { BillStancePoint, BillParams } from '@/lib/types';

/**
 * "Policy momentum" — a diverging bar chart that answers "is the field advancing or being rolled
 * back?". Bills classified as `advances` (establish/strengthen) stack upward in green; `weakens`
 * (exempt/narrow/repeal/preempt) stack downward in red, around a zero line. `neutral`
 * (administrative/study/ambiguous) carries no direction, so it's left off the axis by design.
 *
 * Per-bill stance markers were pulled from the public site (a mislabeled "weakens" is worse than no
 * marker — see lib/utils statusBadge). This is an aggregate on an internal/URL-only page with a
 * confidence floor applied server-side, where a single misclassification can't flip the read.
 */

// Mirror the page's INSTRUMENT_OPTIONS so this section can be sliced independently of the timeline.
const INSTRUMENT_OPTIONS: Array<{ value: string | undefined; label: string }> = [
  { value: undefined, label: 'All instruments' },
  ...['epr', 'deposit_return', 'right_to_repair', 'recycled_content', 'incentives', 'labeling', 'preemption', 'other'].map(
    (v) => ({ value: v, label: formatInstrumentType(v) }),
  ),
];

// Reads the active theme's neutrals AND the canonical status palette (--status-*, see theme.css),
// so "advances" green matches the enacted green used everywhere else instead of a one-off hex.
function useThemeColors() {
  const [colors, setColors] = useState({
    muted: '#6b7280', border: '#dee2e6', advances: '#16a34a', weakens: '#dc2626',
  });
  useEffect(() => {
    const root = getComputedStyle(document.documentElement);
    const get = (v: string, fb: string) => root.getPropertyValue(v).trim() || fb;
    setColors({
      muted: get('--text-muted', '#6b7280'),
      border: get('--border-default', '#dee2e6'),
      advances: get('--status-enacted', '#16a34a'),
      weakens: get('--status-weakens', '#dc2626'),
    });
  }, []);
  return colors;
}

interface Row {
  year: number;
  advances: number;
  weakens: number; // stored negative so it stacks below the zero line
  neutral: number;
}

export function StanceMomentumChart() {
  const [points, setPoints] = useState<BillStancePoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [instrument, setInstrument] = useState<string | undefined>(undefined);
  const [drill, setDrill] = useState<{ params: BillParams; title: string; subtitle: string } | null>(null);
  const colors = useThemeColors();

  function openDrill(stance: 'advances' | 'weakens', d: { year?: number; payload?: { year?: number } }) {
    const year = d?.year ?? d?.payload?.year;
    if (!year) return;
    setDrill({
      params: { ce_relevant: true, policy_stance: stance, instrument_type: instrument, year, min_confidence: 0.7 },
      title: `${stance === 'advances' ? 'Advancing' : 'Weakening'} bills · ${year}`,
      subtitle: instrument ? formatInstrumentType(instrument) : 'All instruments',
    });
    track('insights_momentum_drilldown', { stance, year, instrument: instrument ?? 'all' });
  }

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setPoints(null);
    fetchStanceMomentum({ instrument_type: instrument })
      .then((d) => {
        if (!cancelled) setPoints(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load momentum.');
      });
    return () => {
      cancelled = true;
    };
  }, [instrument]);

  // One gap-filled row per year; weakens stored negative so the bar diverges below zero.
  const { rows, totals } = useMemo(() => {
    if (!points || points.length === 0) return { rows: [], totals: { advances: 0, weakens: 0, neutral: 0 } };
    const byYear = new Map<number, Row>();
    let minY = Infinity;
    let maxY = -Infinity;
    const totals = { advances: 0, weakens: 0, neutral: 0 };
    for (const p of points) {
      minY = Math.min(minY, p.year);
      maxY = Math.max(maxY, p.year);
      const row = byYear.get(p.year) ?? { year: p.year, advances: 0, weakens: 0, neutral: 0 };
      if (p.stance === 'advances') row.advances += p.count;
      else if (p.stance === 'weakens') row.weakens -= p.count;
      else row.neutral += p.count;
      byYear.set(p.year, row);
      totals[p.stance as keyof typeof totals] = (totals[p.stance as keyof typeof totals] ?? 0) + p.count;
    }
    const out: Row[] = [];
    for (let y = minY; y <= maxY; y++) {
      out.push(byYear.get(y) ?? { year: y, advances: 0, weakens: 0, neutral: 0 });
    }
    return { rows: out, totals };
  }, [points]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {INSTRUMENT_OPTIONS.map((opt) => {
          const active = opt.value === instrument;
          return (
            <button
              key={opt.label}
              onClick={() => {
                setInstrument(opt.value);
                track('insights_stance_instrument', { instrument: opt.value ?? 'all' });
              }}
              aria-pressed={active}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                active
                  ? 'border-[rgb(var(--green-accent))] bg-[rgb(var(--green-accent))] text-white'
                  : 'border-border-default bg-bg-primary text-text-secondary hover:bg-bg-tertiary'
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      {error ? (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : !points ? (
        <div className="h-[340px] w-full animate-pulse rounded-lg bg-bg-tertiary" />
      ) : rows.length === 0 ? (
        <p className="text-text-muted text-sm">No stance-classified bills for this slice yet.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-4 text-xs">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: colors.advances }} />
              Advances ({totals.advances.toLocaleString()})
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: colors.weakens }} />
              Weakens ({totals.weakens.toLocaleString()})
            </span>
            <span className="text-text-muted">
              {totals.neutral.toLocaleString()} neutral (administrative — not plotted)
            </span>
          </div>

          <div className="h-[340px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} stackOffset="sign" margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={colors.border} vertical={false} />
                <XAxis
                  dataKey="year"
                  stroke={colors.muted}
                  tick={{ fontSize: 11, fill: colors.muted }}
                  tickLine={false}
                />
                <YAxis
                  stroke={colors.muted}
                  tick={{ fontSize: 11, fill: colors.muted }}
                  tickLine={false}
                  allowDecimals={false}
                  width={44}
                  tickFormatter={(v: number) => `${Math.abs(v)}`}
                />
                <ReferenceLine y={0} stroke={colors.muted} />
                <Tooltip
                  contentStyle={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border-default)',
                    borderRadius: 8,
                    fontSize: 12,
                    color: 'var(--text-primary)',
                  }}
                  labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
                  formatter={(value, name) => [Math.abs(Number(value)), name]}
                />
                <Bar
                  dataKey="advances"
                  name="Advances"
                  stackId="stance"
                  fill={colors.advances}
                  isAnimationActive={false}
                  cursor="pointer"
                  onClick={(d) => openDrill('advances', d)}
                />
                <Bar
                  dataKey="weakens"
                  name="Weakens"
                  stackId="stance"
                  fill={colors.weakens}
                  isAnimationActive={false}
                  cursor="pointer"
                  onClick={(d) => openDrill('weakens', d)}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <p className="text-text-muted text-xs leading-relaxed">
            Bars are bucketed by the year of each bill&apos;s most recent status change and its classified
            policy stance. Above the line, bills that <span className="text-text-secondary">establish or strengthen</span>{' '}
            a circular-economy obligation; below it, bills that <span className="text-text-secondary">exempt, narrow,
            repeal, or preempt</span> one. Auto-classified at a 0.7 confidence floor; neutral
            (administrative or study) bills carry no direction and are left off the axis.{' '}
            <span className="text-text-secondary">Click any bar to see the bills behind it, each linked to its source.</span>
          </p>
        </>
      )}

      <BillDrilldownPanel
        open={!!drill}
        onClose={() => setDrill(null)}
        title={drill?.title ?? ''}
        subtitle={drill?.subtitle}
        params={drill?.params ?? null}
        source="momentum"
      />
    </div>
  );
}
