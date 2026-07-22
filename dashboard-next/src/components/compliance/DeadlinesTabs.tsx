'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useRegion } from '@/components/layout/RegionContext';
import { CalendarIcon, CapitolIcon } from '@/components/ui/icons';

// Upcoming Deadlines and Federal Actions each keep their own route + state (the deadline calendar's
// scope, the federal filters), so the tabs are Links, not client-toggled panels — every deep link
// keeps working while the two present as one tabbed surface. Mirrors GuidesTabs.
//
// Federal Actions is US-only (no EU analog yet — see TopNav's usOnly note), so its tab only appears
// in the US region view; outside the US, Upcoming Deadlines stands alone.
const TABS = [
  { href: '/compliance', label: 'Upcoming Deadlines', Icon: CalendarIcon, usOnly: false },
  { href: '/federal', label: 'Federal Actions', Icon: CapitolIcon, usOnly: true },
] as const;

export function DeadlinesTabs() {
  const pathname = usePathname();
  const { isUsView } = useRegion();
  const tabs = TABS.filter((t) => isUsView || !t.usOnly);
  return (
    <nav aria-label="Deadlines" className="flex flex-wrap items-center gap-1.5 border-b border-border-default pb-px">
      {tabs.map(({ href, label, Icon }) => {
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
          </Link>
        );
      })}
    </nav>
  );
}
