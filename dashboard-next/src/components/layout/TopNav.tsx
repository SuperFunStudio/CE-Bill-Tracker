'use client';
import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from './ThemeContext';
import { useRegion } from './RegionContext';
import { RegionSwitcher } from './RegionSwitcher';
import { useScrolled } from '@/hooks/useScrolled';
import { AuthButton } from '@/components/auth/AuthButton';
import { useAuth } from '@/components/auth/AuthContext';
import {
  HomeIcon, CalendarIcon, CapitolIcon, FactoryIcon, InfoIcon, TagIcon, CompassIcon, UserIcon, SunIcon, MoonIcon,
} from '@/components/ui/icons';

// `usOnly` items are hidden outside the US: Federal Actions has no EU analog yet (EU-central law is
// shown in the Bill Explorer), and company impact scoring is US-only. See RegionContext.
const NAV_ITEMS = [
  { href: '/', label: 'Bill Explorer', Icon: HomeIcon },
  { href: '/compliance', label: 'Upcoming Deadlines', Icon: CalendarIcon },
  { href: '/federal', label: 'Federal Actions', Icon: CapitolIcon, usOnly: true },
  { href: '/company', label: 'My Portfolio', Icon: FactoryIcon, usOnly: true },
  { href: '/design-guide', label: 'Design Guide', Icon: CompassIcon },
  { href: '/pricing', label: 'Pricing', Icon: TagIcon },
  { href: '/about', label: 'About', Icon: InfoIcon },
];

// Pro subscribers have already bought — surface "Account" where the "Pricing" link sits rather than
// keep selling them the plan they own. The /pricing route stays reachable directly.
const ACCOUNT_ITEM = { href: '/account', label: 'Account', Icon: UserIcon };

/**
 * Top nav with the "BATTLE OF THE BILLS" masthead centered, theme toggle pinned right.
 * At sm+ an inline section bar (newspaper-style) shows every destination; on mobile that
 * collapses behind the left hamburger into a dropdown. On scroll the brand shrinks.
 */
export function TopNav() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const scrolled = useScrolled(80);
  const { theme, toggle } = useTheme();
  const { isPro } = useAuth();
  const { region } = useRegion();

  // Hide US-only destinations outside the US, then swap Pricing→Account for Pro users.
  const navItems = NAV_ITEMS
    .filter(item => region === 'US' || !item.usOnly)
    .map(item => (isPro && item.href === '/pricing' ? ACCOUNT_ITEM : item));

  const isActive = (href: string) =>
    pathname === href || (href !== '/' && pathname.startsWith(href));

  // 'bar' = horizontal desktop section strip; 'menu' = stacked mobile dropdown rows.
  const renderLinks = (variant: 'bar' | 'menu') =>
    navItems.map(({ href, label, Icon }) => {
      const active = isActive(href);
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
    <header className="sticky top-0 z-40 bg-bg-secondary/95 backdrop-blur border-b border-border-default">
      <div
        className={`relative flex flex-col items-center justify-center px-14 transition-all duration-300 ${
          scrolled ? 'py-2.5' : 'py-5 sm:py-7'
        }`}
      >
        {/* Hamburger — left corner, mobile only (desktop uses the inline bar below) */}
        <button
          onClick={() => setMenuOpen(o => !o)}
          className={`sm:hidden absolute left-3 p-2 text-text-secondary hover:text-text-primary transition-all duration-300 ${
            scrolled ? 'top-1/2 -translate-y-1/2' : 'top-3'
          }`}
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

        {/* Brand — large & centered at top, condenses onto the button row on scroll */}
        <Link href="/" onClick={() => setMenuOpen(false)} className="text-center leading-none">
          <h1
            className={`font-serif uppercase text-text-primary tracking-[0.06em] transition-all duration-300 ${
              scrolled ? 'text-lg sm:text-xl' : 'text-3xl sm:text-5xl'
            }`}
          >
            Battle of the Bills
          </h1>
          <p
            className={`font-serif italic text-text-secondary overflow-hidden transition-all duration-300 ${
              scrolled ? 'max-h-0 opacity-0' : 'mt-2 max-h-10 opacity-100 text-sm sm:text-base'
            }`}
          >
            Tracking circularity legislation across the world
          </p>
        </Link>

        {/* Theme toggle — right corner */}
        <button
          onClick={toggle}
          className={`absolute right-3 p-2 text-lg text-text-secondary hover:text-text-primary transition-all duration-300 ${
            scrolled ? 'top-1/2 -translate-y-1/2' : 'top-3'
          }`}
          aria-label="Toggle theme"
        >
          {theme === 'light' ? <MoonIcon /> : <SunIcon />}
        </button>
      </div>

      {/* Desktop section bar — visible at sm+ */}
      <nav className="relative hidden sm:flex items-center justify-center flex-wrap gap-x-5 gap-y-1 border-t border-border-default px-4 py-2">
        <div className="absolute left-4 top-1/2 -translate-y-1/2">
          <RegionSwitcher />
        </div>
        {renderLinks('bar')}
        <div className="absolute right-4 top-1/2 -translate-y-1/2">
          <AuthButton />
        </div>
      </nav>

      {/* Mobile dropdown menu (opened by the hamburger) */}
      {menuOpen && (
        <nav className="sm:hidden absolute left-0 right-0 top-full bg-bg-secondary border-b border-border-default shadow-lg">
          <div className="max-w-6xl mx-auto p-3 space-y-1">
            <div className="pb-2 mb-1 border-b border-border-default">
              <RegionSwitcher />
            </div>
            {renderLinks('menu')}
            <div className="pt-2 border-t border-border-default mt-2">
              <AuthButton variant="menu" onNavigate={() => setMenuOpen(false)} />
            </div>
            <div className="text-text-muted text-xs text-center pt-2">
              Circularity legislation tracker · Beta
            </div>
          </div>
        </nav>
      )}
    </header>
  );
}
