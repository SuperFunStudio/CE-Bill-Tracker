'use client';
import Link from 'next/link';
import { MAP_METRIC, fmtCount } from '@/lib/mapScale';

/**
 * Static top-10 under the map — replaces the auto-scrolling ranking ticker that used to sit above
 * everything. Same data (enacted laws, region-aware: umbrella regions / US states / EU member states),
 * but readable at a glance, with counts, and out of the way of the table. Hovering a row previews it
 * on the map; clicking filters the page to it.
 */
export function JurisdictionTopList({
  label, data, nameOf, onSelect, onHover, selected, restHref,
}: {
  label: string;
  /** Code → enacted-law count. */
  data: Record<string, number>;
  nameOf: (code: string) => string;
  onSelect?: (code: string) => void;
  onHover?: (code: string | null) => void;
  selected?: string | null;
  restHref?: string;
}) {
  const ranked = Object.entries(data)
    .filter(([, c]) => c > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  // A one-entry "ranking" (a lone country in focus) says nothing the summary above doesn't.
  if (ranked.length < 2) return null;
  const max = ranked[0][1];

  return (
    <section aria-label={label}>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <h2 className="field-label">
          {label} <span className="normal-case tracking-normal">· {MAP_METRIC}</span>
        </h2>
        {restHref && <Link href={restHref} className="link-arrow text-xs">View all</Link>}
      </div>
      <ol className="divide-y divide-border-default border-y border-border-default" onMouseLeave={() => onHover?.(null)}>
        {ranked.map(([code, n], i) => {
          const on = selected === code;
          return (
            <li key={code}>
              <button
                type="button"
                onClick={() => onSelect?.(code)}
                onMouseEnter={() => onHover?.(code)}
                onFocus={() => onHover?.(code)}
                aria-pressed={on}
                className={`group relative flex w-full items-center gap-3 px-1 py-1.5 text-left text-sm transition-colors hover:bg-bg-secondary ${on ? 'bg-bg-secondary' : ''}`}
              >
                <span className="w-5 shrink-0 text-right text-xs text-text-muted tabular-nums">{i + 1}</span>
                <span className={`flex-1 truncate ${on ? 'font-semibold text-text-primary' : 'text-text-primary'}`}>
                  {nameOf(code)}
                </span>
                {/* A thin magnitude bar: data, so it may carry the accent. */}
                <span className="hidden w-16 sm:block" aria-hidden>
                  <span
                    className="block h-1 rounded-full bg-green-accent/70"
                    style={{ width: `${Math.max(6, (n / max) * 100)}%` }}
                  />
                </span>
                <span className="w-10 shrink-0 text-right text-text-secondary tabular-nums">{fmtCount(n)}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
