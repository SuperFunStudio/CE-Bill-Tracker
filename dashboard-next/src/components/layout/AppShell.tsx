'use client';
import { usePathname } from 'next/navigation';
import { TopNav } from './TopNav';
import { GlobalRegionBar } from './GlobalRegionBar';
import { SiteFooter } from './SiteFooter';
import { ScopeOnboarding } from '@/components/scope/ScopeOnboarding';

/**
 * App chrome wrapper. Embed routes (`/embed/*`) render bare — no top nav and no
 * full-height scroll lock — so they sit cleanly inside a host-site iframe (e.g. a
 * Squarespace Code Block) and let the iframe size itself to the content. Every
 * other route gets the standard masthead + scroll shell.
 */
// Pages where the global jurisdiction bar is redundant or sends mixed signals, so each hosts its own
// scope control instead: '/compliance' now carries its own multi-select Regions filter (deadlines +
// the "does this apply to me" checker read it — it is NOT US-only anymore; the corpus spans 40+
// regions). '/federal' genuinely is US-only (federal actions). Packaging Studio quotes fixed foreign
// fee schedules (UK pEPR, JP JCPRA) that a US-state selector would contradict. Ask the Bills scopes
// geography from the QUESTION TEXT (resolve_facets), so the bar never reached the request. The home
// page ('/') hosts the Regions selector inside its own explorer filter box (BillFilters showRegion).
// '/pricing' has nothing a jurisdiction filter could scope — the coverage figures there are deliberately
// whole-corpus, and a filter above them invites the reader to shrink the thing being priced. '/methodology'
// is the same case: it describes how the whole engine works, and its counts are the whole-corpus totals.
const REGION_BAR_HIDDEN = ['/', '/compliance', '/federal', '/studio', '/ask', '/pricing', '/methodology'];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isEmbed = pathname?.startsWith('/embed') ?? false;

  if (isEmbed) return <>{children}</>;

  const showRegionBar = !REGION_BAR_HIDDEN.some(p => pathname === p || pathname?.startsWith(`${p}/`));

  return (
    <div className="flex flex-col h-[100dvh] overflow-hidden">
      <TopNav />
      {showRegionBar && <GlobalRegionBar />}
      <main className="flex-1 overflow-auto">
        {children}
        {/* The referral offer is the standing end-of-funnel CTA on every page — no longer buried in
            the Upcoming Deadlines lock card. Lives inside the scroll area, at the foot of content. */}
        <SiteFooter />
      </main>
      <ScopeOnboarding />
    </div>
  );
}
