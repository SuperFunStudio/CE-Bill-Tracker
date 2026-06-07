'use client';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';
import { FIPS_TO_ABBR } from '@/lib/utils';
import { useTheme } from '@/components/layout/ThemeContext';

const GEO_URL = '/us-states-10m.json';

// Solid spot color, opacity grows with activity (levels 1..4). Empty = barely-there tint.
const LEVEL_OPACITY = [0.25, 0.45, 0.7, 1.0];
const EMPTY_OPACITY = 0.07;

function withAlpha(hex: string, opacity: number) {
  const a = Math.round(Math.max(0, Math.min(1, opacity)) * 255)
    .toString(16)
    .padStart(2, '0');
  return hex + a;
}

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

  const color = isDark ? '#f3bcc3' : '#1e6ae9'; // pink on dark, blue on light
  // Stroke = page background so the ~1px border reads as a gap between states.
  const stroke = isDark ? '#111827' : '#f8f9fa';

  const maxCount = Math.max(...Object.values(data), 1);
  const level = (c: number) => (c <= 0 ? 0 : Math.min(4, Math.ceil((c / maxCount) * 4)));

  return (
    <div style={{ height }}>
      <ComposableMap projection="geoAlbersUsa" style={{ width: '100%', height: '100%' }}>
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies.map(geo => {
              const fips = geo.id as string;
              const abbr = FIPS_TO_ABBR[fips.padStart(2, '0')];
              const count = abbr ? (data[abbr] ?? 0) : 0;
              const lvl = level(count);
              const isSelected = abbr === selectedState;
              const op = isSelected ? 1 : lvl > 0 ? LEVEL_OPACITY[lvl - 1] : EMPTY_OPACITY;
              const baseFill = withAlpha(color, op);
              const hoverFill = withAlpha(color, Math.min(1, op + 0.2));

              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={baseFill}
                  stroke={isSelected ? color : stroke}
                  strokeWidth={isSelected ? 1.6 : 1}
                  onClick={() => abbr && onStateClick?.(abbr)}
                  style={{
                    default: { fill: baseFill, outline: 'none', cursor: onStateClick ? 'pointer' : 'default' },
                    hover: { fill: hoverFill, outline: 'none' },
                    pressed: { outline: 'none' },
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
