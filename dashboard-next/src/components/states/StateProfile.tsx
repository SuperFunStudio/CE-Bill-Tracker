'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useBills } from '@/hooks/useBills';
import { useDeadlines } from '@/hooks/useDeadlines';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { BillTable } from '@/components/bills/BillTable';
import { BillFilters, DEFAULT_FILTERS, applyBillFilters, type BillFilterState } from '@/components/bills/BillFilters';
import { STATE_NAMES, formatInstrumentType, formatDate, daysUntil } from '@/lib/utils';
import { programsForState, PROGRAM_KIND_LABEL } from '@/lib/stateProfiles';

/**
 * Pipeline stages, earliest → latest. Mirrors the State Standings leaderboard so a bill's
 * "momentum" reads the same everywhere; opacity climbs with progress.
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

const DEAD_STATUSES = new Set(['failed', 'vetoed', 'tabled', 'dead']);

export function StateProfile({ abbr }: { abbr: string }) {
  const name = STATE_NAMES[abbr];
  const { data: bills = [], isLoading } = useBills({ epr_relevant: true, limit: 5000 });
  const { data: deadlines = [] } = useDeadlines();
  const programs = programsForState(abbr);
  // Bill-explorer filters, scoped to this state (the State select is hidden).
  const [filters, setFilters] = useState<BillFilterState>({ ...DEFAULT_FILTERS, state: abbr });

  const stateBills = useMemo(() => bills.filter(b => b.state === abbr), [bills, abbr]);

  const stats = useMemo(() => {
    const blank = () => ({ introduced: 0, committee: 0, advancing: 0, enacted: 0 } as Record<StageKey, number>);
    const stages = blank();
    let dead = 0;
    let advances = 0;
    let weakens = 0;
    stateBills.forEach(b => {
      const stage = STAGE_OF[(b.status ?? '').toLowerCase()];
      if (stage) stages[stage] += 1;
      if (DEAD_STATUSES.has((b.status ?? '').toLowerCase())) dead += 1;
      if (b.policy_stance === 'advances') advances += 1;
      else if (b.policy_stance === 'weakens') weakens += 1;
    });
    const inMotion = stages.introduced + stages.committee + stages.advancing + stages.enacted;
    return { stages, inMotion, dead, advances, weakens, total: stateBills.length };
  }, [stateBills]);

  const instrumentMix = useMemo(() => {
    const counts: Record<string, number> = {};
    stateBills.forEach(b => {
      const k = b.instrument_type ?? 'other';
      counts[k] = (counts[k] ?? 0) + 1;
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [stateBills]);

  const recentBills = useMemo(
    () =>
      [...stateBills].sort((a, b) =>
        (b.last_action_date ?? '').localeCompare(a.last_action_date ?? ''),
      ),
    [stateBills],
  );

  const filteredBills = useMemo(() => applyBillFilters(recentBills, filters), [recentBills, filters]);

  const upcomingDeadlines = useMemo(
    () =>
      deadlines
        .filter(d => d.state === abbr)
        .filter(d => (daysUntil(d.deadline_date) ?? -1) >= 0)
        .sort((a, b) => a.deadline_date.localeCompare(b.deadline_date))
        .slice(0, 8),
    [deadlines, abbr],
  );

  if (!name) {
    return (
      <div className="p-6 max-w-3xl mx-auto space-y-4">
        <GazetteHeader title="Unknown state" />
        <p className="text-text-muted text-sm">
          We don&rsquo;t recognize &ldquo;{abbr}&rdquo;.{' '}
          <Link href="/states/" className="text-green-accent hover:underline">Back to State Standings</Link>
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <GazetteHeader title={name} subtitle="Circular-economy activity & incentives" />

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link href="/states/" className="text-sm text-green-accent hover:underline">&larr; All states</Link>
        <Link href="/" className="text-sm text-green-accent hover:underline">Front page &rarr;</Link>
      </div>

      {/* At-a-glance counters */}
      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Tracked bills" value={stats.total} />
        <Stat label="Enacted" value={stats.stages.enacted} />
        <Stat label="Advancing" value={stats.advances} hint="bills that strengthen circularity" />
        <Stat label="Weakening" value={stats.weakens} hint="bills that exempt / narrow / repeal" danger={stats.weakens > 0} />
      </section>

      {/* Momentum bar — same visual language as the leaderboard */}
      {stats.inMotion > 0 && (
        <section className="space-y-2">
          <h2 className="font-serif text-lg text-text-primary">Momentum</h2>
          <span className="flex h-2.5 w-full rounded-sm overflow-hidden bg-bg-tertiary">
            {STAGES.map(s =>
              stats.stages[s.key] > 0 ? (
                <span
                  key={s.key}
                  title={`${stats.stages[s.key]} ${s.label.toLowerCase()}`}
                  style={{
                    width: `${(stats.stages[s.key] / stats.inMotion) * 100}%`,
                    backgroundColor: `rgb(var(--green-accent) / ${s.opacity})`,
                  }}
                />
              ) : null,
            )}
          </span>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
            {STAGES.map(s => (
              <span key={s.key} className="inline-flex items-center gap-1.5">
                <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: `rgb(var(--green-accent) / ${s.opacity})` }} />
                {s.label} · {stats.stages[s.key]}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Instrument mix */}
      {instrumentMix.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-serif text-lg text-text-primary">Policy mix</h2>
          <div className="flex flex-wrap gap-2">
            {instrumentMix.map(([type, n]) => (
              <span key={type} className="inline-flex items-center gap-1.5 rounded-full border border-border-default bg-bg-secondary px-3 py-1 text-xs">
                <span className="text-text-primary">{formatInstrumentType(type)}</span>
                <span className="font-serif tabular-nums text-text-muted">{n}</span>
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Curated "beyond the bills" programs / incentives */}
      {programs.length > 0 && (
        <section className="space-y-3">
          <div>
            <h2 className="font-serif text-lg text-text-primary">Notable programs &amp; incentives</h2>
            <p className="text-text-muted text-xs">
              Curated, non-legislative levers — permanent-fund investment, standing incentive programs, and the like.
            </p>
          </div>
          <ul className="space-y-3">
            {programs.map((p, i) => (
              <li key={i} className="rounded-lg border border-border-default bg-bg-secondary p-4">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="font-mono text-[10px] uppercase tracking-wide text-green-accent border border-green-accent/40 rounded px-1.5 py-0.5">
                    {PROGRAM_KIND_LABEL[p.kind]}
                  </span>
                  <h3 className="font-serif text-text-primary">{p.title}</h3>
                </div>
                <p className="text-text-secondary text-sm mt-1.5 leading-relaxed">{p.summary}</p>
                {(p.url || p.source) && (
                  <p className="text-xs text-text-muted mt-2">
                    {p.url ? (
                      <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-green-accent hover:underline">
                        {p.source ?? 'Source'} &rarr;
                      </a>
                    ) : (
                      p.source
                    )}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Upcoming deadlines in this state */}
      {upcomingDeadlines.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-serif text-lg text-text-primary">Upcoming deadlines</h2>
          <ul className="rounded-lg border border-border-default divide-y divide-border-default overflow-hidden">
            {upcomingDeadlines.map(d => (
              <li key={d.id} className="px-4 py-2.5 flex items-baseline justify-between gap-3 bg-bg-secondary/40">
                <span className="text-sm text-text-primary min-w-0">
                  {d.description || d.deadline_type}
                  {d.bill_number && <span className="text-text-muted"> · {d.bill_number}</span>}
                </span>
                <span className="text-xs text-text-muted whitespace-nowrap tabular-nums">{formatDate(d.deadline_date)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Tracked bills */}
      <section className="space-y-2">
        <div className="flex items-baseline gap-3">
          <h2 className="font-serif text-lg text-text-primary">Tracked bills</h2>
          {!isLoading && recentBills.length > 0 && (
            <span className="text-text-muted text-sm">{filteredBills.length} of {recentBills.length}</span>
          )}
        </div>
        {isLoading ? (
          <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="h-12 bg-bg-secondary rounded animate-pulse" />)}</div>
        ) : recentBills.length > 0 ? (
          <>
            <BillFilters filters={filters} onChange={setFilters} hideState />
            {filteredBills.length > 0 ? (
              <BillTable bills={filteredBills} autoPageSize={8} />
            ) : (
              <p className="text-text-muted text-sm py-2">No bills match these filters.</p>
            )}
          </>
        ) : (
          <p className="text-text-muted text-sm">
            No tracked circularity legislation in {name} yet — wide-open territory.
          </p>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, hint, danger }: { label: string; value: number; hint?: string; danger?: boolean }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-secondary px-3 py-2.5" title={hint}>
      <div className={`font-serif text-2xl tabular-nums ${danger ? 'text-urgency-high' : 'text-text-primary'}`}>{value}</div>
      <div className="text-xs text-text-muted">{label}</div>
    </div>
  );
}
