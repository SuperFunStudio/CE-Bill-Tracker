'use client';
import { useMemo, useState } from 'react';
import { useBills } from '@/hooks/useBills';
import { STATE_NAMES, formatDate, fixEncoding, formatInstrumentType } from '@/lib/utils';
import type { BillSummary } from '@/lib/types';
import sessionsData from './legislative-sessions.json';

/**
 * Legislative Timeline — PROTOTYPE (Layer 1 of the "enhanced timeline" concept).
 *
 * Overlays each state's real legislative session windows with our tracked bills, plotted by
 * last_action_date and colored by status, so you can see *when* a bill has a runway to advance.
 *
 * Session windows are REAL: sourced from the OpenStates monthly Postgres dump
 * (opencivicdata_legislativesession) via scripts/fetch_legislative_sessions.py — the same bulk
 * dump behind our historical bill backfill, so no rate-limited API calls. Note that biennium
 * states (CA, NY, NJ, IL, …) carry a single 2-year session row, so their band spans the whole
 * window — the annual rhythm comes from the curated procedural cutoffs below.
 *
 * Still curated/approximate: the dashed CUTOFFS (crossover / house-of-origin deadlines).
 * OpenStates doesn't carry these; they'd become a small curated annual table (Layer 2).
 */

type Session = { start: string; end: string; label: string; special: boolean; active: boolean };
const SESSIONS: Record<string, Session[]> = (sessionsData as { states: Record<string, Session[]> }).states;

const AXIS_START = '2025-01-01';
const AXIS_END = '2026-12-31';
const TODAY = '2026-06-17';

// The only hand-entered layer left — procedural cutoffs after which un-advanced bills are
// effectively dead for the session. Approximate; OpenStates doesn't carry these.
const CUTOFFS: Record<string, { date: string; label: string }[]> = {
  CA: [
    { date: '2025-06-06', label: 'House of origin' },
    { date: '2026-06-05', label: 'House of origin' },
  ],
  WA: [{ date: '2025-03-12', label: 'House of origin' }],
};

const ms = (d: string) => new Date(`${d}T00:00:00`).getTime();
const SPAN = ms(AXIS_END) - ms(AXIS_START);
const pct = (d: string) => Math.min(100, Math.max(0, ((ms(d) - ms(AXIS_START)) / SPAN) * 100));

function statusDot(status: string | null): string {
  switch (status) {
    case 'enacted':
      return 'bg-[rgb(var(--green-accent))]';
    case 'passed':
    case 'passed_chamber':
      return 'bg-sky-400';
    case 'in_committee':
      return 'bg-amber-400';
    case 'introduced':
      return 'bg-amber-300/80';
    case 'vetoed':
    case 'failed':
      return 'bg-text-muted/40';
    default:
      return 'bg-text-muted/60';
  }
}

// Month gridlines; label the first month of each quarter, with the year on January.
const MONTH_TICKS = (() => {
  const ticks: { pos: number; label: string | null }[] = [];
  for (let y = 2025; y <= 2026; y++) {
    for (let m = 0; m < 12; m++) {
      const d = `${y}-${String(m + 1).padStart(2, '0')}-01`;
      const quarter = m % 3 === 0;
      ticks.push({
        pos: pct(d),
        label: quarter ? (m === 0 ? `${y}` : ['Jan', 'Apr', 'Jul', 'Oct'][m / 3]) : null,
      });
    }
  }
  return ticks;
})();

