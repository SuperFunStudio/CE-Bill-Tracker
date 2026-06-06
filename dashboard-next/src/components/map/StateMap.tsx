'use client';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';
import { scaleLinear } from 'd3-scale';
import { FIPS_TO_ABBR } from '@/lib/utils';
import { useTheme } from '@/components/layout/ThemeContext';

const GEO_URL = '/us-states-10m.json';

interface StateMapProps {
  /** Map of state abbreviation → count (e.g. { OR: 5, CA: 12 }) */
  data: Record<string, number>;
  selectedState?: string | null;
  onStateClick?: (abbr: string) => void;
  height?: number;
}

export function StateMap({ data, selectedState, onStateClick, height = 400 }: StateMapProps) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const emptyFill  = isDark ? '#1f2937' : '#e5e7eb';
  const strokeColor = isDark ? '#374151' : '#d1d5db';
  const hoverFill  = isDark ? '#22c55e' : '#16a34a';

  const colorScale = scaleLinear<string>()
    .domain([0, 0.33, 0.66, 1])
    .range(isDark
      ? [emptyFill, '#14532d', '#166534', '#86efac']
      : [emptyFill, '#bbf7d0', '#4ade80', '#16a34a']);

  const maxCount = Math.max(...Object.values(data), 1);

  return (
    <div style={{ height }}>
      <ComposableMap
        projection="geoAlbersUsa"
        style={{ width: '100%', height: '100%' }}
      >
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies.map(geo => {
              const fips = geo.id as string;
              const abbr = FIPS_TO_ABBR[fips.padStart(2, '0')];
              const count = abbr ? (data[abbr] ?? 0) : 0;
              const isSelected = abbr === selectedState;

              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={isSelected ? '#facc15' : count > 0 ? colorScale(count / maxCount) : emptyFill}
                  stroke={isSelected ? '#facc15' : strokeColor}
                  strokeWidth={isSelected ? 2 : 0.5}
                  onClick={() => abbr && onStateClick?.(abbr)}
                  style={{
                    default: { outline: 'none', cursor: onStateClick ? 'pointer' : 'default' },
                    hover: { fill: isSelected ? '#facc15' : hoverFill, outline: 'none' },
                    pressed: { fill: '#16a34a', outline: 'none' },
                  }}
                />
              );
            })
          }
        </Geographies>
      </ComposableMap>
    </div>
  );
}
