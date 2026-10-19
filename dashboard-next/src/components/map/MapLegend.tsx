'use client';
import { ENACTED_BINS, MAP_METRIC, binLabel, hatchBackground, type MapPalette } from '@/lib/mapScale';

/**
 * The one legend for every map (globe, US states, regional insets) — same swatches, same bins, same
 * metric name, so the scale reads identically at every zoom level. `showUntracked` adds the hatched
 * "not tracked" chip; the US state map omits it because every state is tracked.
 */
export function MapLegend({
  palette, showUntracked = true, className = '',
}: { palette: MapPalette; showUntracked?: boolean; className?: string }) {
  const chip = 'inline-block h-2.5 w-4 rounded-[2px] border border-black/5 dark:border-white/10';
  return (
    <div className={`flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-text-muted ${className}`}>
      <span className="field-label">{MAP_METRIC}</span>
      <span className="inline-flex items-center gap-1">
        <span className={chip} style={{ background: palette.land }} />0
      </span>
      {ENACTED_BINS.map((_, i) => (
        <span key={i} className="inline-flex items-center gap-1 tabular-nums">
          <span className={chip} style={{ background: palette.bins[i] }} />
          {binLabel(i)}
        </span>
      ))}
      {showUntracked && (
        <span className="inline-flex items-center gap-1">
          <span className={chip} style={{ background: hatchBackground(palette) }} />
          Not tracked
        </span>
      )}
    </div>
  );
}
