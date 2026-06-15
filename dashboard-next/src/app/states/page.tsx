'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useBills } from '@/hooks/useBills';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { STATE_NAMES } from '@/lib/utils';

/**
 * Pipeline stages, ordered from earliest to latest. A bill's momentum is how far
 * right it has reached. Opacity climbs with progress so a more-saturated bar reads
 * as "more advanced," independent of how many bills a state has filed.
 */
const STAGES = [
  { key: 'introduced', label: 'Introduced', statuses: ['introduced'], opacity: 0.25 },
  { key: 'committee', label: 'In committee', statuses: ['in_committee'], opacity: 0.5 },
  { key: 'advancing', label: 'Advancing', statuses: ['passed_chamber', 'passed', 'enrolled'], opacity: 0.75 },
  { key: 'enacted', label: 'Enacted', statuses: ['enacted', 'signed'], opacity: 1 },
] as const;

type StageKey = (typeof STAGES)[number]['key'];

const STAGE_OF: Record<string, StageKey> = Object.fromEntries(
  STAGES.flatMap(s => s.statuses.map(st => [st, s.key])),
);

type SortMode = 'active' | 'enacted';

export default function StatesPage() {
  const { data: bills = [], isLoading } = useBills({ epr_relevant: true, limit: 5000 });
  const [sortBy, setSortBy] = useState<SortMode>('active');

  const ranking = useMemo(() => {
    const blank = () => ({ introduced: 0, committee: 0, advancing: 0, enacted: 0 } as Record<StageKey, number>);
    const stages: Record<string, Record<StageKey, number>> = {};
    const counts: Record<string, number> = {};
    bills.forEach(b => {
      counts[b.state] = (counts[b.state] ?? 0) + 1;
      const stage = STAGE_OF[(b.status ?? '').toLowerCase()];
      if (stage) (stages[b.state] ??= blank())[stage] += 1;
    });
    return Object.keys(STATE_NAMES)
      .map(abbr => {
        const s = stages[abbr] ?? blank();
        // Bills still alive in the pipeline (excludes failed/vetoed) — the basis for the bar.
        const inMotion = s.introduced + s.committee + s.advancing + s.enacted;
        return { abbr, name: STATE_NAMES[abbr], count: counts[abbr] ?? 0, inMotion, ...s };
      })
      .sort((a, b) =>
        sortBy === 'enacted'
          ? b.enacted - a.enacted || b.count - a.count || a.name.localeCompare(b.name)
          : b.count - a.count || a.name.localeCompare(b.name),
      );
  }, [bills, sortBy]);

  const active = ranking.filter(r => r.count > 0);
  const dormant = ranking.filter(r => r.count === 0);

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <GazetteHeader title="State Standings" subtitle="Who’s winning the Battle of the Bills" />

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link href="/" className="text-sm text-green-accent hover:underline">&larr; Back to the front page</Link>
        <div className="inline-flex rounded-md border border-border-default overflow-hidden text-xs">
          {([['active', 'Most active'], ['enacted', 'Most enacted']] as const).map(([mode, label]) => (
            <button
              key={mode}
              onClick={() => setSortBy(mode)}
              aria-pressed={sortBy === mode}
              className={`px-3 py-1.5 font-mono uppercase tracking-wide transition-colors ${
                sortBy === mode
                  ? 'bg-green-accent text-bg-primary'
                  : 'bg-bg-secondary text-text-muted hover:text-text-primary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <p className="text-text-muted text-sm -mt-2">
        {sortBy === 'enacted'
          ? 'Ranked by bills signed into law. The bar shows each state’s momentum — how far its bills have advanced.'
          : 'Ranked by total bills introduced. The bar shows each state’s momentum — how far its bills have advanced.'}
      </p>

      {/* Momentum legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
        {STAGES.map(s => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block w-3 h-3 rounded-sm"
              style={{ backgroundColor: `rgb(var(--green-accent) / ${s.opacity})` }}
            />
            {s.label}
          </span>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">{[...Array(8)].map((_, i) => <div key={i} className="h-9 bg-bg-secondary rounded animate-pulse" />)}</div>
      ) : (
        <ol className="rounded-lg border border-border-default overflow-hidden">
          <li className="flex items-center gap-3 bg-bg-secondary px-4 py-2 text-xs uppercase tracking-wide text-text-muted">
            <span className="w-6 text-right">#</span>
            <span className="w-8">St</span>
            <span className="flex-1">Momentum</span>
            <span className="w-16 text-right">Enacted</span>
            <span className="w-12 text-right">Bills</span>
          </li>
          {active.map((r, i) => (
            <li key={r.abbr} className="border-t border-border-default">
              <Link
                href={`/states/${r.abbr.toLowerCase()}/`}
                className="flex items-center gap-3 px-4 py-2 hover:bg-bg-secondary/60"
              >
                <span className="font-serif text-text-muted w-6 text-right tabular-nums">{i + 1}</span>
                <span className="font-mono font-bold text-green-accent w-8" title={r.name}>{r.abbr}</span>
                <span className="flex-1 min-w-0">
                <span className="flex h-2.5 w-full rounded-sm overflow-hidden bg-bg-tertiary" title={momentumTitle(r)}>
                  {STAGES.map(s =>
                    r[s.key] > 0 ? (
                      <span
                        key={s.key}
                        style={{
                          width: `${(r[s.key] / r.inMotion) * 100}%`,
                          backgroundColor: `rgb(var(--green-accent) / ${s.opacity})`,
                        }}
                      />
                    ) : null,
                  )}
                </span>
              </span>
                <span className="text-text-muted text-sm tabular-nums w-16 text-right">{r.enacted || '—'}</span>
                <span className="font-serif text-text-primary tabular-nums w-12 text-right">{r.count}</span>
              </Link>
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
              <Link
                key={r.abbr}
                href={`/states/${r.abbr.toLowerCase()}/`}
                title={r.name}
                className="font-mono text-xs border border-border-default rounded px-2 py-1 text-text-muted hover:text-text-primary hover:border-text-muted"
              >
                {r.abbr}
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function momentumTitle(r: Record<StageKey, number> & { name: string }): string {
  const parts = STAGES.filter(s => r[s.key] > 0).map(s => `${r[s.key]} ${s.label.toLowerCase()}`);
  return parts.length ? `${r.name}: ${parts.join(', ')}` : r.name;
}
