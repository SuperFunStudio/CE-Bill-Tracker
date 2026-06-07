'use client';
import Link from 'next/link';

/**
 * "Top States" leaderboard line, styled like a subheading under the masthead.
 * The current top 5 loop continuously (slow marquee, pauses on hover); fixed label
 * and "The rest →" link bookend the scroll so neither gets clipped.
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

  const top5 = ranked.slice(0, 5);
  const REPEAT = 5; // repeat the top-5 enough to fill wide screens for a seamless loop

  const copy = (prefix: string) =>
    Array.from({ length: REPEAT }).flatMap((_, r) =>
      top5.map(([abbr], i) => (
        <button
          key={`${prefix}-${r}-${i}`}
          onClick={() => onStateClick?.(abbr)}
          className="inline-flex items-baseline gap-1.5 px-5 whitespace-nowrap hover:text-green-accent transition-colors"
        >
          <span className="text-text-muted">{i + 1}.</span>
          <span className="font-mono font-bold text-text-primary">{abbr}</span>
        </button>
      )),
    );

  return (
    <div className="flex items-center gap-3 border-y border-text-primary/20">
      <span className="shrink-0 pl-1 font-serif text-xs uppercase tracking-wider text-green-accent">
        Top States
      </span>
      <div className="flex-1 overflow-hidden group">
        <div
          className="flex w-max animate-marquee py-2 group-hover:[animation-play-state:paused]"
          style={{ animationDuration: '70s' }}
        >
          {copy('a')}
          {copy('b')}
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
