'use client';
import { useEffect, useState } from 'react';
import { track } from '@/lib/analytics';

/**
 * Client-side A/B assignment for the homepage. The production build is a static export (no server /
 * middleware), so bucketing happens in the browser and is persisted in localStorage — stable per
 * device across sessions. Variant "a" is the current homepage (also what the pre-rendered HTML shows,
 * so crawlers and first paint always get A); "b" is the new dot-explorer, swapped in after mount for
 * bucketed devices.
 *
 * Rollout: 50% of ALL visitors (new and returning). Dial B's share with B_SHARE — 0 disables the test
 * (everyone gets A), 1 forces B. Exposure fires once per device as `home_variant_assigned`.
 */
const VARIANT_KEY = 'ac_home_variant';   // 'a' | 'b' — the sticky assignment
const VISITED_KEY = 'ac_visited';        // set on first ever visit → distinguishes new vs returning
const B_SHARE = 0.5;                     // fraction routed to Homepage B

export type HomeVariant = 'a' | 'b';

export function useHomeVariant(): { variant: HomeVariant; ready: boolean } {
  // Default 'a' (matches the static HTML) until the effect resolves the sticky bucket post-mount.
  const [variant, setVariant] = useState<HomeVariant>('a');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let v: HomeVariant;
    let assigned = false;
    let audience: 'new' | 'returning' = 'returning';
    try {
      const stored = localStorage.getItem(VARIANT_KEY);
      audience = localStorage.getItem(VISITED_KEY) ? 'returning' : 'new';
      if (stored === 'a' || stored === 'b') {
        v = stored;
      } else {
        v = Math.random() < B_SHARE ? 'b' : 'a';
        assigned = true;
        localStorage.setItem(VARIANT_KEY, v);
      }
      localStorage.setItem(VISITED_KEY, '1');
    } catch {
      v = 'a'; // storage blocked (private mode) → default experience, no test
    }
    setVariant(v);
    setReady(true);
    if (assigned) track('home_variant_assigned', { variant: v, audience });
    // Fire on every load so downstream conversions can be segmented by variant, not just first assignment.
    track('home_variant_exposed', { variant: v, audience });
  }, []);

  return { variant, ready };
}
