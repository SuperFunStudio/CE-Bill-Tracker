'use client';
import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from './ThemeContext';
import { useRegion } from './RegionContext';
import { AuthButton } from '@/components/auth/AuthButton';
import { useAuth } from '@/components/auth/AuthContext';
import {
  HomeIcon, CalendarIcon, FactoryIcon, InfoIcon, TagIcon, CompassIcon, UserIcon, SunIcon, MoonIcon,
  LabelIcon, ScaleIcon, ChartIcon, CapitolIcon,
} from '@/components/ui/icons';

// `usOnly` items are hidden outside the US (company impact scoring is US-only; Federal Actions, now a
// tab under Upcoming Deadlines, has no EU analog yet). See RegionContext. `altPaths` keeps a nav item
// active on sibling routes it fronts (Upcoming Deadlines → /compliance fronts /federal; Guides →
// /design-guide fronts /studio too).
type NavItem = {
  href: string;
  label: string;
  Icon: typeof HomeIcon;
  usOnly?: boolean;
  adminOnly?: boolean;
  altPaths?: string[];
};

const NAV_ITEMS: NavItem[] = [
  // Explore is the unified surface: the faceted bill browse AND "Ask the Atlas" share one adaptive
  // bar (keywords filter; a question gets a grounded, cited answer over the same corpus). /ask
  // redirects here, preserving ?session= so saved research threads still open.
  { href: '/', label: 'Explore', Icon: HomeIcon },
  // Rankings is the global two-column activity tracker (national law by country + sub-national) —
  // global, so no usOnly gate. /states adapts to the region selection (US momentum / EU / two-column).
  { href: '/states', label: 'Rankings', Icon: CapitolIcon },
  // Upcoming Deadlines is a tabbed surface — Federal Actions is folded in as a subpage tab (see
  // DeadlinesTabs), so /federal lights this item up too. Federal has no top-level nav entry anymore.
  { href: '/compliance', label: 'Upcoming Deadlines', Icon: CalendarIcon, altPaths: ['/federal'] },
  { href: '/library', label: 'My Library', Icon: FactoryIcon, usOnly: true },
  // Insights is the analytics briefing room — shown to everyone; the page itself carries the same
  // Pro membership gate as Federal Actions / Packaging Studio, so it does the selling on click.
  { href: '/insights', label: 'Insights', Icon: ChartIcon },
  // Guides is a tabbed surface — the Design Guide (design imperatives from enacted law) and the
  // Packaging Studio (price-a-package walkthrough) share it. Nav points at the Design Guide tab; the
  // in-page GuidesTabs switches between them, so both /design-guide and /studio light this item up.
  { href: '/design-guide', label: 'Guides', Icon: CompassIcon, altPaths: ['/studio'] },
  // Prototype — dogfooding in prod, admin-only; graduates to Pro alongside /ask (drop adminOnly, the
  // page + endpoint already gate on isPro / require_pro).
  { href: '/evaluate', label: 'Evaluate a Bill', Icon: ScaleIcon, adminOnly: true },
  // Regulation Facts is admin-only for now — still being validated, so it's kept off the public nav
  // (and its route guarded) until it graduates. See the /label page guard.
  { href: '/label', label: 'Regulation Facts', Icon: LabelIcon, adminOnly: true },
  { href: '/pricing', label: 'Pricing', Icon: TagIcon },
  { href: '/about', label: 'About', Icon: InfoIcon },
];

// Pro subscribers have already bought — surface "Account" where the "Pricing" link sits rather than
// keep selling them the plan they own. The /pricing route stays reachable directly.
const ACCOUNT_ITEM: NavItem = { href: '/account', label: 'Account', Icon: UserIcon };

/**
 * Top nav: a single slim bar with the "ATLAS CIRCULAR" wordmark on the left and the inline
 * section links on the right, theme + account pinned far right. Below lg the inline links
 * collapse behind the hamburger into a dropdown (the full set only fits one row at lg+).
 *
 * Non-animated by design: the bar has a fixed height and nothing resizes on scroll, so
 * pinning it never reflows the page. (An earlier version shrank a taller pinned header,
 * which shortened the document above the viewport and yanked content upward — the "zoom
 * forward" jolt, worst on mobile.)
 */
