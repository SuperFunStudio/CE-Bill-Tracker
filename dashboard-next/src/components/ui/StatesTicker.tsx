'use client';
import Link from 'next/link';

/**
 * "Top States" leaderboard line, styled like a subheading under the masthead.
 * Auto-scrolls like a stock ticker (pauses on hover); tap a state to filter by it.
 * A fixed label and "The rest →" link bookend the moving strip so neither clips.
 */
export function StatesTicker({
  data,
  onStateClick,
}: {
  data: Record<string, number>;
  onStateClick?: (abbr: string) => void;
}) {
  const ranked = Object.entries(data)
    .filter(([, c]) => c > 0)
    .sort((a, b) => b[1] - a[1]);

  if (ranked.length === 0) return null;

  // Scale the duration with the number of states so the scroll speed stays
  // roughly constant regardless of how many states are in the list.
  const durationSec = Math.max(20, ranked.length * 3);

  // Duplicate the list so the -50% marquee translation loops seamlessly.
  const loop = [...ranked, ...ranked];

  return (
    <div className="flex items-center gap-3 border-y border-text-primary/20">
      <span className="shrink-0 pl-1 font-serif text-xs uppercase tracking-wider text-green-accent">
        Top States
      </span>
      {/* group → pause on hover; overflow-hidden clips the looping track */}
      <div className="group relative flex-1 overflow-hidden py-2">
        <div
          className="flex w-max animate-marquee group-hover:[animation-play-state:paused]"
          style={{ animationDuration: `${durationSec}s` }}
        >
          {loop.map(([abbr], i) => (
            <button
              key={`${abbr}-${i}`}
              onClick={() => onStateClick?.(abbr)}
              aria-hidden={i >= ranked.length}
              tabIndex={i >= ranked.length ? -1 : 0}
              className="inline-flex items-baseline gap-1.5 px-4 whitespace-nowrap hover:text-green-accent transition-colors"
            >
              <span className="text-text-muted">{(i % ranked.length) + 1}.</span>
              <span className="font-mono font-bold text-text-primary">{abbr}</span>
            </button>
          ))}
        </div>
      </div>
      <Link
        href="/states"
        className="shrink-0 pr-1 text-xs text-green-accent hover:underline whitespace-nowrap"
      >
        The rest &rarr;
      </Link>
    </div>
  );
}
