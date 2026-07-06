'use client';

import { useEffect, useState } from 'react';
import { fetchMaterialMap } from '@/lib/api';
import type { MaterialMapPoint } from '@/lib/types';
import { MaterialPositionMap, REGIME_COLOR } from './MaterialPositionMap';

// Insights view of the material-position framework: the scatter (all tracked materials) next to the two
// regime rosters. Answers "which materials can go circular incrementally, and which need engineered
// critical mass" — the lens the Evaluate page applies to a single bill, shown across the whole material set.

function Roster({ title, colorKey, materials }: { title: string; colorKey: string; materials: string[] }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full" style={{ background: REGIME_COLOR[colorKey] }} />
        <span className="text-xs font-semibold text-text-primary">{title}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {materials.map(m => (
          <span key={m} className="rounded-full border border-border-default bg-bg-primary px-2 py-0.5 text-xs text-text-secondary">
            {m}
          </span>
        ))}
      </div>
    </div>
  );
}

export function MaterialRegimeMap() {
  const [points, setPoints] = useState<MaterialMapPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMaterialMap().then(setPoints).catch(() => setError('Could not load the material map.'));
  }, []);

  if (error) return <p className="text-sm text-error">{error}</p>;
  if (!points) return <div className="h-[300px] w-full animate-pulse rounded-lg bg-bg-tertiary" />;

  // Order each roster the way the map reads: critical-mass hardest-first (most dispersed), incremental
  // strongest-first (highest value).
  const critical = points.filter(p => p.regime === 'critical_mass')
    .sort((a, b) => b.dispersion - a.dispersion).map(p => p.material);
  const incremental = points.filter(p => p.regime === 'incremental_viable')
    .sort((a, b) => b.value_density - a.value_density).map(p => p.material);

  return (
    <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_220px] sm:items-start">
      <MaterialPositionMap points={points} height={300} />
      <div className="space-y-4">
        <Roster title="Critical-mass-required" colorKey="critical_mass" materials={critical} />
        <Roster title="Incremental-viable" colorKey="incremental_viable" materials={incremental} />
        <p className="text-xs text-text-muted leading-relaxed">
          Hover any point for its material and recoverable value. All three axes are now data- or
          model-grounded: value in mid-2026 scrap prices (log scale), channel maturity in how many
          jurisdictions have enacted a collection law, and dispersion in a Sonnet estimate of end-of-life
          holder spread. Meant to frame which intervention a material needs, not to price it.
        </p>
      </div>
    </div>
  );
}