export function LegislativeTimeline() {
  const { data: bills = [], isLoading } = useBills({ epr_relevant: true, limit: 5000 });
  const [hideEnacted, setHideEnacted] = useState(false);
  const [selected, setSelected] = useState<BillSummary | null>(null);

  // Group in-window bills by state. Lane set is stable (ignores hideEnacted); only the dots filter.
  const { lanes, totalPlotted } = useMemo(() => {
    const byState = new Map<string, BillSummary[]>();
    for (const b of bills) {
      if (!b.last_action_date) continue;
      const p = pct(b.last_action_date);
      if (p <= 0 || p >= 100) continue;
      if (!SESSIONS[b.state]) continue; // only states we have session data for
      (byState.get(b.state) ?? byState.set(b.state, []).get(b.state)!).push(b);
    }
    const ordered = [...byState.entries()].sort((a, b) => b[1].length - a[1].length);
    const total = ordered.reduce((s, [, arr]) => s + arr.filter((x) => !(hideEnacted && x.status === 'enacted')).length, 0);
    return {
      lanes: ordered.map(([state, stateBills]) => ({
        state,
        sessions: SESSIONS[state] ?? [],
        cutoffs: CUTOFFS[state] ?? [],
        bills: stateBills.filter((b) => !(hideEnacted && b.status === 'enacted')),
      })),
      totalPlotted: total,
    };
  }, [bills, hideEnacted]);

  return (
    <section className="rounded-xl border border-border-default bg-bg-secondary p-5 space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="font-serif text-lg text-text-primary">
          Legislative Timeline <span className="text-text-muted text-sm">(prototype)</span>
        </h2>
        <label className="flex items-center gap-2 text-xs text-text-secondary select-none cursor-pointer">
          <input
            type="checkbox"
            checked={hideEnacted}
            onChange={(e) => setHideEnacted(e.target.checked)}
            className="accent-[rgb(var(--green-accent))]"
          />
          Hide enacted (show only bills still in motion)
        </label>
      </div>

      <div className="rounded-lg border border-border-default bg-bg-primary/50 p-3 text-xs text-text-secondary leading-relaxed space-y-1.5">
        <p>
          <span className="text-[rgb(var(--green-accent))] font-medium uppercase tracking-wider text-[10px]">Real data</span>{' '}
          Session windows are sourced from the <span className="text-text-primary">OpenStates monthly dump</span>; bills
          are real ({totalPlotted} plotted), placed by last action date.
        </p>
        <p>
          <span className="text-amber-400 font-medium uppercase tracking-wider text-[10px]">Still curated</span>{' '}
          The dashed <span className="text-text-primary">house-of-origin / crossover</span> cutoffs are approximate.
          Biennium states (e.g. CA, NY, NJ) carry one 2-year session, so their band spans the whole window — the annual
          rhythm shows through the cutoffs, not the band.
        </p>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-text-muted">
        <Legend cls="bg-amber-300/80" label="introduced" />
        <Legend cls="bg-amber-400" label="in committee" />
        <Legend cls="bg-sky-400" label="passed chamber" />
        <Legend cls="bg-[rgb(var(--green-accent))]" label="enacted" />
        <Legend cls="bg-text-muted/40" label="failed / vetoed" />
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm bg-[rgb(var(--green-accent))]/15 border border-[rgb(var(--green-accent))]/30" />
          regular session
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm bg-violet-400/15 border border-violet-400/40" />
          special session
        </span>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-11 bg-bg-primary rounded animate-pulse" />
          ))}
        </div>
      ) : lanes.length === 0 ? (
        <p className="text-text-muted text-sm">No tracked bills with an action date in this window.</p>
      ) : (
        <div className="overflow-x-auto">
          <div className="min-w-[680px]">
            {/* Axis */}
            <div className="flex">
              <div className="w-16 shrink-0" />
              <div className="relative h-5 flex-1">
                {MONTH_TICKS.map((t, i) =>
                  t.label ? (
                    <span
                      key={i}
                      className="absolute -translate-x-1/2 text-[10px] text-text-muted"
                      style={{ left: `${t.pos}%` }}
                    >
                      {t.label}
                    </span>
                  ) : null,
                )}
              </div>
            </div>

            {/* Lanes */}
            <div className="space-y-1.5">
              {lanes.map((lane) => (
                <div key={lane.state} className="flex items-stretch">
                  <div className="w-16 shrink-0 flex items-center" title={STATE_NAMES[lane.state] ?? lane.state}>
                    <span className="font-mono text-green-accent text-sm">{lane.state}</span>
                    <span className="ml-1 text-[10px] text-text-muted/70 tabular-nums">{lane.bills.length}</span>
                  </div>
                  <div className="relative flex-1 h-11 rounded bg-bg-primary border border-border-default/60 overflow-hidden">
                    {/* Month gridlines */}
                    {MONTH_TICKS.map((t, i) => (
                      <span
                        key={i}
                        className="absolute top-0 bottom-0 w-px bg-border-default/30"
                        style={{ left: `${t.pos}%` }}
                      />
                    ))}
                    {/* Session bands (special sessions tinted differently) */}
                    {lane.sessions.map((s, i) => (
                      <span
                        key={i}
                        title={`${s.label}: ${formatDate(s.start)} – ${formatDate(s.end)}${s.special ? ' (special)' : ''}`}
                        className={`absolute bottom-0 ${
                          s.special
                            ? 'top-1/2 bg-violet-400/15 border-x border-violet-400/40'
                            : 'top-0 bg-[rgb(var(--green-accent))]/10 border-x border-[rgb(var(--green-accent))]/25'
                        }`}
                        style={{ left: `${pct(s.start)}%`, width: `${Math.max(0.4, pct(s.end) - pct(s.start))}%` }}
                      />
                    ))}
                    {/* Procedural cutoffs (Layer 2 teaser) */}
                    {lane.cutoffs.map((c, i) => (
                      <span
                        key={i}
                        title={`${c.label} cutoff: ${formatDate(c.date)}`}
                        className="absolute top-0 bottom-0 w-px border-l border-dashed border-rose-400/70"
                        style={{ left: `${pct(c.date)}%` }}
                      />
                    ))}
                    {/* Today */}
                    <span className="absolute top-0 bottom-0 w-px bg-text-primary/50" style={{ left: `${pct(TODAY)}%` }} />
                    {/* Bills */}
                    {lane.bills.map((b, i) => {
                      const top = 6 + ((i * 7) % 28);
                      return (
                        <button
                          key={b.id}
                          onClick={() => setSelected(b)}
                          title={`${b.bill_number ?? ''} — ${fixEncoding(b.title)} (${b.status ?? '—'}, ${formatDate(b.last_action_date)})`}
                          className={`absolute h-2 w-2 -translate-x-1/2 rounded-full ${statusDot(b.status)} ring-1 ring-bg-primary hover:scale-150 transition-transform`}
                          style={{ left: `${pct(b.last_action_date!)}%`, top: `${top}px` }}
                        />
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Selected-bill detail */}
      {selected && (
        <div className="rounded-lg border border-border-default bg-bg-primary p-4 text-sm space-y-1">
          <div className="flex items-center justify-between gap-3">
            <span className="font-mono text-green-accent">
              {selected.state} {selected.bill_number ?? ''}
            </span>
            <button onClick={() => setSelected(null)} className="text-text-muted hover:text-text-primary text-xs">
              close ✕
            </button>
          </div>
          <p className="text-text-primary">{fixEncoding(selected.title)}</p>
          <p className="text-text-muted text-xs">
            {formatInstrumentType(selected.instrument_type)} · {selected.status ?? '—'} · last action{' '}
            {formatDate(selected.last_action_date)}
          </p>
        </div>
      )}
    </section>
  );
}

function Legend({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-block h-2 w-2 rounded-full ${cls}`} />
      {label}
    </span>
  );
}
