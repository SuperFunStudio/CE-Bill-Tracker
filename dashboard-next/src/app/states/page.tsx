'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useBills } from '@/hooks/useBills';
import { useFederalActions } from '@/hooks/useFederal';
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

// ── Two ranks (see WorldStandings) ──────────────────────────────────────────────────────────────
// ENACTED — laws in force, the fair cross-jurisdiction comparison (the metric the homepage globe
// shades by). ACTIVITY — a plain count of every tracked bill (all statuses), plus US federal
// regulatory actions, so it reads as an honest tally of movement rather than an abstract index.
// `total` counts every bill regardless of status; the per-stage fields drive the momentum bar.
type StageTally = { introduced: number; committee: number; advancing: number; enacted: number; total: number };
const blankStage = (): StageTally => ({ introduced: 0, committee: 0, advancing: 0, enacted: 0, total: 0 });

function tallyStage(t: StageTally, status: string | null | undefined): void {
  t.total += 1; // every tracked bill counts toward Activity, whatever its status
  const stage = STAGE_OF[(status ?? '').toLowerCase()];
  if (stage) t[stage] += 1; // failed/vetoed/dead map to no stage — the momentum bar shows LIVE movement
}

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
      <GazetteHeader title="State Rankings" subtitle="US circular-economy law momentum" />

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
  // region: 'all' — the endpoint defaults to US-only, but this board filters to EU rows, so without
  // it the EU list would always be empty.
  const { data: bills = [], isLoading, isError, refetch } = useBills({ ce_relevant: true, limit: 5000, region: 'all' });

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

  const title = 'Member State Rankings';
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

/**
 * One row shared by both Standings columns. The jurisdiction NAME is the `flex-1` element and the
 * progress bar is FIXED-width — previously the bar grew (`flex-1`) and starved the name to zero in the
 * narrow two-column desktop grid, so the name showed on mobile (wide single column) but vanished on
 * desktop. The bar hides below `sm` to give the name the whole row on the smallest screens.
 */
function StandingRow({ rank, code, name, href, primary, secondary, barPct, tag, note }: {
  rank: number; code: string; name: string; href: string;
  primary: number | string; secondary: number | string; barPct: number; tag?: string; note?: string;
}) {
  return (
    <li className="border-t border-border-default first:border-t-0">
      <Link href={href} className="flex items-center gap-2.5 px-3 py-2 hover:bg-bg-secondary/60">
        <span className="font-serif text-text-muted w-5 text-right tabular-nums shrink-0">{rank}</span>
        <span className="font-mono font-bold text-green-accent w-9 shrink-0" title={name}>{code}</span>
        <span className="flex-1 min-w-0 truncate text-sm text-text-primary" title={name}>{name}</span>
        {tag && (
          <span className="shrink-0 text-[10px] uppercase tracking-wide text-text-muted border border-border-default rounded px-1 leading-4">
            {tag}
          </span>
        )}
        {note && <span className="shrink-0 text-[10px] text-text-muted whitespace-nowrap hidden md:inline">{note}</span>}
        <span className="hidden sm:block w-14 h-2 rounded-sm overflow-hidden bg-bg-tertiary shrink-0" title={`${Math.round(barPct)}%`}>
          <span className="block h-full" style={{ width: `${Math.min(100, barPct)}%`, backgroundColor: 'rgb(var(--green-accent))' }} />
        </span>
        <span className="text-text-muted text-xs tabular-nums w-8 text-right shrink-0">{secondary || '—'}</span>
        <span className="font-serif text-text-primary tabular-nums w-9 text-right shrink-0">{primary}</span>
      </Link>
    </li>
  );
}

// A ranked jurisdiction row (a country in the national column, or a US state in the sub-national one).
// `combinedEnacted`/`combinedMotion` fold in the country's sub-national tier (US states today); they
// only differ from the national figures for a federation with tracked sub-national law.
type StandingEntry = {
  region: string; code: string; name: string;
  enacted: number; motion: number; activity: number;
  combinedEnacted: number; combinedMotion: number;
};

