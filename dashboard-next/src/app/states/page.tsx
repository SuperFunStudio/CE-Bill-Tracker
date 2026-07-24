'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useBills } from '@/hooks/useBills';
import { useRegion } from '@/components/layout/RegionContext';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { STATE_NAMES } from '@/lib/utils';
import { EU_MEMBERS, jurisdictionDisplayName } from '@/lib/jurisdictions';

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

const ENACTED = new Set(['enacted', 'signed']);

type SortMode = 'active' | 'enacted';

// Which board to show, derived from the global region selection. An EXPLICIT US selection gets the
// deep US-state momentum board; an EU/member selection gets the EU board; everything else — the
// default "all regions" landing and any lone foreign selection — gets the flagship two-column
// Standings board (US states next to the world's nations).
export default function StatesPage() {
  const { regions } = useRegion();
  if (regions.includes('US')) return <UsStandings />;
  if (regions.includes('EU') || regions.some(r => r in EU_MEMBERS)) return <RegionStandings />;
  return <WorldStandings />;
}

/** US-state momentum leaderboard — the original "State Standings" board. */
function UsStandings() {
  const { data: bills = [], isLoading, isError, refetch } = useBills({ ce_relevant: true, limit: 5000 });
  const [sortBy, setSortBy] = useState<SortMode>('active');

  const ranking = useMemo(() => {
    const blank = () => ({ introduced: 0, committee: 0, advancing: 0, enacted: 0 } as Record<StageKey, number>);
    const stages: Record<string, Record<StageKey, number>> = {};
    const counts: Record<string, number> = {};
    bills.forEach(b => {
      if (b.region !== 'US') return;
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
      <GazetteHeader title="State Standings" subtitle="Who’s winning the Atlas Circular" />

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

      <p className="text-text-secondary text-body -mt-2">
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

      {isError ? (
        <div className="surface-inset px-4 py-8 text-center space-y-2">
          <p className="text-body text-text-primary">Couldn&rsquo;t load state standings.</p>
          <button onClick={() => refetch()} className="text-sm text-green-accent hover:underline">
            Try again
          </button>
        </div>
      ) : isLoading ? (
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
                href={`/jurisdictions/us/${r.abbr.toLowerCase()}/`}
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
          <p className="text-text-secondary text-body mb-3">
            {dormant.length} states have no tracked circularity legislation yet — wide-open territory.
          </p>
          <div className="flex flex-wrap gap-2">
            {dormant.map(r => (
              <Link
                key={r.abbr}
                href={`/jurisdictions/us/${r.abbr.toLowerCase()}/`}
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

/**
 * EU board — EU-wide act + member countries. This corpus is enacted-heavy national law with no
 * introduced→enacted funnel, so we rank by bill count and show an enacted-share bar instead of the
 * US momentum stages. (The world/all-regions view is the two-column WorldStandings below.)
 */
function RegionStandings() {
  const { data: bills = [], isLoading, isError, refetch } = useBills({ ce_relevant: true, limit: 5000 });

  const rows = useMemo(() => {
    const groups: Record<string, { region: string; code: string; count: number; enacted: number }> = {};
    for (const b of bills) {
      if (b.region === 'US') continue;
      const isEuWide = b.region === 'EU';
      const isMember = b.region in EU_MEMBERS;
      if (!(isEuWide || isMember)) continue;
      const key = isEuWide ? 'EU' : b.region;
      const g = (groups[key] ??= { region: key, code: key, count: 0, enacted: 0 });
      g.count += 1;
      if (ENACTED.has((b.status ?? '').toLowerCase())) g.enacted += 1;
    }
    return Object.values(groups)
      .map(g => ({ ...g, name: jurisdictionDisplayName(g.region, g.code) }))
      .sort((a, b) => b.count - a.count || b.enacted - a.enacted || a.name.localeCompare(b.name));
  }, [bills]);

  const title = 'Member State Standings';
  const subtitle = 'Circular-economy law across the European Union';

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <GazetteHeader title={title} subtitle={subtitle} />

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link href="/" className="text-sm text-green-accent hover:underline">&larr; Back to the front page</Link>
      </div>

      <p className="text-text-secondary text-body -mt-2">
        Ranked by tracked laws. The bar shows the share already enacted — national circular-economy law
        is mostly in force rather than moving through a US-style pipeline.
      </p>

      {isError ? (
        <div className="surface-inset px-4 py-8 text-center space-y-2">
          <p className="text-body text-text-primary">Couldn&rsquo;t load standings.</p>
          <button onClick={() => refetch()} className="text-sm text-green-accent hover:underline">Try again</button>
        </div>
      ) : isLoading ? (
        <div className="space-y-2">{[...Array(6)].map((_, i) => <div key={i} className="h-9 bg-bg-secondary rounded animate-pulse" />)}</div>
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-border-default bg-bg-secondary px-4 py-6 text-body text-text-secondary text-center">
          No tracked laws in this region yet.
        </p>
      ) : (
        <ol className="rounded-lg border border-border-default overflow-hidden">
          <li className="flex items-center gap-3 bg-bg-secondary px-4 py-2 text-xs uppercase tracking-wide text-text-muted">
            <span className="w-6 text-right">#</span>
            <span className="w-8">Jx</span>
            <span className="flex-1">Jurisdiction</span>
            <span className="w-16 text-right">Enacted</span>
            <span className="w-12 text-right">Laws</span>
          </li>
          {rows.map((r, i) => (
            <li key={`${r.region}/${r.code}`} className="border-t border-border-default">
              <Link
                href={`/jurisdictions/${r.region.toLowerCase()}/${r.code.toLowerCase()}/`}
                className="flex items-center gap-3 px-4 py-2 hover:bg-bg-secondary/60"
              >
                <span className="font-serif text-text-muted w-6 text-right tabular-nums">{i + 1}</span>
                <span className="font-mono font-bold text-green-accent w-8" title={r.name}>{r.code}</span>
                <span className="flex-1 min-w-0 flex items-center gap-2">
                  <span className="truncate text-sm text-text-primary">{r.name}</span>
                  <span className="flex-1 h-2 rounded-sm overflow-hidden bg-bg-tertiary min-w-8" title={`${r.enacted} of ${r.count} enacted`}>
                    <span
                      className="block h-full"
                      style={{ width: `${r.count ? (r.enacted / r.count) * 100 : 0}%`, backgroundColor: 'rgb(var(--green-accent))' }}
                    />
                  </span>
                </span>
                <span className="text-text-muted text-sm tabular-nums w-16 text-right">{r.enacted || '—'}</span>
                <span className="font-serif text-text-primary tabular-nums w-12 text-right">{r.count}</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** One row shared by both Standings columns: rank, code, name (+ optional tag), enacted-share bar, tallies. */
function StandingRow({ rank, code, name, href, enacted, count, tag }: {
  rank: number; code: string; name: string; href: string; enacted: number; count: number; tag?: string;
}) {
  const share = count ? (enacted / count) * 100 : 0;
  return (
    <li className="border-t border-border-default first:border-t-0">
      <Link href={href} className="flex items-center gap-3 px-3 py-2 hover:bg-bg-secondary/60">
        <span className="font-serif text-text-muted w-5 text-right tabular-nums">{rank}</span>
        <span className="font-mono font-bold text-green-accent w-8 shrink-0" title={name}>{code}</span>
        <span className="flex-1 min-w-0 flex items-center gap-2">
          <span className="truncate text-sm text-text-primary">{name}</span>
          {tag && (
            <span className="shrink-0 text-[10px] uppercase tracking-wide text-text-muted border border-border-default rounded px-1 leading-4">
              {tag}
            </span>
          )}
          <span className="flex-1 h-2 rounded-sm overflow-hidden bg-bg-tertiary min-w-6" title={`${enacted} of ${count} enacted`}>
            <span className="block h-full" style={{ width: `${share}%`, backgroundColor: 'rgb(var(--green-accent))' }} />
          </span>
        </span>
        <span className="text-text-muted text-xs tabular-nums w-10 text-right">{enacted || '—'}</span>
        <span className="font-serif text-text-primary tabular-nums w-8 text-right">{count}</span>
      </Link>
    </li>
  );
}

/**
 * The flagship two-column leaderboard: US states ranked next to the world's nations. This is where
 * the United States is scored *fairly* on two axes at once — its states dominate the left column,
 * while the US-as-a-nation (its FEDERAL law alone) sits low in the right column, because circular-
 * economy law in America is a state-level story with almost no federal analog. Inclusive of every
 * country we track.
 *
 * Sub-national rows are first-class only for the US today: foreign provinces (CA/AU) collapse to their
 * country code in the data (see foreign_id in app/ingestion/foreign.py), so decomposing them into the
 * left column is a v2. The US-federal row is scored on bills with state == "US" (agency rulemakings
 * live in the separate federal_actions table and are not counted here).
 */
function WorldStandings() {
  const { setRegions } = useRegion();
  const { data: bills = [], isLoading, isError, refetch } = useBills({ ce_relevant: true, limit: 5000 });

  const { states, nations } = useMemo(() => {
    const stCount: Record<string, number> = {};
    const stEnacted: Record<string, number> = {};
    // Seed the US-federal row so America is always visible among the nations — the whole point is that
    // it ranks LOW there even as its states top the other column.
    const nat: Record<string, { region: string; code: string; name: string; count: number; enacted: number }> = {
      US: { region: 'US', code: 'US', name: 'United States', count: 0, enacted: 0 },
    };
    for (const b of bills) {
      const isEnacted = ENACTED.has((b.status ?? '').toLowerCase());
      if (b.region === 'US') {
        if (b.state && b.state !== 'US') {
          stCount[b.state] = (stCount[b.state] ?? 0) + 1;
          if (isEnacted) stEnacted[b.state] = (stEnacted[b.state] ?? 0) + 1;
        } else {
          nat.US.count += 1;
          if (isEnacted) nat.US.enacted += 1;
        }
        continue;
      }
      // Foreign / EU: region is the country/bloc bucket (region == state for foreign national law).
      const g = (nat[b.region] ??= { region: b.region, code: b.region, name: jurisdictionDisplayName(b.region, b.region), count: 0, enacted: 0 });
      g.count += 1;
      if (isEnacted) g.enacted += 1;
    }
    const states = Object.keys(STATE_NAMES)
      .map(abbr => ({ abbr, name: STATE_NAMES[abbr], count: stCount[abbr] ?? 0, enacted: stEnacted[abbr] ?? 0 }))
      .filter(r => r.count > 0)
      .sort((a, b) => b.count - a.count || b.enacted - a.enacted || a.name.localeCompare(b.name));
    const nations = Object.values(nat)
      .sort((a, b) => b.count - a.count || b.enacted - a.enacted || a.name.localeCompare(b.name));
    return { states, nations };
  }, [bills]);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <GazetteHeader title="Standings" subtitle="US states next to the world’s nations" />

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link href="/" className="text-sm text-green-accent hover:underline">&larr; Back to the front page</Link>
      </div>

      <p className="text-text-secondary text-body -mt-2">
        Two leaderboards, side by side. On the left, US states — the only federation whose sub-national
        law we track individually. On the right, nations ranked by tracked law, with the United States
        scored on its <em>federal</em> law alone. America leads by state and lags by nation: the same
        country sits near the top of one column and the bottom of the other.
      </p>

      {isError ? (
        <div className="surface-inset px-4 py-8 text-center space-y-2">
          <p className="text-body text-text-primary">Couldn&rsquo;t load standings.</p>
          <button onClick={() => refetch()} className="text-sm text-green-accent hover:underline">Try again</button>
        </div>
      ) : isLoading ? (
        <div className="grid gap-8 md:grid-cols-2">
          {[0, 1].map(col => (
            <div key={col} className="space-y-2">{[...Array(6)].map((_, i) => <div key={i} className="h-9 bg-bg-secondary rounded animate-pulse" />)}</div>
          ))}
        </div>
      ) : (
        <div className="grid gap-8 md:grid-cols-2">
          {/* Left: US states */}
          <section className="space-y-3">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-serif text-xl text-text-primary">State standings</h2>
              <button onClick={() => setRegions(['US'])} className="text-xs text-green-accent hover:underline whitespace-nowrap">
                Full momentum board &rarr;
              </button>
            </div>
            <ol className="rounded-lg border border-border-default overflow-hidden">
              <li className="flex items-center gap-3 bg-bg-secondary px-3 py-2 text-xs uppercase tracking-wide text-text-muted">
                <span className="w-5 text-right">#</span>
                <span className="w-8">St</span>
                <span className="flex-1">Enacted share</span>
                <span className="w-10 text-right">Enac.</span>
                <span className="w-8 text-right">Bills</span>
              </li>
              {states.map((r, i) => (
                <StandingRow key={r.abbr} rank={i + 1} code={r.abbr} name={r.name}
                  href={`/jurisdictions/us/${r.abbr.toLowerCase()}/`} enacted={r.enacted} count={r.count} />
              ))}
            </ol>
          </section>

          {/* Right: nations */}
          <section className="space-y-3">
            <h2 className="font-serif text-xl text-text-primary">National standings</h2>
            <ol className="rounded-lg border border-border-default overflow-hidden">
              <li className="flex items-center gap-3 bg-bg-secondary px-3 py-2 text-xs uppercase tracking-wide text-text-muted">
                <span className="w-5 text-right">#</span>
                <span className="w-8">Jx</span>
                <span className="flex-1">Enacted share</span>
                <span className="w-10 text-right">Enac.</span>
                <span className="w-8 text-right">Laws</span>
              </li>
              {nations.map((r, i) => (
                <StandingRow key={`${r.region}/${r.code}`} rank={i + 1} code={r.code} name={r.name}
                  href={`/jurisdictions/${r.region.toLowerCase()}/${r.code.toLowerCase()}/`}
                  enacted={r.enacted} count={r.count} tag={r.region === 'US' ? 'federal' : undefined} />
              ))}
            </ol>
            <p className="text-meta text-text-muted">
              The United States is ranked here on federal law only — its state-level leadership is the
              board on the left.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

function momentumTitle(r: Record<StageKey, number> & { name: string }): string {
  const parts = STAGES.filter(s => r[s.key] > 0).map(s => `${r[s.key]} ${s.label.toLowerCase()}`);
  return parts.length ? `${r.name}: ${parts.join(', ')}` : r.name;
}
