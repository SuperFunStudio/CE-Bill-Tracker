'use client';

import { useEffect, useState } from 'react';
import { fetchChampions, fetchChampionBills } from '@/lib/api';
import { STATE_NAMES, formatInstrumentType, fixEncoding } from '@/lib/utils';
import { track } from '@/lib/analytics';
import type { ChampionSummary, ChampionBill } from '@/lib/types';

/**
 * The CE champion roster — legislators advancing circular-economy bills, currently in office, ranked
 * by lead sponsorships. Filter by state (≈34 active/state). Expanding a champion lists their bills,
 * each linked to its source (the link-to-source rule, applied to people as well as the gap table).
 */

const STATE_OPTIONS = Object.keys(STATE_NAMES).sort((a, b) => STATE_NAMES[a].localeCompare(STATE_NAMES[b]));

function partyChip(party: string | null): { label: string; cls: string } | null {
  if (!party) return null;
  const p = party.toLowerCase();
  if (p.includes('republican'))
    return { label: party, cls: 'border-red-500 text-red-600 dark:text-red-400' };
  if (p.includes('democratic') || p.includes('working families') || p.startsWith('progressive'))
    return { label: party, cls: 'border-blue-500 text-blue-600 dark:text-blue-400' };
  return { label: party, cls: 'border-border-default text-text-muted' };
}

function ChampionBills({ personId }: { personId: string }) {
  const [bills, setBills] = useState<ChampionBill[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchChampionBills(personId)
      .then((d) => !cancelled && setBills(d))
      .catch(() => !cancelled && setBills([]));
    return () => {
      cancelled = true;
    };
  }, [personId]);

  if (!bills) return <div className="h-10 animate-pulse rounded bg-bg-tertiary" />;
  return (
    <div className="space-y-1.5 pt-2">
      {bills.map((b, i) => (
        <div key={b.bill_id ?? i} className="flex items-center justify-between gap-2 text-xs">
          <span className="text-text-secondary">
            {[b.state, b.bill_number].filter(Boolean).join(' ')}
            {b.instrument && <span className="text-text-muted"> · {formatInstrumentType(b.instrument)}</span>}
            {b.enacted && <span className="text-[rgb(var(--green-accent))]"> · enacted</span>}
          </span>
          {b.source_url ? (
            <a
              href={b.source_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => track('insights_champion_source', { person_id: personId, bill_id: b.bill_id })}
              className="shrink-0 text-[rgb(var(--green-accent))] hover:underline"
            >
              source ↗
            </a>
          ) : (
            <span className="shrink-0 italic text-text-muted opacity-70">no source</span>
          )}
        </div>
      ))}
    </div>
  );
}

function ChampionCard({ champ }: { champ: ChampionSummary }) {
  const [open, setOpen] = useState(false);
  const chip = partyChip(champ.party);
  const seat = [champ.chamber, champ.district ? `Dist. ${champ.district}` : null].filter(Boolean).join(' · ');
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-3">
      <button
        onClick={() => {
          setOpen((o) => !o);
          if (!open && champ.person_id) track('insights_champion_expand', { person_id: champ.person_id });
        }}
        className="flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-text-primary text-sm">{fixEncoding(champ.name ?? '—')}</span>
            {chip && <span className={`rounded-full border px-1.5 py-0.5 text-[10px] ${chip.cls}`}>{chip.label}</span>}
          </div>
          <div className="text-text-muted text-xs mt-0.5">
            {champ.states.join(', ')}{seat ? ` · ${seat}` : ''}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-text-primary text-sm font-bold">{champ.primary_sponsorships}</div>
          <div className="text-text-muted text-[10px]">lead bills</div>
        </div>
      </button>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-text-muted">
        {champ.cosponsorships > 0 && <span>+{champ.cosponsorships} co-sponsored</span>}
        {champ.success_rate != null && <span>{(champ.success_rate * 100).toFixed(0)}% enacted</span>}
        {champ.instruments.length > 0 && (
          <span>{champ.instruments.map(formatInstrumentType).join(', ')}</span>
        )}
        {champ.person_id && (
          <button onClick={() => setOpen((o) => !o)} className="text-[rgb(var(--green-accent))] hover:underline">
            {open ? 'hide bills' : `${champ.total_ce_bills} bills + sources`}
          </button>
        )}
      </div>
      {open && champ.person_id && <ChampionBills personId={champ.person_id} />}
    </div>
  );
}

export function ChampionRoster() {
  const [state, setState] = useState<string>('');
  const [champs, setChamps] = useState<ChampionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setChamps(null);
    setError(null);
    fetchChampions({ state: state || undefined, limit: 50 })
      .then((d) => !cancelled && setChamps(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : 'Could not load the roster.'));
    return () => {
      cancelled = true;
    };
  }, [state]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <label className="text-text-muted text-xs">State</label>
        <select
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            track('insights_roster_state', { state: e.target.value || 'all' });
          }}
          className="rounded-md border border-border-default bg-bg-primary px-2 py-1 text-xs text-text-secondary"
        >
          <option value="">All states (top 50)</option>
          {STATE_OPTIONS.map((s) => (
            <option key={s} value={s}>{STATE_NAMES[s]}</option>
          ))}
        </select>
      </div>

      {error ? (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : !champs ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-bg-tertiary" />
          ))}
        </div>
      ) : champs.length === 0 ? (
        <p className="text-text-muted text-sm">No active champions tracked for this state yet.</p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {champs.map((c) => (
            <ChampionCard key={c.person_id ?? c.name} champ={c} />
          ))}
        </div>
      )}

      <p className="text-text-muted text-xs leading-relaxed">
        Legislators currently in office who have sponsored advancing circular-economy bills, ranked by
        lead sponsorships. &ldquo;% enacted&rdquo; is how many of their sponsored CE bills became law. Sponsorship
        is from the OpenStates record; in-office status is as of the latest data snapshot.
      </p>
    </div>
  );
}
