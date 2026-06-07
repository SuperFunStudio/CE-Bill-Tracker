'use client';
import Link from 'next/link';
import { useRef } from 'react';

/**
 * "Top States" leaderboard line, styled like a subheading under the masthead.
 * Shows every ranked state in a full-width, horizontally scrollable strip.
 * Drag (or wheel/trackpad) to scroll; a fixed label and "The rest →" link
 * bookend the scroller so neither gets clipped.
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

  const scroller = useRef<HTMLDivElement>(null);
  // Track an in-progress drag so a drag-release doesn't fire the underlying button click.
  const drag = useRef({ active: false, startX: 0, startLeft: 0, moved: false });

  if (ranked.length === 0) return null;

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = scroller.current;
    if (!el) return;
    drag.current = { active: true, startX: e.clientX, startLeft: el.scrollLeft, moved: false };
    el.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = scroller.current;
    if (!el || !drag.current.active) return;
    const dx = e.clientX - drag.current.startX;
    if (Math.abs(dx) > 3) drag.current.moved = true;
    el.scrollLeft = drag.current.startLeft - dx;
  };

  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = scroller.current;
    if (el?.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    drag.current.active = false;
  };

  return (
    <div className="flex items-center gap-3 border-y border-text-primary/20">
      <span className="shrink-0 pl-1 font-serif text-xs uppercase tracking-wider text-green-accent">
        Top States
      </span>
      <div
        ref={scroller}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className="flex flex-1 select-none cursor-grab items-center overflow-x-auto py-2 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden active:cursor-grabbing"
      >
        {ranked.map(([abbr], i) => (
          <button
            key={abbr}
            onClick={() => {
              // Suppress the click that ends a drag gesture.
              if (drag.current.moved) return;
              onStateClick?.(abbr);
            }}
            className="inline-flex items-baseline gap-1.5 px-4 whitespace-nowrap hover:text-green-accent transition-colors"
          >
            <span className="text-text-muted">{i + 1}.</span>
            <span className="font-mono font-bold text-text-primary">{abbr}</span>
          </button>
        ))}
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
