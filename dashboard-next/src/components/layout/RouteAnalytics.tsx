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

  return null;
}