/**
 * The flagship two-column ranking: NATIONAL law by country (left) alongside SUB-NATIONAL law (right).
 * Not a US-vs-world comparison — just the global tally, by jurisdiction. Each column carries its OWN
 * ranking control, because the two tiers are measured differently:
 *
 * NATIONAL toggle — "National" vs "Combined". National law is enacted-heavy with no introduced→enacted
 * funnel, so an activity/introduced axis is meaningless here; both views rank by ENACTED laws in force.
 * "Combined" folds each country's sub-national enacted laws into its total — today only the US has a
 * tracked sub-national tier, so switching to Combined is what lifts the US (no federal EPR statute) up
 * on the strength of its 50 states. It generalizes as more federations gain state coverage.
 *
 * SUB-NATIONAL toggle — "Enacted" vs "Activity". Here the US pipeline IS a funnel, so the introduced/
 * enacted distinction is real: Enacted ranks by laws in force; Activity ranks by a plain count of every
 * tracked bill (all statuses). This is where that toggle lives.
 *
 * Sub-national rows are first-class only for the US today: foreign provinces (CA/AU) collapse to their
 * country code in the data (see foreign_id in app/ingestion/foreign.py), so decomposing them into the
 * sub-national column is a v2.
 */
function WorldStandings() {
  const { setRegions } = useRegion();
  // region: 'all' is REQUIRED here — the /bills endpoint defaults to US-only when no region is given,
  // so without this the national column would only ever show the United States (no France/Japan/…).
  const { data: bills = [], isLoading, isError, refetch } = useBills({ ce_relevant: true, limit: 5000, region: 'all' });
  // US FEDERAL regulatory activity — agency rulemakings (EPA/GSA/FTC) live in a separate table from
  // bills. They feed the sub-national ACTIVITY score only (movement, not enacted law); the national
  // column ranks purely by enacted law and never counts them.
  const { data: federal = [] } = useFederalActions({ ce_relevant: true, limit: 500, days_back: 3650 });
  const [natView, setNatView] = useState<'national' | 'combined'>('national'); // left column: enacted scope
  const [subView, setSubView] = useState<'enacted' | 'activity'>('enacted');   // right column: enacted vs activity

  const { states, nations, maxStateRaw, usRollup } = useMemo(() => {
    const stStage: Record<string, StageTally> = {};
    const natStage: Record<string, StageTally> = { US: blankStage() };
    const natMeta: Record<string, { region: string; code: string; name: string }> = {
      US: { region: 'US', code: 'US', name: 'United States' },
    };
    for (const b of bills) {
      if (b.region === 'US') {
        if (b.state && b.state !== 'US') tallyStage((stStage[b.state] ??= blankStage()), b.status);
        else tallyStage(natStage.US, b.status); // state == "US" → federal law
        continue;
      }
      // Foreign / EU: region is the country/bloc bucket (region == state for foreign national law).
      natMeta[b.region] ??= { region: b.region, code: b.region, name: jurisdictionDisplayName(b.region, b.region) };
      tallyStage((natStage[b.region] ??= blankStage()), b.status);
    }

    const toRow = (meta: { region: string; code: string; name: string }, s: StageTally, activityBonus = 0): StandingEntry => {
      const enacted = s.enacted;
      const motion = s.introduced + s.committee + s.advancing + s.enacted;
      return { ...meta, enacted, motion, activity: s.total + activityBonus, combinedEnacted: enacted, combinedMotion: motion };
    };

    const states = Object.keys(stStage)
      .map(abbr => toRow({ region: 'US', code: abbr, name: STATE_NAMES[abbr] ?? abbr }, stStage[abbr]))
      .filter(r => r.motion > 0);

    // Per-country sub-national totals, folded into the national row's "Combined" view. Only the US has a
    // tracked sub-national tier today; the map generalizes as more federations gain state coverage.
    const subEnactedByCountry: Record<string, { enacted: number; motion: number }> = {
      US: {
        enacted: states.reduce((n, r) => n + r.enacted, 0),
        motion: states.reduce((n, r) => n + r.motion, 0),
      },
    };

    const nations = Object.keys(natStage).map(code => {
      const row = toRow(natMeta[code], natStage[code]);
      const sub = subEnactedByCountry[code];
      if (sub) { row.combinedEnacted = row.enacted + sub.enacted; row.combinedMotion = row.motion + sub.motion; }
      return row;
    });

    const maxStateRaw = Math.max(1, ...states.map(r => r.activity));

    // Per-country combined rollup callout: the US across every tier (federal + all 50 states).
    const usNat = nations.find(n => n.code === 'US')!;
    const usRollup = {
      enacted: usNat.combinedEnacted,
      motion: usNat.combinedMotion,
      states: states.length,
      federalActions: federal.length,
    };

    return { states, nations, maxStateRaw, usRollup };
  }, [bills, federal]);

  // National column ranks by enacted law only; "Combined" swaps in the tier-combined figures.
  const isCombined = natView === 'combined';
  const sortedNations = useMemo(() => {
    const key = (r: StandingEntry) => (isCombined ? r.combinedEnacted : r.enacted);
    const tie = (r: StandingEntry) => (isCombined ? r.combinedMotion : r.motion);
    return [...nations].sort((a, b) => key(b) - key(a) || tie(b) - tie(a) || a.name.localeCompare(b.name));
  }, [nations, isCombined]);
  const natRowFor = (r: StandingEntry) =>
    isCombined
      ? { primary: r.combinedEnacted, secondary: r.combinedMotion, barPct: r.combinedMotion ? (r.combinedEnacted / r.combinedMotion) * 100 : 0 }
      : { primary: r.enacted, secondary: r.motion, barPct: r.motion ? (r.enacted / r.motion) * 100 : 0 };

  // Sub-national column carries the enacted-vs-activity toggle (the US pipeline is a real funnel).
  const subEnacted = subView === 'enacted';
  const sortedStates = useMemo(() => {
    const cmp = (a: StandingEntry, b: StandingEntry) =>
      subEnacted
        ? b.enacted - a.enacted || b.activity - a.activity || a.name.localeCompare(b.name)
        : b.activity - a.activity || b.enacted - a.enacted || a.name.localeCompare(b.name);
    return [...states].sort(cmp);
  }, [states, subEnacted]);
  const subRowFor = (r: StandingEntry) =>
    subEnacted
      ? { primary: r.enacted, secondary: r.motion, barPct: r.motion ? (r.enacted / r.motion) * 100 : 0 }
      : { primary: r.activity, secondary: r.enacted, barPct: (r.activity / maxStateRaw) * 100 };

  const Toggle = <T extends string>({ value, options, onChange }: {
    value: T; options: readonly (readonly [T, string])[]; onChange: (v: T) => void;
  }) => (
    <div className="inline-flex rounded-md border border-border-default overflow-hidden text-xs">
      {options.map(([mode, label]) => (
        <button
          key={mode}
          onClick={() => onChange(mode)}
          aria-pressed={value === mode}
          className={`px-2.5 py-1 font-mono uppercase tracking-wide transition-colors ${
            value === mode ? 'bg-green-accent text-bg-primary' : 'bg-bg-secondary text-text-muted hover:text-text-primary'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-6">
      <GazetteHeader title="Rankings" subtitle="Circular-economy law by jurisdiction" />

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link href="/" className="text-sm text-green-accent hover:underline">&larr; Back to the front page</Link>
      </div>

      <p className="text-text-secondary text-body -mt-2">
        Two rankings side by side. <strong>National</strong> ranks countries by circular-economy law in
        force — the fair comparison across borders; switch it to <strong>Combined</strong> to fold in each
        country&rsquo;s sub-national laws (today that means the US and its 50 states). <strong>Sub-national</strong>
        ranks US states, where you can toggle between law <strong>enacted</strong> and total <strong>activity</strong>.
      </p>

      {/* Per-country combined rollup: the US across every tier (federal + all 50 states). */}
      {!isLoading && !isError && (
        <div className="rounded-lg border border-border-default bg-bg-secondary/50 px-4 py-3 text-sm text-text-secondary">
          <span className="font-serif text-text-primary">United States — all tiers combined:</span>{' '}
          <span className="tabular-nums text-text-primary">{usRollup.enacted}</span> enacted ·{' '}
          <span className="tabular-nums text-text-primary">{usRollup.motion}</span> bills in motion across
          federal + {usRollup.states} states ·{' '}
          <span className="tabular-nums text-text-primary">{usRollup.federalActions}</span> federal regulatory actions
        </div>
      )}

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
          {/* Left: national law by country — ranked by enacted law (National) or tier-combined enacted (Combined). */}
          <section className="space-y-3">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-serif text-xl text-text-primary">National</h2>
              <Toggle value={natView} onChange={setNatView}
                options={[['national', 'National'], ['combined', 'Combined']] as const} />
            </div>
            <ol className="rounded-lg border border-border-default overflow-hidden">
              <li className="flex items-center gap-2.5 bg-bg-secondary px-3 py-2 text-xs uppercase tracking-wide text-text-muted">
                <span className="w-5 text-right shrink-0">#</span>
                <span className="w-9 shrink-0">Jx</span>
                <span className="flex-1 min-w-0">Country</span>
                <span className="hidden sm:block w-14 shrink-0">Enac. share</span>
                <span className="w-8 text-right shrink-0">Bills</span>
                <span className="w-9 text-right shrink-0">Laws</span>
              </li>
              {sortedNations.map((r, i) => {
                const v = natRowFor(r);
                return (
                  <StandingRow key={`${r.region}/${r.code}`} rank={i + 1} code={r.code} name={r.name}
                    href={`/jurisdictions/${r.region.toLowerCase()}/${r.code.toLowerCase()}/`}
                    primary={v.primary} secondary={v.secondary} barPct={v.barPct}
                    tag={r.region === 'US' && !isCombined ? 'federal' : undefined} />
                );
              })}
            </ol>
            <p className="text-meta text-text-muted">
              National law is enacted-heavy with no introduced→enacted pipeline, so this column ranks
              purely by <strong>laws in force</strong>. On <span className="uppercase">National</span> a
              federal tag marks a country counted on its national statutes only (e.g. the US, with no
              federal EPR law); <span className="uppercase">Combined</span> folds in its sub-national tier —
              the board on the right — which is what lifts the US.
            </p>
          </section>

          {/* Right: sub-national law (US states today) + a quick pivot to its parent national jurisdiction */}
          <section className="space-y-3">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-serif text-xl text-text-primary">Sub-national</h2>
              <div className="flex items-center gap-3">
                <Toggle value={subView} onChange={setSubView}
                  options={[['enacted', 'Enacted'], ['activity', 'Activity']] as const} />
                {/* Quick-select the national jurisdiction this sub-national tier belongs to. Today that's the
                    US (opens its full momentum board); becomes a picker when more federations are tracked. */}
                <button onClick={() => setRegions(['US'])} className="text-xs text-green-accent hover:underline whitespace-nowrap">
                  United States &rarr;
                </button>
              </div>
            </div>
            <ol className="rounded-lg border border-border-default overflow-hidden">
              <li className="flex items-center gap-2.5 bg-bg-secondary px-3 py-2 text-xs uppercase tracking-wide text-text-muted">
                <span className="w-5 text-right shrink-0">#</span>
                <span className="w-9 shrink-0">St</span>
                <span className="flex-1 min-w-0">State</span>
                <span className="hidden sm:block w-14 shrink-0">{subEnacted ? 'Enac. share' : 'Activity'}</span>
                <span className="w-8 text-right shrink-0">{subEnacted ? 'Bills' : 'Enac.'}</span>
                <span className="w-9 text-right shrink-0">{subEnacted ? 'Laws' : 'Total'}</span>
              </li>
              {sortedStates.map((r, i) => {
                const v = subRowFor(r);
                return (
                  <StandingRow key={r.code} rank={i + 1} code={r.code} name={r.name}
                    href={`/jurisdictions/us/${r.code.toLowerCase()}/`}
                    primary={v.primary} secondary={v.secondary} barPct={v.barPct} />
                );
              })}
            </ol>
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
