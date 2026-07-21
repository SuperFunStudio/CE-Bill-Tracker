'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { CompassIcon, PackageIcon } from '@/components/ui/icons';

// The two Guides live at their own routes (each keeps its own state — the Design Guide's bill modal,
// the Packaging Studio's hash-encoded spec), so the tabs are Links, not client-toggled panels. That
// keeps every existing deep link (/studio#<spec>, ?bill=…) working while presenting one tabbed surface.
const TABS = [
  { href: '/design-guide', label: 'Design Guide', Icon: CompassIcon, beta: false },
  // Beta: the calculator is sound but the layout is still being reworked — flag it as in-progress
  // rather than present it as finished. Drop `beta` once the Studio redesign lands.
  { href: '/studio', label: 'Packaging Studio', Icon: PackageIcon, beta: true },
] as const;

export function GuidesTabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="Guides" className="flex flex-wrap items-center gap-1.5 border-b border-border-default pb-px">
      {TABS.map(({ href, label, Icon, beta }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? 'page' : undefined}
            className={`inline-flex items-center gap-1.5 rounded-t-lg border-b-2 px-3.5 py-2 text-sm font-serif tracking-wide transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 ${
              active
                ? 'border-green-accent text-green-accent'
                : 'border-transparent text-text-secondary hover:text-text-primary'
            }`}
          >
            <Icon className="text-[1rem] shrink-0 opacity-70" />
            <span>{label}</span>
            {beta && (
              <span className="rounded-full border border-green-accent/40 px-1.5 py-px text-[0.6rem] font-sans uppercase tracking-wider text-green-accent">
                Beta
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
