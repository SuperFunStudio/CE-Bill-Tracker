// One choropleth scale for every map on the site — the globe, the US state map and the regional inset
// maps all shade by the same metric (ENACTED laws) through the same fixed bins, so drilling from the
// globe into a country reads as zooming in rather than switching to a different chart. Fixed absolute
// bins (not "relative to the busiest unit") are what make that true: a state with 20 enacted laws is
// the same shade as a country with 20.
//
// Calibrated against prod (2026-10): countries top out near 300 once EU-central law is counted for
// members (FR ≈ 294, US ≈ 286); US states top out at 45 (CA). The bins are roughly log-spaced so both
// levels spread across the ramp.
//
// Encoding rules (see the Explore redesign notes):
//  - Colour means "more enacted laws" and nothing else. Selection and hover are an OUTLINE, never a
//    fill change, so the accent never doubles as "selected".
//  - "Not tracked" (we ingest nothing there) is hatched, with its own legend swatch, so it can't be
//    mistaken for the lightest data bin. Tracked-but-zero is the plain land fill.

/** Lower bound of each bin, ascending. A count below the first bound (i.e. 0) is "none". */
export const ENACTED_BINS = [1, 5, 15, 50, 150] as const;

/** The metric name the map colour encodes — used verbatim in every heading, legend and readout. */
export const MAP_METRIC = 'enacted laws';

/** Bin index 0..4 for a count, or -1 for zero/negative. */
export function binOf(n: number): number {
  let b = -1;
  for (let i = 0; i < ENACTED_BINS.length; i++) if (n >= ENACTED_BINS[i]) b = i;
  return b;
}

/** "1–4", "5–14", … "150+" */
export function binLabel(i: number): string {
  const lo = ENACTED_BINS[i];
  const next = ENACTED_BINS[i + 1];
  return next === undefined ? `${lo}+` : `${lo}–${next - 1}`;
}

// Mix weight of the accent over the land base for each bin. Starts high enough (0.3) that the lightest
// data bin separates clearly from plain land, and steps evenly to the full accent.
const BIN_WEIGHT = [0.3, 0.47, 0.64, 0.82, 1];

type RGB = [number, number, number];
const hex = (h: string): RGB => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)) as RGB;
const css = ([r, g, b]: RGB) => `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
const mix = (a: RGB, b: RGB, w: number): RGB => [0, 1, 2].map(i => a[i] + (b[i] - a[i]) * w) as RGB;

export interface MapPalette {
  /** Land with no enacted laws (tracked, zero). */
  land: string;
  /** Sea / page behind the map. */
  ocean: string;
  /** Hairline between units — the page background, so borders read as gaps. */
  stroke: string;
  /** Hatch line colour for "not tracked". */
  hatch: string;
  /** Selection / hover outline — the ink colour, deliberately NOT the accent. */
  outline: string;
  /** The five bin fills, lightest → darkest. Solid colours (not alpha) so SVG, canvas and the legend
   *  swatches render identically. */
  bins: string[];
}

export function mapPalette(isDark: boolean): MapPalette {
  const land = isDark ? '#273241' : '#e2e8f0';
  const accent = isDark ? '#f3bcc3' : '#1e6ae9';
  return {
    land,
    ocean: isDark ? '#0b1220' : '#eef2f6',
    stroke: isDark ? '#111827' : '#f8f9fa',
    hatch: isDark ? '#4b5563' : '#a8b3c2',
    outline: isDark ? '#f3f4f6' : '#1a1a2e',
    bins: BIN_WEIGHT.map(w => css(mix(hex(land), hex(accent), w))),
  };
}

/** Fill for a count: a bin colour, or the land base for zero. */
export function fillFor(n: number, p: MapPalette): string {
  const b = binOf(n);
  return b < 0 ? p.land : p.bins[b];
}

/** CSS background for a hatched "not tracked" swatch (legend chips, HTML overlays). */
export function hatchBackground(p: MapPalette): string {
  return `repeating-linear-gradient(135deg, ${p.hatch} 0 1px, ${p.land} 1px 4px)`;
}

/** Locale-aware thousands separators everywhere a count is shown. */
export const fmtCount = (n: number) => n.toLocaleString('en-US');
