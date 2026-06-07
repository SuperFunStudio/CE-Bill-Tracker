'use client';
import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from './ThemeContext';
import { useScrolled } from '@/hooks/useScrolled';

const NAV_ITEMS = [
  { href: '/', label: 'Bill Explorer', icon: '🏠' },
  { href: '/compliance', label: 'Upcoming Deadlines', icon: '📅' },
  { href: '/federal', label: 'Federal Actions', icon: '🏛️' },
  { href: '/company', label: 'Company Impact', icon: '🏭' },
];

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-primary hover:text-text-primary transition-colors"
      aria-label="Toggle theme"
    >
      <span className="text-base">{theme === 'light' ? '🌙' : '☀️'}</span>
      <span>{theme === 'light' ? 'Dark mode' : 'Light mode'}</span>
    </button>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const scrolled = useScrolled();

  const navLinks = NAV_ITEMS.map(({ href, label, icon }) => {
    const isActive = pathname === href || (href !== '/' && pathname.startsWith(href));
    return (
      <Link
        key={href}
        href={href}
        onClick={() => setMobileOpen(false)}
        className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
          isActive
            ? 'bg-green-dark text-green-accent font-medium'
            : 'text-text-secondary hover:bg-bg-primary hover:text-text-primary'
        }`}
      >
        <span>{icon}</span>
        <span>{label}</span>
      </Link>
    );
  });

  return (
    <>
      {/* ── Desktop sidebar (hidden below md) ── */}
      <aside className="hidden md:flex w-56 min-h-screen bg-bg-secondary border-r border-border-default flex-col shrink-0">
        <div className="p-4 border-b border-border-default">
          <Link href="/" className="block hover:opacity-80 transition-opacity">
            <div className="font-serif text-text-primary text-lg leading-tight">
              Battle of the <span className="text-green-accent">Bills</span>
            </div>
            <div className="text-text-muted text-xs mt-0.5 flex items-center gap-1.5">
              Circularity legislation
              <span className="text-[10px] uppercase tracking-wide text-green-accent border border-green-accent/40 rounded px-1 leading-tight">Beta</span>
            </div>
          </Link>
        </div>
        <nav className="flex-1 p-3 space-y-1">{navLinks}</nav>
        <div className="p-3 border-t border-border-default space-y-1">
          <ThemeToggle />
          <div className="text-text-muted text-xs text-center pt-1">Circularity legislation tracker</div>
        </div>
      </aside>

      {/* ── Mobile top bar (visible below md) — sun + menu, brand appears on scroll ── */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 bg-bg-secondary border-b border-border-default flex items-center justify-between gap-2 px-4 h-12">
        <Link
          href="/"
          className={`font-serif text-text-primary text-base tracking-wide transition-opacity duration-300 ${
            scrolled ? 'opacity-100' : 'opacity-0 pointer-events-none'
          }`}
        >
          Battle of the Bills
        </Link>
        <div className="flex items-center gap-2">
          <MobileThemeToggle />
          <button
            onClick={() => setMobileOpen(o => !o)}
            className="text-text-secondary hover:text-text-primary p-1"
            aria-label="Toggle navigation"
          >
            {mobileOpen ? (
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Mobile dropdown menu */}
      {mobileOpen && (
        <div className="md:hidden fixed top-12 left-0 right-0 z-40 bg-bg-secondary border-b border-border-default shadow-lg">
          <nav className="p-3 space-y-1">{navLinks}</nav>
        </div>
      )}
    </>
  );
}

function MobileThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      className="text-text-secondary hover:text-text-primary p-1 text-base"
      aria-label="Toggle theme"
    >
      {theme === 'light' ? '🌙' : '☀️'}
    </button>
  );
}
