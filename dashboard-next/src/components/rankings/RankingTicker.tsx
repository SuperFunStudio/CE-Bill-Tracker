'use client';
import Link from 'next/link';
import { track } from '@/lib/analytics';

export type TickerEntry = { code: string; name: string; href: string; count: number };

/**
 * The Rankings page's headline strip: ranked regions sliding past like a stock ticker. Every entry is a
 * link to that region's profile — the point of the page is to send readers into the stat pages, so the
 * ranking is a doorway, not a destination. Pauses on hover/focus; stands still (and scrolls by hand)
 * under reduced motion. See .rank-marquee in globals.css.
 */
export function RankingTicker({ entries, controls }: { entries: TickerEntry[]; controls?: React.ReactNode }) {
  if (entries.length === 0) return null;
  // Constant speed whatever the length: ~3s an entry.
  const durationSec = Math.max(24, entries.length * 3);
  // The list twice, so the -50% slide loops seamlessly; the copy is hidden from assistive tech.
  const loop = [...entries, ...entries];

  return (
    <div className="flex items-center gap-3 border-y border-text-primary/20">
      {controls && <div className="shrink-0 py-1.5">{controls}</div>}
      <div className="rank-marquee-wrap relative min-w-0 flex-1 overflow-hidden py-2.5">
        <ol className="rank-marquee flex w-max" style={{ animationDuration: `${durationSec}s` }}>
          {loop.map((e, i) => {
            const copy = i >= entries.length;
            return (
              <li key={`${e.code}-${i}`} aria-hidden={copy || undefined}>
                <Link
                  href={e.href}
                  tabIndex={copy ? -1 : undefined}
                  onClick={() => track('cta_click', { entry_source: 'rankings_ticker', region: e.code })}
                  className="inline-flex items-baseline gap-1.5 whitespace-nowrap px-4 transition-colors hover:text-green-accent"
                >
                  <span className="text-sm text-text-muted tabular-nums">{(i % entries.length) + 1}.</span>
                  <span className="font-serif text-text-primary">{e.name}</span>
                  <span className="text-sm font-semibold tabular-nums text-green-accent">{e.count}</span>
                </Link>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
