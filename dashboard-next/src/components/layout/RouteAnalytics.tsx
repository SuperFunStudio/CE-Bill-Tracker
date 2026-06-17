'use client';
import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { track, pageTitleFromPath } from '@/lib/analytics';

/**
 * GA4 page_view tracker for client-side navigation. Next.js App Router navigates without a full reload,
 * so gtag's automatic page_view (configured with `send_page_view: false` in layout.tsx) only ever fires
 * once. This fires one page_view per route change — including the initial mount — so every route shows
 * up in GA instead of collapsing into the landing page.
 *
 * NOTE: In GA Admin, turn OFF Enhanced Measurement → "Page changes based on browser history events"
 * to avoid double-counting these manual page_views.
 */
export function RouteAnalytics() {
  const pathname = usePathname();

  useEffect(() => {
    if (!pathname) return;
    track('page_view', {
      page_path: pathname,
      page_title: pageTitleFromPath(pathname),
      page_location: window.location.href,
    });
  }, [pathname]);

  // Stripe Checkout returns here on a full page load with ?checkout=success|cancel (success_url is
  // tier-specific: /design-guide for Pro, /compliance for Basic — see app/api/billing.py). This is the
  // only place the completed purchase is observable client-side. Fire once on mount, then strip the
  // param so a refresh can't double-count. (Authoritative revenue should come from the Stripe webhook
  // via the Measurement Protocol later; this gives the conversion event today.)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const checkout = params.get('checkout');
    if (!checkout) return;
    if (checkout === 'success') {
      const path = window.location.pathname;
      const tier = path.startsWith('/design-guide') ? 'pro' : path.startsWith('/compliance') ? 'basic' : 'unknown';
      track('purchase', { tier, method: 'stripe_checkout' });
    } else if (checkout === 'cancel') {
      track('checkout_cancel', {});
    }
    params.delete('checkout');
    const qs = params.toString();
    window.history.replaceState({}, '', window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash);
  }, []);

  return null;
}