export function TopNav() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const { theme, toggle } = useTheme();
  const { isPro, isAdmin } = useAuth();
  const { isUsView } = useRegion();

  // Hide US-only destinations outside the US and admin-only tools from non-admins, then swap
  // Pricing→Account for Pro users.
  const navItems = NAV_ITEMS
    .filter(item => isUsView || !item.usOnly)
    .filter(item => isAdmin || !item.adminOnly)
    .map(item => (isPro && item.href === '/pricing' ? ACCOUNT_ITEM : item));

  const matchPath = (href: string) =>
    pathname === href || (href !== '/' && pathname.startsWith(href));
  // A nav item is active on its own href or any of its altPaths (e.g. Guides → /design-guide, /studio).
  const isActive = (href: string, altPaths?: string[]) =>
    matchPath(href) || (altPaths?.some(matchPath) ?? false);

  // 'bar' = horizontal desktop section strip; 'menu' = stacked mobile dropdown rows.
  const renderLinks = (variant: 'bar' | 'menu') =>
    navItems.map(({ href, label, Icon, altPaths }) => {
      const active = isActive(href, altPaths);
      const cls = variant === 'bar'
        ? `inline-flex items-center gap-1.5 px-2 py-1 font-serif text-sm tracking-wide border-b-2 transition-colors ${
            active
              ? 'border-green-accent text-green-accent'
              : 'border-transparent text-text-secondary hover:text-text-primary'
          }`
        : `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
            active
              ? 'bg-green-dark text-green-accent font-medium'
              : 'text-text-secondary hover:bg-bg-primary hover:text-text-primary'
          }`;
      return (
        <Link key={href} href={href} onClick={() => setMenuOpen(false)} className={cls}>
          <Icon className={variant === 'bar' ? 'text-[1rem] shrink-0 opacity-70' : 'text-[1.15rem] shrink-0 opacity-80'} />
          <span>{label}</span>
        </Link>
      );
    });

  return (
    // Single slim sticky bar — brand left, inline section links right (frog-style). Fixed
    // height, nothing resizes on scroll, so no reflow/"zoom" jump and the brand shows once.
    <header className="sticky top-0 z-40 bg-bg-secondary/95 backdrop-blur border-b border-border-default">
      <div className="flex items-center gap-3 px-4 sm:px-6 min-h-[3.25rem] py-2">
        {/* Brand — left. The slogan rides alongside as secondary text (hidden until there's
            room for it) so identity stays without a whole masthead row. */}
        <Link href="/" onClick={() => setMenuOpen(false)} className="flex items-center gap-2.5 shrink-0">
          <span className="font-serif uppercase text-text-primary tracking-[0.06em] text-lg sm:text-xl leading-none">
            Atlas Circular
          </span>
          <span className="hidden xl:inline border-l border-border-default pl-2.5 font-serif text-text-muted text-xs leading-tight">
            Tracking circularity globally
          </span>
        </Link>

        {/* Desktop section links — inline only at lg+, where the full set fits on one row;
            below that everything collapses behind the hamburger. */}
        <nav className="hidden lg:flex flex-1 items-center justify-end flex-wrap gap-x-5 gap-y-1">
          {renderLinks('bar')}
        </nav>

        {/* Desktop right controls — theme + account. */}
        <div className="hidden lg:flex items-center gap-1 shrink-0">
          <button
            onClick={toggle}
            className="p-1.5 text-lg text-text-secondary hover:text-text-primary"
            aria-label="Toggle theme"
          >
            {theme === 'light' ? <MoonIcon /> : <SunIcon />}
          </button>
          <AuthButton />
        </div>

        {/* Compact right controls — theme + hamburger (links live in the dropdown). Shown up
            through the tablet range; the inline bar only takes over at lg+. */}
        <div className="flex items-center gap-1 ml-auto lg:hidden">
          <button
            onClick={toggle}
            className="p-2 text-lg text-text-secondary hover:text-text-primary"
            aria-label="Toggle theme"
          >
            {theme === 'light' ? <MoonIcon /> : <SunIcon />}
          </button>
          <button
            onClick={() => setMenuOpen(o => !o)}
            className="p-2 text-text-secondary hover:text-text-primary"
            aria-label="Toggle navigation"
            aria-expanded={menuOpen}
          >
            {menuOpen ? (
              <svg width="22" height="22" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg width="22" height="22" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Dropdown menu (opened by the hamburger) — anchored below the bar; used below lg */}
      {menuOpen && (
        <nav className="lg:hidden absolute left-0 right-0 top-full bg-bg-secondary border-b border-border-default shadow-lg">
          <div className="max-w-6xl mx-auto p-3 space-y-1">
            {renderLinks('menu')}
            <div className="pt-2 border-t border-border-default mt-2">
              <AuthButton variant="menu" onNavigate={() => setMenuOpen(false)} />
            </div>
            <div className="text-text-muted text-xs text-center pt-2">
              Circular-economy law atlas · Beta
            </div>
          </div>
        </nav>
      )}
    </header>
  );
}
