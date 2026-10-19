'use client';
import { useMemo, useState } from 'react';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';
import { FIPS_TO_ABBR, STATE_NAMES } from '@/lib/utils';
import { useTheme } from '@/components/layout/ThemeContext';
import { MapLegend } from '@/components/map/MapLegend';
import { MAP_METRIC, fillFor, fmtCount, mapPalette } from '@/lib/mapScale';
import { useTapOrClick } from '@/hooks/useTapOrClick';

const GEO_URL = '/us-states-10m.json';

interface StateMapProps {
  /** State abbreviation → ENACTED law count (the site-wide map metric; see lib/mapScale). */
  data: Record<string, number>;
  selectedState?: string | null;
  /** A state to outline from outside — the jurisdiction of the table row under the pointer. */
  highlightState?: string | null;
  onStateClick?: (abbr: string) => void;
  height?: number;
}

/**
 * US states shaded on the site-wide enacted-laws scale (the globe's bins, so drilling in reads as
 * zooming in). Selection and the row-hover preview are an ink outline; colour only ever means count.
 */
export function StateMap({ data, selectedState, highlightState, onStateClick, height = 400 }: StateMapProps) {
  const { theme } = useTheme();
  const palette = useMemo(() => mapPalette(theme === 'dark'), [theme]);
  const verb = useTapOrClick();
  const [hover, setHover] = useState<string | null>(null);

  return (
    <div>
      <div className="relative rounded-lg border border-border-default" style={{ height, background: palette.ocean }}>
        <ComposableMap projection="geoAlbersUsa" style={{ width: '100%', height: '100%' }}>
          <Geographies geography={GEO_URL}>
            {({ geographies }) => {
              // Outlined states render last so their stroke isn't overpainted by a neighbour's hairline.
              const isOutlined = (abbr?: string) =>
                !!abbr && (abbr === selectedState || abbr === highlightState || abbr === hover);
              const ordered = [...geographies].sort((a, b) => {
                const oa = isOutlined(FIPS_TO_ABBR[String(a.id).padStart(2, '0')]) ? 1 : 0;
                const ob = isOutlined(FIPS_TO_ABBR[String(b.id).padStart(2, '0')]) ? 1 : 0;
                return oa - ob;
              });
              return ordered.map(geo => {
                const abbr = FIPS_TO_ABBR[String(geo.id).padStart(2, '0')];
                const count = abbr ? (data[abbr] ?? 0) : 0;
                const fill = fillFor(count, palette);
                const outlined = isOutlined(abbr);
                const strokeWidth = abbr === selectedState ? 2.25 : outlined ? 1.75 : 0.75;

                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={fill}
                    stroke={outlined ? palette.outline : palette.stroke}
                    strokeWidth={strokeWidth}
                    onClick={() => abbr && onStateClick?.(abbr)}
                    onMouseEnter={() => abbr && setHover(abbr)}
                    onMouseLeave={() => setHover(h => (h === abbr ? null : h))}
                    // Keyboard parity with the click handler (WCAG 2.1.1): focusable + Enter/Space.
                    tabIndex={onStateClick && abbr ? 0 : -1}
                    role={onStateClick && abbr ? 'button' : undefined}
                    aria-label={abbr ? `${STATE_NAMES[abbr] ?? abbr}: ${count} ${MAP_METRIC}` : undefined}
                    aria-pressed={onStateClick && abbr ? abbr === selectedState : undefined}
                    onFocus={() => abbr && setHover(abbr)}
                    onBlur={() => setHover(null)}
                    onKeyDown={
                      onStateClick && abbr
                        ? (e: React.KeyboardEvent) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              onStateClick(abbr);
                            }
                          }
                        : undefined
                    }
                    style={{
                      // Same fill on hover — the outline is the hover signal, colour stays the count.
                      default: { fill, outline: 'none', cursor: onStateClick ? 'pointer' : 'default' },
                      hover: { fill, outline: 'none' },
                      pressed: { fill, outline: 'none' },
                    }}
                  />
                );
              });
            }}
          </Geographies>
        </ComposableMap>
        <div className="pointer-events-none absolute left-2 top-2 rounded-md bg-bg-primary/90 px-2.5 py-1.5 text-xs shadow-sm backdrop-blur-sm">
          {hover ? (
            <span className="text-text-primary">
              <span className="font-semibold">{STATE_NAMES[hover] ?? hover}</span>
              {' · '}{fmtCount(data[hover] ?? 0)} {(data[hover] ?? 0) === 1 ? 'enacted law' : MAP_METRIC}
            </span>
          ) : (
            <span className="text-text-muted">{verb === 'tap' ? 'Tap' : 'Click'} a state to filter</span>
          )}
        </div>
      </div>
      <MapLegend palette={palette} showUntracked={false} className="mt-2" />
    </div>
  );
}
