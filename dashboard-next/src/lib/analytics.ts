// Thin wrapper around GA4 (gtag). The gtag script + config live in app/layout.tsx; components never
// touch `window.gtag` directly — they call `track()` so event names/usage stay greppable in one place.
//
// PII rule: never pass email, name, or free-text into GA params — GA's terms prohibit it and it bloats
// the property. Send counts, flags, and enums instead.

declare global {
  interface Window {
    gtag?: (command: string, ...args: unknown[]) => void;
  }
}

/** Fire a GA4 event. No-op on the server or before gtag has loaded. */
export function track(event: string, params: Record<string, unknown> = {}): void {
  if (typeof window === 'undefined' || typeof window.gtag !== 'function') return;
  window.gtag('event', event, params);
}

/** What a gate decided to do with the visitor. Keep in sync with the `outcome` custom dimension in GA. */
export type GateOutcome = 'sign_in' | 'checkout' | 'pricing' | 'allowed';

/**
 * A wall was RENDERED — a passive impression, the counterpart to trackGateHit's click.
 *
 * Having both is what turns "nobody upgraded" into "N saw the wall, M acted on it". Without the
 * impression, a drop-off is unattributable: you can't tell a wall nobody reached from a wall everyone
 * reached and declined. Fire this from the wall's mount effect.
 */
export function trackGateShown(gate: string, feature: string): void {
  track('gate_shown', { gate, feature });
}

/**
 * A visitor ACTED at a gate and we decided what to do with them. `gate` is the capability being
 * protected ('pro', or a capability key), `outcome` is what we did about it, and `feature` names the
 * specific CTA so two walls guarding the same capability stay distinguishable.
 *
 * Every gate in the app routes through here so the param names can't drift. That matters more than it
 * looks: GA custom dimensions bind to an exact param name and are NOT retroactive, so a param that's
 * misnamed (or never registered) is data lost permanently, not data you can reprocess later.
 */
export function trackGateHit(gate: string, outcome: GateOutcome, feature: string): void {
  track('gate_hit', { gate, outcome, feature });
}

/**
 * Set GA4 user properties — the "who is this" that segments EVERY event (free vs pro behavior, which
 * org, corporate vs personal). Registered as User-scoped custom dimensions in GA (plan_tier,
 * account_domain, org_name). Undefined/empty values are dropped so we never overwrite a real value
 * with blank. Same PII rule as track(): domain and tier only, never the raw email/name.
 */
export function setUserProperties(props: Record<string, string | undefined | null>): void {
  if (typeof window === 'undefined' || typeof window.gtag !== 'function') return;
  const clean: Record<string, string> = {};
  for (const [k, v] of Object.entries(props)) if (v) clean[k] = v;
  if (Object.keys(clean).length) window.gtag('set', 'user_properties', clean);
}

/**
 * Bind the GA4 user_id to the signed-in account (the Firebase uid — a pseudonymous, non-PII id, which
 * GA permits). This is what lets GA/BigQuery stitch a person's events across devices and sessions and
 * attribute a funnel to an account — e.g. the referral loop (this user's shares → the signups they
 * produced). Pass null on sign-out to unbind so a shared browser doesn't blend two accounts.
 */
export function setUserId(uid: string | null): void {
  if (typeof window === 'undefined' || typeof window.gtag !== 'function') return;
  window.gtag('set', { user_id: uid ?? null });
}

/**
 * Human-readable page title per route, so GA4's "page title" report distinguishes every route instead
 * of collapsing them all under the static layout title. Keep in sync with the app/ route folders.
 */
const ROUTE_TITLES: Record<string, string> = {
  '/': 'Bills (Home)',
  '/ask': 'Ask the Atlas',
  '/compliance': 'Compliance & Deadlines',
  '/watchlist': 'Watchlist',
  '/design-guide': 'Design Guide',
  '/states': 'States',
  '/federal': 'Federal',
  '/library': 'My Library',
  '/company': 'Company Impact',
  '/bill': 'Bill Detail',
  '/privacy': 'Privacy Policy',
  '/pricing': 'Pricing',
  '/account': 'Account',
  '/about': 'About',
  '/methodology': 'Methodology',
  '/insights': 'Insights',
  '/studio': 'Studio',
  '/label': 'Regulation Label',
  '/evaluate': 'Evaluate a Bill',
  '/developers': 'Developers',
  '/faq': 'FAQ',
  '/terms': 'Terms',
  '/beta': 'Beta',
  '/admin': 'Admin',
};

export function pageTitleFromPath(pathname: string): string {
  // next.config has trailingSlash:true, so usePathname yields '/pricing/' — strip it so the map hits.
  const path = pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
  if (ROUTE_TITLES[path]) return ROUTE_TITLES[path];
  // Dynamic per-state pages (/states/ca) — group them under a readable, state-stamped title.
  const stateMatch = path.match(/^\/states\/([a-z]{2})$/i);
  if (stateMatch) return `State: ${stateMatch[1].toUpperCase()}`;
  // Unified jurisdiction profiles (/jurisdictions/us/ca, /jurisdictions/jp/jp) — region/code stamped.
  const jxMatch = path.match(/^\/jurisdictions\/([a-z]{2})\/([a-z]{2})$/i);
  if (jxMatch) return `Jurisdiction: ${jxMatch[1].toUpperCase()}/${jxMatch[2].toUpperCase()}`;
  // Shared research threads (/r/<id>) and published articles (/p/<slug>) — collapse to one title each.
  // The id/slug is per-document, so leaving them raw fragments the report into one row per share.
  if (/^\/r\//.test(path)) return 'Shared Research';
  if (/^\/p\//.test(path)) return 'Published Article';
  return path;
}
