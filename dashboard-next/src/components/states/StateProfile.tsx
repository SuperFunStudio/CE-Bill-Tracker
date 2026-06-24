'use client';
import { useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useBills } from '@/hooks/useBills';
import { useDeadlines } from '@/hooks/useDeadlines';
import { useCompliancePathways } from '@/hooks/useCompliancePathways';
import type { CompliancePathway } from '@/lib/types';
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

/** Action types that impose a concrete producer obligation (vs. monitor/none). */
const ACTIONABLE = new Set([
  'join_pro', 'file_individual_plan', 'register_with_state', 'pay_into_program', 'arrange_collection',
]);
const ACTION_LABEL: Record<string, string> = {
  join_pro: 'Join a PRO',
  file_individual_plan: 'File a plan',
  register_with_state: 'Register with state',
  pay_into_program: 'Pay into program',
  arrange_collection: 'Arrange collection',
};

export function StateProfile({ abbr }: { abbr: string }) {
  const name = STATE_NAMES[abbr];
  const { data: bills = [], isLoading } = useBills({ ce_relevant: true, limit: 5000 });
  const { data: deadlines = [] } = useDeadlines();
  const { data: pathways = [], isLoading: pathwaysLoading, isError: pathwaysError } = useCompliancePathways(abbr);
  const programs = programsForState(abbr);

  // Compliance pathways exist only for enacted laws. Split into actionable obligations
  // (join a PRO / file a plan / register) vs. tracked-but-no-obligation (labeling, study, …).
  const actionable = useMemo(
    () => pathways.filter(p => ACTIONABLE.has(p.action_type ?? '')),
    [pathways],
  );
  const hasPRO = useMemo(
    () => actionable.some(p => p.action_type === 'join_pro' || p.entity?.entity_type === 'pro'),
    [actionable],
  );
  // Bill-explorer filters, scoped to this state (the State select is hidden).
  const [filters, setFilters] = useState<BillFilterState>({ ...DEFAULT_FILTERS, state: abbr });
  const [showAllPathways, setShowAllPathways] = useState(false);
  const billsRef = useRef<HTMLDivElement>(null);

  // A headline counter sets the matching bill filter and jumps to the table.
  const PATHWAY_PAGE = 5;
  function focusBills(partial: Partial<BillFilterState>) {
    setFilters({ ...DEFAULT_FILTERS, state: abbr, ...partial });
    billsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  const stateBills = useMemo(() => bills.filter(b => b.state === abbr), [bills, abbr]);

  const stats = useMemo(() => {
    const blank = () => ({ introduced: 0, committee: 0, advancing: 0, enacted: 0 } as Record<StageKey, number>);
    const stages = blank();
    let dead = 0;
    stateBills.forEach(b => {
      const stage = STAGE_OF[(b.status ?? '').toLowerCase()];
      if (stage) stages[stage] += 1;
      if (DEAD_STATUSES.has((b.status ?? '').toLowerCase())) dead += 1;
    });
    const inMotion = stages.introduced + stages.committee + stages.advancing + stages.enacted;
    return { stages, inMotion, dead, total: stateBills.length };
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
        <p className="text-text-secondary text-body">
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

      {/* At-a-glance counters. Tracked + Enacted filter the table below and scroll to it;
          Advancing + In motion are momentum read-outs that match the Momentum bar. */}
      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Tracked bills" value={stats.total} onClick={() => focusBills({})} />
        <Stat label="Enacted" value={stats.stages.enacted} onClick={() => focusBills({ status: 'enacted' })} />
        <Stat label="Advancing" value={stats.stages.advancing} hint="cleared at least one chamber" />
        <Stat label="In motion" value={stats.inMotion} hint="active bills, introduced through enacted" />
      </section>

      {/* How to comply — the action layer: each enacted law → its next step */}
      <section className="space-y-3">
        <div>
          <h2 className="font-serif text-lg text-text-primary">How to comply</h2>
          <p className="text-text-muted text-xs">
            For each enacted law, who a producer registers with and what to do next.
          </p>
        </div>

        {stats.stages.enacted === 0 ? (
          <p className="rounded-lg border border-border-default bg-bg-secondary px-4 py-3 text-body text-text-secondary">
            No enacted EPR law in {name} yet — there&rsquo;s nothing to comply with here.
          </p>
        ) : pathwaysLoading && pathways.length === 0 ? (
          <div className="space-y-2">{[...Array(2)].map((_, i) => <div key={i} className="h-20 bg-bg-secondary rounded animate-pulse" />)}</div>
        ) : pathwaysError ? (
          <p className="rounded-lg border border-border-default bg-bg-secondary px-4 py-3 text-body text-text-secondary">
            Couldn&rsquo;t load compliance details right now — please try again shortly.
          </p>
        ) : pathways.length === 0 ? (
          <p className="rounded-lg border border-border-default bg-bg-secondary px-4 py-3 text-body text-text-secondary">
            Compliance pathways for {name} aren&rsquo;t available yet.
          </p>
        ) : actionable.length === 0 ? (
          <p className="rounded-lg border border-border-default bg-bg-secondary px-4 py-3 text-body text-text-secondary">
            {name} has enacted circularity legislation, but none yet imposes a producer-compliance
            obligation (e.g. labeling, disposal-ban, or study laws).
          </p>
        ) : (
          <>
            {!hasPRO && (
              <p className="rounded-lg border border-border-default bg-bg-tertiary/40 px-4 py-2.5 text-xs text-text-muted">
                No producer responsibility organization (PRO) operates in {name} yet — obligations are
                met through individual producer filings or state-run programs.
              </p>
            )}
            <ul className="space-y-3">
              {(showAllPathways ? actionable : actionable.slice(0, PATHWAY_PAGE)).map(p => (
                <PathwayCard key={p.bill_id} p={p} />
              ))}
            </ul>
            {actionable.length > PATHWAY_PAGE && (
              <button
                onClick={() => setShowAllPathways(s => !s)}
                className="text-green-accent text-xs hover:underline"
              >
                {showAllPathways
                  ? 'Show fewer'
                  : `Show all ${actionable.length} compliance actions`}
              </button>
            )}
            {pathways.length - actionable.length > 0 && (
              <p className="text-text-muted text-xs">
                + {pathways.length - actionable.length} other enacted law
                {pathways.length - actionable.length === 1 ? '' : 's'} with no producer-compliance obligation.
              </p>
            )}
          </>
        )}
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
                  <span className="font-mono text-meta uppercase tracking-wide text-green-accent border border-green-accent/40 rounded px-1.5 py-0.5">
                    {PROGRAM_KIND_LABEL[p.kind]}
                  </span>
                  <h3 className="font-serif text-text-primary">{p.title}</h3>
                </div>
                <p className="text-text-secondary text-body mt-1.5 leading-relaxed">{p.summary}</p>
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
      <section ref={billsRef} className="space-y-2 scroll-mt-6">
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
              <p className="text-text-secondary text-body py-2">No bills match these filters.</p>
            )}
          </>
        ) : (
          <p className="text-text-secondary text-body">
            No tracked circularity legislation in {name} yet — wide-open territory.
          </p>
        )}
      </section>
    </div>
  );
}

