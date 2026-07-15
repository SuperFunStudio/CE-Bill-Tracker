'use client';
import { usePathname } from 'next/navigation';
import { TopNav } from './TopNav';
import { GlobalRegionBar } from './GlobalRegionBar';
import { ScopeOnboarding } from '@/components/scope/ScopeOnboarding';

/**
 * App chrome wrapper. Embed routes (`/embed/*`) render bare — no top nav and no
 * full-height scroll lock — so they sit cleanly inside a host-site iframe (e.g. a
 * Squarespace Code Block) and let the iframe size itself to the content. Every
 * other route gets the standard masthead + scroll shell.
 */
// Pages where the global jurisdiction filter is meaningless and only sends mixed signals: Upcoming
// Deadlines + Federal Actions are US-only datasets, and Packaging Studio quotes fixed foreign fee
// schedules (UK pEPR, JP JCPRA) that a US-state region selector would contradict. Ask the Bills scopes
// geography from the QUESTION TEXT (resolve_facets), so the bar is a dead control there — it never
// reached the request. Atlas-migration note: when the ask textbox becomes the primary home UI, the
// global region filter should fold into the unified bill-explorer filter set, not sit above the ask.
const REGION_BAR_HIDDEN = ['/compliance', '/federal', '/studio', '/ask'];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isEmbed = pathname?.startsWith('/embed') ?? false;

  if (isEmbed) return <>{children}</>;

  const showRegionBar = !REGION_BAR_HIDDEN.some(p => pathname === p || pathname?.startsWith(`${p}/`));

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <TopNav />
      {showRegionBar && <GlobalRegionBar />}
      <main className="flex-1 overflow-auto">{children}</main>
      <ScopeOnboarding />
    </div>
  );
}
