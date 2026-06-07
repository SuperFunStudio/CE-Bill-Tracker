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
  { href: '/about', label: 'About', icon: 'ℹ️' },
];

/**
 * Single unified top nav across all screen sizes.
 * At the top of the page the "BATTLE OF THE BILLS" brand is large and centered,
 * with the hamburger (left) and theme toggle (right) pinned to the corners.
 * On scroll the brand shrinks onto the same compact row as those two buttons.
 */
export function TopNav() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const scrolled = useScrolled(80);
  const { theme, toggle } = useTheme();

  const navLinks = NAV_ITEMS.map(({ href, label, icon }) => {
    const isActive = pathname === href || (href !== '/' && pathname.startsWith(href));
    return (
      <Link
        key={href}
        href={href}
        onClick={() => setMenuOpen(false)}
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
    <header className="sticky top-0 z-40 bg-bg-secondary/95 backdrop-blur border-b border-border-default">
      <div
        className={`relative flex flex-col items-center justify-center px-14 transition-all duration-300 ${
          scrolled ? 'py-2.5' : 'py-5 sm:py-7'
        }`}
      >
        {/* Hamburger — left corner */}
        <button
          onClick={() => setMenuOpen(o => !o)}
          className={`absolute left-3 p-2 text-text-secondary hover:text-text-primary transition-all duration-300 ${
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
            Battle of the <span className="text-green-accent">Bills</span>
          </h1>
          <p
            className={`font-serif italic text-text-secondary overflow-hidden transition-all duration-300 ${
              scrolled ? 'max-h-0 opacity-0' : 'mt-2 max-h-10 opacity-100 text-sm sm:text-base'
            }`}
          >
            Tracking circularity-aligned legislation across the USA
          </p>
        </Link>

        {/* Theme toggle — right corner */}
        <button
          onClick={toggle}
          className={`absolute right-3 p-2 text-base text-text-secondary hover:text-text-primary transition-all duration-300 ${
            scrolled ? 'top-1/2 -translate-y-1/2' : 'top-3'
          }`}
          aria-label="Toggle theme"
        >
          {theme === 'light' ? '🌙' : '☀️'}
        </button>
      </div>

      {/* Dropdown nav menu (opened by the hamburger, all screen sizes) */}
      {menuOpen && (
        <nav className="absolute left-0 right-0 top-full bg-bg-secondary border-b border-border-default shadow-lg">
          <div className="max-w-6xl mx-auto p-3 space-y-1">
            {navLinks}
            <div className="text-text-muted text-xs text-center pt-2 border-t border-border-default mt-2">
              Circularity legislation tracker · Beta
            </div>
          </div>
        </nav>
      )}
    </header>
  );
}
