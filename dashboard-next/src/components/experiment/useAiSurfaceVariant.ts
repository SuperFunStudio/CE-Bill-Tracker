'use client';
import { useEffect, useState } from 'react';
import { track } from '@/lib/analytics';

/**
 * Client-side A/B for the Explore search bar's AI surface: does showing the "AI Analysis" toggle +
 * Ask button next to the keyword box help or hurt?
 *
 *  • "shown"  — today's bar: the toggle flips the box between keyword filtering and asking, and Ask
 *               hands the question off to /ask.
 *  • "hidden" — the box is a plain keyword filter. Nothing is taken away, only moved: the line under
 *               the bar links to /ask, which owns the conversation anyway, and the facets open by
 *               default since they're the only controls left on that row.
 *
 * The hypothesis worth testing is whether the toggle is a fork in the road that stalls people at the
 * top of the page. Segment any downstream event by `ai_surface_variant` (fired on every load as
 * `ai_surface_exposed`) to answer it — asks started, bills opened, filters touched, CSV exports.
 *
 * Same mechanics as useHomeVariant: the production build is a static export (no server, no
 * middleware), so bucketing happens in the browser and sticks per device in localStorage. Variant
 * "shown" matches the pre-rendered HTML, so crawlers and first paint always get it and the swap
 * happens after mount. Dial with HIDDEN_SHARE; ENABLED=false ends the test (everyone sees the
 * toggle, including devices previously bucketed into "hidden").
 */
const VARIANT_KEY = 'ac_ai_surface_variant';
const HIDDEN_SHARE = 0.5;
const ENABLED = true;

export type AiSurfaceVariant = 'shown' | 'hidden';

export function useAiSurfaceVariant(): { variant: AiSurfaceVariant; ready: boolean } {
  const [variant, setVariant] = useState<AiSurfaceVariant>('shown');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ENABLED) { setVariant('shown'); setReady(true); return; }
    let v: AiSurfaceVariant;
    let assigned = false;
    try {
      const stored = localStorage.getItem(VARIANT_KEY);
      if (stored === 'shown' || stored === 'hidden') {
        v = stored;
      } else {
        v = Math.random() < HIDDEN_SHARE ? 'hidden' : 'shown';
        assigned = true;
        localStorage.setItem(VARIANT_KEY, v);
      }
    } catch {
      v = 'shown'; // storage blocked (private mode) → default experience, no test
    }
    setVariant(v);
    setReady(true);
    if (assigned) track('ai_surface_assigned', { variant: v });
    // Every load, so conversions can be segmented by variant rather than only first assignment.
    track('ai_surface_exposed', { variant: v });
  }, []);

  return { variant, ready };
}
