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

/**
 * Human-readable page title per route, so GA4's "page title" report distinguishes every route instead
 * of collapsing them all under the static layout title. Keep in sync with the app/ route folders.
 */
const ROUTE_TITLES: Record<string, string> = {
  '/': 'Bills (Home)',
  '/compliance': 'Compliance & Deadlines',
  '/watchlist': 'Watchlist',
  '/design-guide': 'Design Guide',
  '/states': 'States',
  '/federal': 'Federal',
  '/company': 'Company Impact',
  '/pricing': 'Pricing',
  '/about': 'About',
  '/methodology': 'Methodology',
};

export function pageTitleFromPath(pathname: string): string {
  return ROUTE_TITLES[pathname] ?? pathname;
}
