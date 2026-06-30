/** One loading-skeleton primitive for list/table views — replaces the ad-hoc
 *  `[...Array(n)].map(() => <div className="h-NN bg-bg-secondary rounded animate-pulse" />)` loops
 *  scattered across pages, so "loading" reads the same everywhere (and the watch list stops showing
 *  a bare "Loading…" line). Pairs with EmptyState for the "nothing here" case. */
export function SkeletonList({
  rows = 5,
  height = 'h-12',
  className = '',
}: {
  rows?: number;
  /** Tailwind height class per row — match the rendered row/card height (e.g. h-12, h-24, h-28). */
  height?: string;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`} aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={`${height} animate-pulse rounded-card bg-bg-secondary`} />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}
