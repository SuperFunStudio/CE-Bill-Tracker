'use client';

import type { MaterialMapPoint, RegimeAxes } from '@/lib/types';

// The value×dispersion quadrant. x = material value (low→high), y = dispersion (low→high). Critical-mass
// materials cluster top-left (low value, spread thin); incremental-viable bottom-right (high value,
// concentrated). Point size = channel maturity. The dashed diagonal is the "collection valley" — above
// it, dispersion outruns value and the economics don't close without engineered critical mass.
//
// Presentational + reused: the Evaluate page passes a `highlight` (the current bill's material, plotted
// from estimated axes when it isn't a known material); Insights renders it plain with hover labels.

export const REGIME_COLOR: Record<string, string> = {
  critical_mass: '#f59e0b',                 // amber — engineer critical mass
  incremental_viable: 'rgb(var(--green-accent))',
};

type PlottedPoint = MaterialMapPoint & { you?: boolean };

export function MaterialPositionMap({
  points, highlight, highlightAxes, confidence, height = 250,
}: {
  points: MaterialMapPoint[];
  highlight?: string;
  highlightAxes?: RegimeAxes;
  confidence?: string;
  height?: number;
}) {
  const W = 340, H = height, pad = 34;
  const px = (v: number) => pad + v * (W - 2 * pad);
  const py = (v: number) => (H - pad) - v * (H - 2 * pad);

  const known = !!highlight && points.some(p => p.material === highlight);
  let all: PlottedPoint[] = points.map(p => ({ ...p, you: !!highlight && p.material === highlight }));
  if (highlight && !known && highlightAxes) {
    all = [...all, {
      material: highlight, value_density: highlightAxes.value_density, dispersion: highlightAxes.dispersion,
      channel_maturity: highlightAxes.channel_maturity,
      regime: (highlightAxes.dispersion > highlightAxes.value_density ? 'critical_mass' : 'incremental_viable'),
      you: true,
    }];
  }
  const youPt = all.find(p => p.you);

  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-4 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-text-secondary text-xs font-semibold uppercase tracking-wide">Material-position map</span>
        {highlight && !known && (
          <span className="text-xs text-amber-400">plotted from estimate{confidence === 'low' ? ' · uncertain' : ''}</span>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Materials on the value-by-dispersion map">
        {/* regime regions + the collection-valley diagonal */}
        <polygon points={`${px(0)},${py(0)} ${px(0)},${py(1)} ${px(1)},${py(1)}`} fill="#f59e0b" opacity={0.06} />
        <polygon points={`${px(0)},${py(0)} ${px(1)},${py(0)} ${px(1)},${py(1)}`} fill="rgb(var(--green-accent))" opacity={0.06} />
        <line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(1)} stroke="rgb(var(--border-default))" strokeDasharray="4 4" />
        {/* axes */}
        <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="rgb(var(--border-default))" />
        <line x1={pad} y1={pad} x2={pad} y2={H - pad} stroke="rgb(var(--border-default))" />
        <text x={W - pad} y={H - pad + 16} textAnchor="end" className="fill-text-muted" fontSize={9}>Recoverable value / tonne →</text>
        <text x={pad - 6} y={pad - 6} textAnchor="start" className="fill-text-muted" fontSize={9}>Dispersion →</text>
        <text x={px(0.02)} y={py(0.94)} className="fill-text-muted" fontSize={9} opacity={0.8}>critical-mass</text>
        <text x={px(0.98)} y={py(0.06)} textAnchor="end" className="fill-text-muted" fontSize={9} opacity={0.8}>incremental</text>
        {/* points — native <title> gives a hover label without any state */}
        {all.map(p => (
          <circle
            key={p.material}
            cx={px(p.value_density)} cy={py(p.dispersion)} r={p.you ? 6 : 3 + p.channel_maturity * 3}
            fill={REGIME_COLOR[p.regime] ?? '#888'} opacity={p.you ? 1 : 0.55}
            stroke={p.you ? 'rgb(var(--text-primary))' : 'none'} strokeWidth={p.you ? 2 : 0}
          >
            <title>{p.material}{p.value_usd_per_tonne != null ? ` · ~$${p.value_usd_per_tonne.toLocaleString()}/t recoverable` : ''}</title>
          </circle>
        ))}
        {youPt && (
          <text x={px(youPt.value_density)} y={py(youPt.dispersion) - 10} textAnchor="middle" className="fill-text-primary" fontSize={10} fontWeight={600}>
            {youPt.material}
          </text>
        )}
      </svg>
      <p className="text-xs text-text-muted leading-relaxed">
        Point size = channel maturity. High-value, concentrated materials (bottom-right) cross the collection
        valley on their own economics; low-value, dispersed ones (top-left) don&apos;t without engineered critical mass.
      </p>
    </div>
  );
}
