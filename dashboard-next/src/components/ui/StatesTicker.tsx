'use client';
import Link from 'next/link';

/**
 * Ranked "leaderboard" ticker under the masthead — auto-scrolls like a stock ticker (pauses on
 * hover). Region-aware: it renders US states, EU member states, or the umbrella regions depending on
 * the global region selection (the caller decides the label, the entries, and what a tap does).
 * A fixed label and optional "The rest →" link bookend the moving strip so neither clips.
 */
export function StatesTicker({
  label = 'Top States',
  data,
  onSelect,
  restHref,
}: {
  /** Heading shown at the left ("Top States" / "Top Member States" / "Top Regions"). */
  label?: string;
  /** Entry code (US state abbr / region code) → count. */
  data: Record<string, number>;
  /** Tap handler — filter by a US state, or drill into a region. */
  onSelect?: (code: string) => void;
  /** Optional "The rest →" destination (only meaningful for the US states list). */
  restHref?: string;
}) {
  const ranked = Object.entries(data)
    .filter(([, c]) => c > 0)
    .sort((a, b) => b[1] - a[1]);

  if (ranked.length === 0) return null;

  // Scale the duration with the number of entries so the scroll speed stays
  // roughly constant regardless of how many are in the list.
  const durationSec = Math.max(20, ranked.length * 3);

  // Duplicate the list so the -50% marquee translation loops seamlessly.
  const loop = [...ranked, ...ranked];

  return (
    <div className="flex items-center gap-3 border-y border-text-primary/20">
      <span className="shrink-0 pl-1 font-serif text-xs uppercase tracking-wider text-green-accent">
        {label}
      </span>
      {/* group → pause on hover; overflow-hidden clips the looping track */}
      <div className="group relative flex-1 overflow-hidden py-2">
        <div
          className="flex w-max animate-marquee group-hover:[animation-play-state:paused]"
          style={{ animationDuration: `${durationSec}s` }}
        >
          {loop.map(([code], i) => (
            <button
              key={`${code}-${i}`}
              onClick={() => onSelect?.(code)}
              aria-hidden={i >= ranked.length}
              tabIndex={i >= ranked.length ? -1 : 0}
              className="inline-flex items-baseline gap-1.5 px-4 whitespace-nowrap hover:text-green-accent transition-colors"
            >
              <span className="text-text-muted">{(i % ranked.length) + 1}.</span>
              <span className="font-mono font-bold text-text-primary">{code}</span>
            </button>
          ))}
        </div>
      </div>
      {restHref && (
        <Link
          href={restHref}
          className="shrink-0 pr-1 text-xs text-green-accent hover:underline whitespace-nowrap"
        >
          The rest &rarr;
        </Link>
      )}
    </div>
  );
}