function PathwayCard({ p }: { p: CompliancePathway }) {
  const actionLabel = ACTION_LABEL[p.action_type ?? ''] ?? 'Action';
  return (
    <li className="rounded-lg border border-border-default bg-bg-secondary p-4">
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="font-mono text-meta uppercase tracking-wide text-green-accent border border-green-accent/40 rounded px-1.5 py-0.5">
          {actionLabel}
        </span>
        <h3 className="font-serif text-text-primary">
          {p.bill_number}
          {p.bill_title && <span className="text-text-secondary font-sans text-sm"> · {p.bill_title}</span>}
        </h3>
      </div>
      <p className="text-text-secondary text-body mt-1.5 leading-relaxed">{p.action_summary}</p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-xs text-text-muted">
        {p.entity && (
          p.registration_url ? (
            <a href={p.registration_url} target="_blank" rel="noopener noreferrer" className="text-green-accent hover:underline">
              {p.entity.name} &rarr;
            </a>
          ) : (
            <span className="text-text-primary">{p.entity.name}</span>
          )
        )}
        {p.next_deadline_date && <span className="tabular-nums">Next deadline {formatDate(p.next_deadline_date)}</span>}
        {p.has_fee && <span>Fee applies</span>}
      </div>
    </li>
  );
}

function Stat({ label, value, hint, danger, onClick }: { label: string; value: number; hint?: string; danger?: boolean; onClick?: () => void }) {
  const inner = (
    <>
      <div className={`font-serif text-2xl tabular-nums ${danger ? 'text-urgency-high' : 'text-text-primary'}`}>{value}</div>
      <div className="text-xs text-text-muted">{label}</div>
    </>
  );
  const base = 'rounded-lg border border-border-default bg-bg-secondary px-3 py-2.5';
  if (!onClick) {
    return <div className={base} title={hint}>{inner}</div>;
  }
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint ? `${hint} — click to filter` : 'Click to filter the bills below'}
      className={`${base} text-left w-full transition-colors hover:border-green-accent/60 hover:bg-bg-tertiary/40 focus:outline-none focus:border-green-accent`}
    >
      {inner}
    </button>
  );
}
