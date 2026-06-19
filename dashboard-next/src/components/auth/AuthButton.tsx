'use client';
import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { useAuth } from './AuthContext';
import { openBillingPortal } from '@/lib/billing';

/**
 * Top-nav auth control. Two variants:
 *  - `bar` (default): compact pill for the desktop section bar; logged-in state opens a nested
 *    absolute-positioned dropdown.
 *  - `menu`: flat, full-width rows for the mobile hamburger menu. The nested dropdown doesn't work
 *    there (it gets clipped at the screen edge, and the menu's own close-on-tap would dismiss it
 *    before it opens), so we inline every action as its own row instead. `onNavigate` lets the
 *    parent close the mobile menu after a row is tapped.
 */
export function AuthButton({
  variant = 'bar',
  onNavigate,
}: {
  variant?: 'bar' | 'menu';
  onNavigate?: () => void;
} = {}) {
  const { user, loading, isPro, openAuth, signOut, getToken } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  if (loading) return <span className="text-text-muted text-xs">…</span>;

  // ── Mobile menu variant: flat rows, no nested dropdown ──────────────────────────────
  if (variant === 'menu') {
    const rowCls =
      'flex w-full items-center gap-3 px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-primary hover:text-text-primary transition-colors text-left';
    if (!user) {
      return (
        <button
          onClick={() => { onNavigate?.(); openAuth(); }}
          className="flex w-full items-center justify-center rounded-lg border border-green-accent bg-green-dark px-3 py-2 text-sm font-medium text-green-accent hover:opacity-90 transition-opacity"
        >
          Sign in / Sign up
        </button>
      );
    }
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2 px-3 py-1">
          {isPro && (
            <span className="text-[9px] uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-1.5 py-0.5">
              Pro
            </span>
          )}
          <span className="text-xs text-text-muted truncate">{user.email ?? 'Account'}</span>
        </div>
        <Link href="/account" onClick={onNavigate} className={rowCls}>Account settings</Link>
        <Link href="/watchlist" onClick={onNavigate} className={rowCls}>My watchlist</Link>
        {isPro && (
          <button
            onClick={async () => { onNavigate?.(); try { await openBillingPortal(getToken); } catch {} }}
            className={rowCls}
          >
            Manage plan
          </button>
        )}
        <button
          onClick={async () => { onNavigate?.(); await signOut(); }}
          className={rowCls}
        >
          Sign out
        </button>
      </div>
    );
  }

  // ── Desktop bar variant (default) ───────────────────────────────────────────────────
  if (!user) {
    return (
      <button
        onClick={openAuth}
        className="inline-flex items-center rounded-lg border border-green-accent bg-green-accent px-3 py-1 text-xs font-medium text-bg-primary hover:opacity-90 transition-opacity"
      >
        Sign up
      </button>
    );
  }

  const label = user.email ?? 'Account';
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1.5 rounded-lg border border-border-default bg-bg-primary px-3 py-1 text-xs text-text-secondary hover:text-text-primary transition-colors"
      >
        {isPro && (
          <span className="text-[9px] uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-1.5 py-0.5">
            Pro
          </span>
        )}
        <span className="max-w-[12ch] truncate">{label}</span>
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-48 rounded-lg border border-border-default bg-bg-secondary shadow-lg p-1 z-50">
          <Link
            href="/account"
            onClick={() => setOpen(false)}
            className="block w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-bg-primary rounded"
          >
            Account settings
          </Link>
          <Link
            href="/watchlist"
            onClick={() => setOpen(false)}
            className="block w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-bg-primary rounded"
          >
            My watchlist
          </Link>
          {isPro && (
            <button
              onClick={async () => { setOpen(false); try { await openBillingPortal(getToken); } catch {} }}
              className="block w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-bg-primary rounded"
            >
              Manage plan
            </button>
          )}
          <button
            onClick={async () => { setOpen(false); await signOut(); }}
            className="block w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-bg-primary rounded"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
