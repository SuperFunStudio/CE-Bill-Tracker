'use client';

import { useEffect, useState } from 'react';
import { fetchStateGap } from '@/lib/api';
import { STATE_NAMES } from '@/lib/utils';
import { track } from '@/lib/analytics';
import type { StateGapRow, BillParams } from '@/lib/types';
import { BillDrilldownPanel } from './BillDrilldownPanel';

/**
 * "Battle of the Bills" gap table: each state's advancing-CE passage rate next to its all-bills
 * baseline. The gap is the signal — a state can pass CE bills ABOVE its general rate (a priority) or
 * far below (contested-policy drag). Clicking a state opens the bill drill-down (its advancing CE
 * bills, each linked to source) — attribution lives on the card and in the modal.
 */

function pct(n: number | null | undefined): string {
  return n == null ? '—' : `${(n * 100).toFixed(0)}%`;
}

function GapBadge({ gap }: { gap: number | null }) {
  if (gap == null) return <span className="text-text-muted text-xs">no baseline</span>;
  const pts = (gap * 100).toFixed(0);
  const positive = gap >= 0;
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${
        positive
          ? 'border-[rgb(var(--green-accent))] text-[rgb(var(--green-accent))]'
          : 'border-red-500 text-red-600 dark:text-red-400'
      }`}
      title={positive ? 'CE bills pass more readily than the state average' : 'CE bills pass below the state average (contested-policy drag)'}
    >
      {positive ? '+' : ''}{pts}pt
    </span>
  );
}

export function StateGapTable() {
  const [rows, setRows] = useState<StateGapRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drill, setDrill] = useState<{ params: BillParams; title: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchStateGap()
      .then((d) => !cancelled && setRows(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : 'Could not load the gap table.'));
    return () => {
      cancelled = true;
    };
  }, []);

  function openState(r: StateGapRow) {
    setDrill({
      params: { ce_relevant: true, state: r.state, policy_stance: 'advances' },
      title: `${STATE_NAMES[r.state] ?? r.state} · advancing circular-economy bills`,
    });
    track('insights_gap_drilldown', { state: r.state });
  }

  if (error) return <p className="text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!rows) {
    return (
      <div className="grid gap-2 sm:grid-cols-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-lg bg-bg-tertiary" />
        ))}
      </div>
    );
  }
  if (rows.length === 0) return <p className="text-text-secondary text-body">No states with enough volume yet.</p>;

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2">
        {rows.map((r) => (
          <button
            key={r.state}
            onClick={() => openState(r)}
            className="flex items-center justify-between gap-3 rounded-lg border border-border-default bg-bg-primary p-3 text-left transition-colors hover:bg-bg-tertiary"
          >
            <div className="min-w-0">
              <div className="font-semibold text-text-primary text-sm">{STATE_NAMES[r.state] ?? r.state}</div>
              <div className="text-text-muted text-xs mt-0.5">
                CE <span className="text-text-secondary">{pct(r.ce_rate)}</span> vs{' '}
                <span className="text-text-secondary">{pct(r.baseline_rate)}</span> all-bills · {r.ce_enacted}/{r.ce_total} enacted
              </div>
            </div>
            <GapBadge gap={r.gap} />
          </button>
        ))}
      </div>
      <p className="text-text-muted text-xs leading-relaxed">
        Each state&apos;s advancing-CE passage rate (2019+) next to its all-bills baseline computed from the
        full OpenStates corpus. <span className="text-text-secondary">Green = CE bills pass above the state&apos;s
        average bill; red = below</span> (contested-policy drag). States with fewer than 15 advancing CE bills
        are omitted as too small to compare. Click a state to see the bills behind its number, each linked to its source.
      </p>

      <BillDrilldownPanel
        open={!!drill}
        onClose={() => setDrill(null)}
        title={drill?.title ?? ''}
        subtitle="advancing · all years tracked"
        params={drill?.params ?? null}
        source="state_gap"
      />
    </div>
  );
}
