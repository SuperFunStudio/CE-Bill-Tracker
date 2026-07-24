'use client';

/**
 * Shared chart primitive — the single source of truth for how every chart in the app
 * is colored and chromed. Before this, each chart carried its own copy of a
 * `useThemeColors` hook, its own Recharts axis/grid/tooltip props, and (in one case)
 * an un-validated categorical palette. Consolidating them here means a chart is themed
 * by role, the light/dark values swap in one place (theme.css / globals.css), and the
 * colorblind-safe palette is defined once.
 *
 * Roles (see the dataviz method — color follows the job the data does):
 *  - categorical  → identity (a region, a series). Fixed order, never cycled; validated
 *                   for CVD + normal-vision separation. A 9th series folds to "Other".
 *  - status       → a reserved semantic state (enacted / weakens / …). Never reused as
 *                   "series N"; ships with a label, not color alone.
 *  - sequential   → magnitude (heatmap cell intensity). One hue, light→dark, via alpha.
 *  - neutrals     → axis / gridline ink, recessive.
 */

import { useEffect, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';

export interface ChartTheme {
  /** Recessive ink for axes, ticks, reference lines. */
  muted: string;
  /** Hairline gridline / border stroke. */
  border: string;
  /**
   * Fixed-order categorical palette (8 slots). Order is the CVD-safety mechanism —
   * assign in order, never cycle. Slots beyond 8 must fold to "Other" or a facet.
   */
  categorical: string[];
  /**
   * The brand accent as a ready-to-use CSS color string, e.g. `rgb(30 106 233)`.
   * --green-accent is stored as a bare rgb TRIPLET (so `/ alpha` opacity works in CSS);
   * this wraps it in `rgb(...)` so it's valid anywhere a solid color is needed — including
   * a Recharts `fill`, where a bare triplet would be an invalid color.
   */
  accent: string;
  /** Reserved semantic status hues — mirror the --status-* tokens in theme.css. */
  status: {
    enacted: string;
    weakens: string;
    introduced: string;
    committee: string;
    advancing: string;
    dormant: string;
  };
}

// Slot vars, in canonical order. Kept in sync with theme.css --chart-cat-*.
const CAT_VARS = [
  '--chart-cat-1', '--chart-cat-2', '--chart-cat-3', '--chart-cat-4',
  '--chart-cat-5', '--chart-cat-6', '--chart-cat-7', '--chart-cat-8',
] as const;

// Light-mode fallbacks for first paint (SSR / before the effect resolves the live
// CSS vars). Must match the :root values in theme.css / globals.css.
const FALLBACK: ChartTheme = {
  muted: '#6b7280',
  border: '#dee2e6',
  categorical: ['#2a78d6', '#008300', '#e87ba4', '#eda100', '#1baf7a', '#eb6834', '#4a3aa7', '#e34948'],
  accent: 'rgb(30 106 233)',
  status: {
    enacted: '#16a34a',
    weakens: '#dc2626',
    introduced: '#0ea5e9',
    committee: '#f59e0b',
    advancing: '#6366f1',
    dormant: '#9ca3af',
  },
};

/**
 * Resolves the active theme's chart colors from CSS custom properties, so a chart
 * tracks light/dark (and any future re-theme) without hardcoding hex. Reads once on
 * mount; the values are static per theme, and Recharts re-renders on the returned
 * object identity change. Replaces the per-file `useThemeColors` copies.
 */
export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState<ChartTheme>(FALLBACK);
  useEffect(() => {
    const root = getComputedStyle(document.documentElement);
    const get = (v: string, fb: string) => root.getPropertyValue(v).trim() || fb;
    setTheme({
      muted: get('--text-muted', FALLBACK.muted),
      border: get('--border-default', FALLBACK.border),
      categorical: CAT_VARS.map((v, i) => get(v, FALLBACK.categorical[i])),
      accent: `rgb(${get('--green-accent', '30 106 233')})`,
      status: {
        enacted: get('--status-enacted', FALLBACK.status.enacted),
        weakens: get('--status-weakens', FALLBACK.status.weakens),
        introduced: get('--status-introduced', FALLBACK.status.introduced),
        committee: get('--status-committee', FALLBACK.status.committee),
        advancing: get('--status-advancing', FALLBACK.status.advancing),
        dormant: get('--status-dormant', FALLBACK.status.dormant),
      },
    });
  }, []);
  return theme;
}

// ── Recharts shared props ──────────────────────────────────────────────────
// Factories (they close over the resolved theme) + one static tooltip style, so the
// four Recharts charts stop repeating the same ~8 lines of axis/grid/tooltip config.

/** XAxis/YAxis shared styling — recessive muted ink, no tick line. Spread onto both. */
export const chartAxis = (t: ChartTheme) => ({
  stroke: t.muted,
  tick: { fontSize: 11, fill: t.muted },
  tickLine: false,
});

/** A count YAxis: whole numbers, fixed gutter. Spread AFTER chartAxis(t). */
export const countAxis = { allowDecimals: false, width: 44 } as const;

/** CartesianGrid shared styling — horizontal hairlines only. */
export const chartGrid = (t: ChartTheme) => ({
  strokeDasharray: '3 3',
  stroke: t.border,
  vertical: false,
});

/** Tooltip styling keyed to theme tokens (works in both modes without JS). */
export const chartTooltip = {
  contentStyle: {
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border-default)',
    borderRadius: 8,
    fontSize: 12,
    color: 'var(--text-primary)',
  },
  labelStyle: { color: 'var(--text-primary)', fontWeight: 600 },
} as const;

// ── Sequential (heatmap) fill ───────────────────────────────────────────────

/**
 * Sequential cell fill for coverage heatmaps: the brand accent at an alpha scaled by
 * magnitude. sqrt compresses the long tail (1..200+) so mid-range cells stay legible
 * instead of washing out next to the largest. count 0 → no fill (empty cell is signal).
 * One hue (via --green-accent), light→dark by opacity — the sequential-encoding rule.
 */
export function sequentialFill(count: number, max: number): CSSProperties {
  if (count <= 0 || max <= 0) return {};
  const alpha = 0.1 + 0.85 * Math.sqrt(count / max);
  return { background: `rgb(var(--green-accent) / ${alpha.toFixed(3)})` };
}

// ── Load / empty / error states ─────────────────────────────────────────────
// Shared so every chart's pending/empty/error affordance reads identically.

/** Pulsing placeholder while a chart's data loads. Pass a Tailwind height class. */
export function ChartSkeleton({ heightClass = 'h-[340px]' }: { heightClass?: string }) {
  return <div className={`${heightClass} w-full animate-pulse rounded-lg bg-bg-tertiary`} />;
}

/** Muted "nothing to chart yet" note. */
export function ChartEmpty({ children }: { children: ReactNode }) {
  return <p className="text-text-muted text-sm">{children}</p>;
}

/** Error note in the error color. */
export function ChartError({ children }: { children: ReactNode }) {
  return <p className="text-sm text-error">{children}</p>;
}
