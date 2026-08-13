'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

const STORAGE_KEY = 'botb_federal_watch_dismissed';

/**
 * Pithy, dismissible federal-preemption notice. "Learn more" links to Federal Actions — the page that
 * actually tracks the Oregon preemption case, its trial date, and the federal register actions on
 * watch (it used to land on the Upcoming Deadlines calendar, which says nothing about the case). The
 * ✕ hides it (remembered).
 */
export function FederalWatchBanner({ highRiskCount = 0 }: { highRiskCount?: number }) {
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    setHidden(localStorage.getItem(STORAGE_KEY) === '1');
  }, []);

  if (hidden) return null;

  function dismiss() {
    localStorage.setItem(STORAGE_KEY, '1');
    setHidden(true);
  }

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-400 bg-amber-100 px-4 py-2.5 text-amber-900 dark:border-amber-700/60 dark:bg-amber-900/40 dark:text-amber-200">
      <div className="flex items-center gap-2 text-sm min-w-0">
        <span aria-hidden className="shrink-0">⚖️</span>
        <span className="truncate sm:whitespace-normal">
          The wildcard: an Oregon court case could let judges strike down state packaging laws
          nationwide — a ruling is expected this August{highRiskCount > 0 ? ` (${highRiskCount} federal actions on watch)` : ''}.
        </span>
        <Link
          href="/federal"
          className="shrink-0 font-medium underline underline-offset-2 hover:no-underline whitespace-nowrap"
        >
          Learn more →
        </Link>
      </div>
      <button
        onClick={dismiss}
        aria-label="Dismiss"
        className="shrink-0 -mr-1 rounded p-1 text-lg leading-none opacity-70 hover:opacity-100 transition-opacity"
      >
        ✕
      </button>
    </div>
  );
}
