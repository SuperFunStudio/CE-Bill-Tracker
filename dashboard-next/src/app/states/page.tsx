'use client';
import { useMemo } from 'react';
import Link from 'next/link';
import { useBills } from '@/hooks/useBills';
import { STATE_NAMES } from '@/lib/utils';

export default function StatesPage() {
  const { data: bills = [], isLoading } = useBills({ epr_relevant: true, limit: 500 });

  const ranking = useMemo(() => {
    const counts: Record<string, number> = {};
    const enacted: Record<string, number> = {};
    bills.forEach(b => {
      counts[b.state] = (counts[b.state] ?? 0) + 1;
      if (b.status === 'enacted') enacted[b.state] = (enacted[b.state] ?? 0) + 1;
    });
    return Object.keys(STATE_NAMES)
      .map(abbr => ({ abbr, name: STATE_NAMES[abbr], count: counts[abbr] ?? 0, enacted: enacted[abbr] ?? 0 }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }, [bills]);

  const active = ranking.filter(r => r.count > 0);
  const dormant = ranking.filter(r => r.count === 0);

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <header className="text-center pt-1 pb-4 border-b-2 border-text-primary/80">
        <div className="border-t border-b border-text-primary/30 py-3">
          <h1 className="font-serif uppercase tracking-[0.06em] text-2xl sm:text-3xl text-text-primary">State Standings</h1>
        </div>
        <p className="mt-2 font-serif italic text-text-secondary text-sm">
          Who&rsquo;s winning the Battle of the Bills
        </p>
      </header>

      <Link href="/" className="inline-block text-sm text-green-accent hover:underline">&larr; Back to the front page</Link>

      {isLoading ? (
        <div className="space-y-2">{[...Array(8)].map((_, i) => <div key={i} className="h-9 bg-bg-secondary rounded animate-pulse" />)}</div>
      ) : (
        <ol className="rounded-lg border border-border-default overflow-hidden">
          <li className="flex items-center justify-between bg-bg-secondary px-4 py-2 text-xs uppercase tracking-wide text-text-muted">
            <span>Rank · State</span>
            <span className="flex gap-6"><span>Enacted</span><span>Bills</span></span>
          </li>
          {active.map((r, i) => (
            <li
              key={r.abbr}
              className="flex items-center justify-between px-4 py-2 border-t border-border-default hover:bg-bg-secondary/60"
            >
              <div className="flex items-baseline gap-3">
                <span className="font-serif text-text-muted w-6 text-right tabular-nums">{i + 1}</span>
                <span className="font-mono font-bold text-green-accent w-8">{r.abbr}</span>
                <span className="text-text-secondary text-sm">{r.name}</span>
              </div>
              <span className="flex items-baseline gap-6">
                <span className="text-text-muted text-sm tabular-nums w-10 text-right">{r.enacted || '—'}</span>
                <span className="font-serif text-text-primary tabular-nums w-10 text-right">{r.count}</span>
              </span>
            </li>
          ))}
        </ol>
      )}

      {dormant.length > 0 && (
        <section className="border-t border-border-default pt-5">
          <h2 className="font-serif text-xl text-text-primary mb-1">On the bench</h2>
          <p className="text-text-muted text-sm mb-3">
            {dormant.length} states have no tracked circularity legislation yet — wide-open territory.
          </p>
          <div className="flex flex-wrap gap-2">
            {dormant.map(r => (
              <span
                key={r.abbr}
                title={r.name}
                className="font-mono text-xs border border-border-default rounded px-2 py-1 text-text-muted"
              >
                {r.abbr}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
