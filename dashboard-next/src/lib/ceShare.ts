// Share loop for the /circular-economy map, built so its viral coefficient can be MEASURED, not guessed.
//
// Every share link carries three things besides the view itself:
//   via  a fresh id per share (one row per link sent: which links got opened, and how often)
//   g    the generation: 1 for a link made by an organic visitor, n+1 for a link made by someone who
//        arrived on a generation-n link. Carried through the session in sessionStorage.
//   utm_source=share, utm_medium=<copy|native|image>, utm_campaign=ce_map, so a later sign_up is credited
//        to the loop by the existing last-touch attribution (lib/attribution).
// A signed-in sharer's referral code rides along as ?ref=, so the free-month reward applies here too.
//
// Reading K in GA4 (register share_gen + share_method as event-scoped custom dimensions first; GA is not
// retroactive):
//   K ≈ ce_map_share_landed{share_gen = n+1} / ce_map_share_landed{share_gen = n}
//   or, for one cohort:  K = (ce_map_share per visitor) × (ce_map_share_landed per ce_map_share)
// with visitors = page_view users on /circular-economy/. K > 1 on a generation means it grew.

import { track } from '@/lib/analytics';

const GEN_KEY = 'ce_map_share_gen';
export const SHARE_PARAMS = ['via', 'g', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'ref'];

/** The generation this session arrived on (0 = organic). */
export function landedGeneration(): number {
  try {
    return Number(sessionStorage.getItem(GEN_KEY) ?? 0) || 0;
  } catch {
    return 0;
  }
}

/** Call once on mount: records a share-link landing and remembers its generation for later shares. */
export function captureShareLanding(): void {
  if (typeof window === 'undefined') return;
  const p = new URLSearchParams(window.location.search);
  const via = p.get('via');
  if (!via) return;
  const gen = Math.max(1, Math.min(99, Number(p.get('g')) || 1));
  try { sessionStorage.setItem(GEN_KEY, String(gen)); } catch { /* the chain just restarts at 1 */ }
  track('ce_map_share_landed', { share_id: via.slice(0, 16), share_gen: gen, has_ref: p.has('ref') });
}

const shareId = () => Math.random().toString(36).slice(2, 10);

/** A share link for the current view. `view` holds only the view's own params (regions, material…). */
export function buildShareLink(view: URLSearchParams, method: 'copy' | 'native' | 'image', refCode?: string | null) {
  const id = shareId();
  const gen = landedGeneration() + 1;
  const p = new URLSearchParams(view);
  p.set('via', id);
  p.set('g', String(gen));
  p.set('utm_source', 'share');
  p.set('utm_medium', method);
  p.set('utm_campaign', 'ce_map');
  if (refCode) p.set('ref', refCode);
  return { url: `${window.location.origin}/circular-economy/?${p}`, id, gen };
}

/** One event per share sent. `view_mode` and `material` say WHAT got shared, the thing worth tuning. */
export function trackShare(method: 'copy' | 'native' | 'image', id: string, gen: number, extra: Record<string, unknown>) {
  track('ce_map_share', { share_method: method, share_id: id, share_gen: gen, ...extra });
}
