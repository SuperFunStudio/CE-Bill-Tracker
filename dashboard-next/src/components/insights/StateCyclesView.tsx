'use client';

import { useEffect, useState } from 'react';
import { fetchStateCycles } from '@/lib/api';
import { STATE_NAMES } from '@/lib/utils';
import { track } from '@/lib/analytics';
import type { StateCycleRow, BillParams } from '@/lib/types';
import { BillDrilldownPanel } from './BillDrilldownPanel';

/**
 * Per-cycle view: one state's advancing-CE passage rate vs. its all-bills baseline, broken out by
 * legislative biennium — so the gap reads as a trend (is CE policy gaining ground cycle over cycle?).
 * Bucketed by biennium, which is carryover-safe (a bill introduced in year 1 and enacted in year 2
 * stays in one cycle). Click a cycle to see its bills + sources.
 */

const STATE_OPTIONS = Object.keys(STATE_NAMES).sort((a, b) => STATE_NAMES[a].localeCompare(STATE_NAMES[b]));

function pct(n: number | null | undefined): string {
  return n == null ? '—' : `${Math.round(n * 100)}%`;
}

function GapBadge({ gap }: { gap: number | null }) {
  if (gap == null) return <span className="text-text-muted text-meta">—</span>;
  const positive = gap >= 0;
  return (
    <span
      className={`shrink-0 rounded-full border px-2 py-0.5 text-meta font-semibold ${
        positive
          ? 'border-[rgb(var(--green-accent))] text-[rgb(var(--green-accent))]'
          : 'border-red-500 text-red-600 dark:text-red-400'
      }`}
    >
      {positive ? '+' : ''}{Math.round(gap * 100)}pt
    </span>
  );
}

/** Two stacked mini-bars: CE rate (green) over baseline rate (gray), each scaled 0–100%. */
function MiniBars({ ce, base }: { ce: number | null; base: number | null }) {
  return (
    <div className="w-28 space-y-1">
      <div className="h-1.5 w-full rounded bg-bg-tertiary">
        <div className="h-1.5 rounded bg-[rgb(var(--green-accent))]" style={{ width: `${(ce ?? 0) * 100}%` }} />
      </div>
      <div className="h-1.5 w-full rounded bg-bg-tertiary">
        <div className="h-1.5 rounded bg-text-muted" style={{ width: `${(base ?? 0) * 100}%` }} />
      </div>
    </div>
  );
}

export function StateCyclesView() {
  const [state, setState] = useState('CA');
  const [rows, setRows] = useState<StateCycleRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drill, setDrill] = useState<{ params: BillParams; title: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    fetchStateCycles(state)
      .then((d) => !cancelled && setRows(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : 'Could not load cycles.'));
    return () => {
      cancelled = true;
    };
  }, [state]);

  function openCycle(r: StateCycleRow) {
    setDrill({
      params: {
        ce_relevant: true,
        state,
        policy_stance: 'advances',
        year_from: r.start_year,
        year_to: r.start_year + 1,
      },
      title: `${STATE_NAMES[state] ?? state} ${r.biennium} · advancing CE bills`,
    });
    track('insights_cycle_drilldown', { state, biennium: r.biennium });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <label className="text-text-muted text-xs">State</label>
        <select
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            track('insights_cycle_state', { state: e.target.value });
          }}
          className="rounded-md border border-border-default bg-bg-primary px-2 py-1 text-xs text-text-secondary"
        >
          {STATE_OPTIONS.map((s) => (
            <option key={s} value={s}>{STATE_NAMES[s]}</option>
          ))}
        </select>
      </div>

      {error ? (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : !rows ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-bg-tertiary" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="text-text-secondary text-body">No tracked circular-economy cycles for {STATE_NAMES[state] ?? state} yet.</p>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <button
              key={r.start_year}
              onClick={() => openCycle(r)}
              className="flex w-full items-center gap-3 rounded-lg border border-border-default bg-bg-primary p-3 text-left transition-colors hover:bg-bg-tertiary"
            >
              <div className="w-24 shrink-0">
                <div className="font-semibold text-text-primary text-sm">{r.biennium}</div>
                {r.in_flight && <div className="text-text-muted text-meta">in progress</div>}
              </div>
              <MiniBars ce={r.ce_rate} base={r.baseline_rate} />
              <div className="min-w-0 flex-1 text-xs text-text-muted">
                CE <span className="text-text-secondary">{pct(r.ce_rate)}</span> ({r.ce_enacted}/{r.ce_total})
                {' '}· baseline <span className="text-text-secondary">{pct(r.baseline_rate)}</span>
              </div>
              <GapBadge gap={r.gap} />
            </button>
          ))}
        </div>
      )}

      <p className="text-text-muted text-xs leading-relaxed">
        Each row is one two-year legislative cycle: the green bar is the state&apos;s advancing-CE passage
        rate, the gray bar its all-bills baseline. The current biennium is still in progress, so its rate
        runs low (bills haven&apos;t finished moving). Pre-2019 cycles are omitted — we hold only enacted laws
        from before continuous tracking, with no denominator. Click a cycle for its bills and sources.
      </p>

      <BillDrilldownPanel
        open={!!drill}
        onClose={() => setDrill(null)}
        title={drill?.title ?? ''}
        params={drill?.params ?? null}
        source="state_cycles"
      />
    </div>
  );
}
