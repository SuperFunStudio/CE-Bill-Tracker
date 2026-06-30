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
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isEmbed = pathname?.startsWith('/embed') ?? false;

  if (isEmbed) return <>{children}</>;

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <TopNav />
      <GlobalRegionBar />
      <main className="flex-1 overflow-auto">{children}</main>
      <ScopeOnboarding />
    </div>
  );
}
