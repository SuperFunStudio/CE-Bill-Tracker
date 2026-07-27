'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchFeeSummary } from '@/lib/api';
import { ChartError, ChartSkeleton, useChartTheme } from '@/lib/charts/theme';
import type { FeeAmountsSummary } from '@/lib/types';

/**
 * "Bill-sourced fees across jurisdictions" — a horizontal bar of how many cited fee facts we've
 * extracted from each jurisdiction's laws (compliance_details.fee_amounts). Single-series magnitude:
 * one hue, no legend, the title names it. Fed by the OPEN /compliance/fee-amounts/summary aggregate,
 * which spans every region and ignores the region filter (it's the cross-jurisdiction breadth view).
 * The row endpoints behind it are US-teaser / world-gated — this chart is the shop window for that.
 */

// Human labels for the jurisdiction codes that carry fee data; anything unmapped shows its code.
const REGION_LABELS: Record<string, string> = {
  US: 'United States', EU: 'EU (central)', UK: 'United Kingdom', FR: 'France', DE: 'Germany',
  PL: 'Poland', SE: 'Sweden', NL: 'Netherlands', JP: 'Japan', ES: 'Spain', IE: 'Ireland',
  DK: 'Denmark', FI: 'Finland', CA: 'Canada', CH: 'Switzerland', CL: 'Chile', LU: 'Luxembourg',
  EE: 'Estonia', SK: 'Slovakia', NO: 'Norway', IT: 'Italy', TR: 'Türkiye', IN: 'India',
  AU: 'Australia', CN: 'China', BR: 'Brazil', KE: 'Kenya', ZA: 'South Africa',
};

const FEE_KIND_LABELS: Record<string, string> = {
  producer_fee: 'producer fees', registration: 'registration', incentive: 'incentives',
  penalty: 'penalties', threshold: 'thresholds', admin_cost: 'admin costs', unspecified: 'unspecified',
};

const TOP_N = 15;

export function FeeCoverageChart() {
  const [summary, setSummary] = useState<FeeAmountsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const colors = useChartTheme();

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setSummary(null);
    fetchFeeSummary()
      .then((d) => { if (!cancelled) setSummary(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load fee coverage.'); });
    return () => { cancelled = true; };
  }, []);

  const rows = useMemo(() => {
    if (!summary) return [];
    return summary.by_region
      .map((r) => ({ code: r.key, label: REGION_LABELS[r.key] ?? r.key, count: r.count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, TOP_N);
  }, [summary]);

  if (error) return <ChartError>{error}</ChartError>;
  if (!summary) return <ChartSkeleton heightClass="h-[420px]" />;

  const jurisdictions = summary.by_region.length;
  const kindComposition = summary.by_fee_kind
    .filter((k) => k.count > 0)
    .map((k) => `${k.count} ${FEE_KIND_LABELS[k.key] ?? k.key}`)
    .join(' · ');

  return (
    <div className="space-y-4">
      {/* Headline stats — the breadth pitch. */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat value={jurisdictions.toLocaleString()} label="Jurisdictions with fee data" />
        <Stat value={summary.bills_with_fees.toLocaleString()} label="Laws with a stated fee" />
        <Stat value={summary.numeric_rate_entries.toLocaleString()} label="Cited fee amounts" />
        <Stat value={summary.bills_with_numeric.toLocaleString()} label="Laws with a numeric fee" />
      </div>

      <ResponsiveContainer width="100%" height={Math.max(200, rows.length * 26)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 28, bottom: 4, left: 8 }}>
          <CartesianGrid horizontal={false} stroke={colors.border} strokeOpacity={0.4} />
          <XAxis type="number" tick={{ fill: colors.muted, fontSize: 12 }} allowDecimals={false} />
          <YAxis type="category" dataKey="label" width={130} tick={{ fill: colors.muted, fontSize: 12 }} />
          <Tooltip
            cursor={{ fill: colors.border, fillOpacity: 0.15 }}
            formatter={(value) => [`${Number(value)} fee entr${Number(value) === 1 ? 'y' : 'ies'}`, 'Extracted']}
            contentStyle={{ background: 'rgb(var(--bg-secondary))', border: `1px solid ${colors.border}`, borderRadius: 8, fontSize: 12 }}
          />
          <Bar dataKey="count" fill={colors.accent} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>

      <p className="text-xs text-text-muted leading-relaxed">
        {summary.total_rate_entries.toLocaleString()} fee entries across {jurisdictions} jurisdictions,
        each cited to the enacting text. Composition: {kindComposition}. Top {Math.min(TOP_N, summary.by_region.length)} jurisdictions
        shown. Every amount is what the <em>law itself states</em> — most per-tonne producer rates are set later by the
        PRO/agency, so a law more often states a registration fee, a revenue threshold, or that fees are eco-modulated.
      </p>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-3">
      <div className="font-bold text-text-primary text-xl">{value}</div>
      <div className="text-text-muted text-xs mt-0.5">{label}</div>
    </div>
  );
}
