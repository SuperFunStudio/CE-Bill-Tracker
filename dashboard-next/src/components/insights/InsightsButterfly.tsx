'use client';

import { useEffect, useMemo, useState } from 'react';
import { fetchButterfly } from '@/lib/api';
import { useBills } from '@/hooks/useBills';
import type { ButterflyCounts, ButterflyStatus } from '@/lib/types';
import { RegionFilter, REGION_CODES, regionLabel } from './RegionFilter';
import { BUTTERFLY_NODES, ButterflyDiagram } from './ButterflyDiagram';
import { ButterflyExplorer } from './ButterflyExplorer';
import { track } from '@/lib/analytics';

/**
 * Insights "Butterfly" tab: where a jurisdiction's law sits on the circular-economy butterfly.
 *
 * One region: the full diagram re-scoped to the picked region(s); empty = the whole corpus.
 * Compare: two jurisdictions as coverage fingerprints side by side, plus a step table that names the
 * gaps (steps one covers and the other doesn't). Defaults to law in force: introduced bills dominate
 * some places (US states) and barely exist in others (EU member states, tracked once they're law), so
 * only enacted law compares across borders.
 */

function useButterfly(regions: string | undefined, status: ButterflyStatus) {
  const [state, setState] = useState<{ data: ButterflyCounts | null; error: boolean }>({ data: null, error: false });
  useEffect(() => {
    let cancelled = false;
    setState(s => ({ data: s.data, error: false }));   // keep the old drawing while the new scope loads
    fetchButterfly({ regions, status })
      .then(d => { if (!cancelled) setState({ data: d, error: false }); })
      .catch(() => { if (!cancelled) setState({ data: null, error: true }); });
    return () => { cancelled = true; };
  }, [regions, status]);
  return state;
}

function Seg<T extends string>({ value, options, onChange, label }: {
  value: T; options: Array<[T, string]>; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-md border border-border-default">
      {options.map(([v, text], i) => (
        <button
          key={v}
          type="button"
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={`px-3 py-1.5 text-sm ${i ? 'border-l border-border-default' : ''} ${
            value === v ? 'bg-text-primary text-bg-primary' : 'bg-bg-secondary text-text-secondary hover:text-text-primary'
          }`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

function RegionSelect({ id, value, onChange, label }: { id: string; value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-sm">
      <span className="text-text-muted text-xs uppercase tracking-wide">{label}</span>
      <select
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="h-8 rounded-md border border-border-default bg-bg-secondary px-2 text-sm text-text-primary"
      >
        {REGION_CODES.map(c => <option key={c} value={c}>{regionLabel(c)}</option>)}
      </select>
    </label>
  );
}

const STEP_ROWS = BUTTERFLY_NODES.filter(n => !n.noSource);
const BOX_ROWS: Array<[string, string]> = [['parts', 'Parts manufacturer · chemical restrictions'], ['service', 'Service provider · labeling']];

export function InsightsButterfly() {
  const [mode, setMode] = useState<'one' | 'compare'>('one');
  const [status, setStatus] = useState<ButterflyStatus>('enacted');
  const [regions, setRegions] = useState<string[]>([]);
  const [a, setA] = useState('FR');
  const [b, setB] = useState('DE');

  // One region: the zoomable explorer over the snapshot-backed bill list (it carries butterfly_steps),
  // filtered to the picked regions. Memoised so the explorer only resets its zoom on a real scope change.
  const { data: allBills } = useBills({ ce_relevant: true, limit: 5000, regions: 'all' });
  const regionKey = regions.join(',');
  const oneBills = useMemo(
    () => (allBills ? allBills.filter(b => !regions.length || regions.includes(b.region)) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allBills, regionKey],
  );
  const inScope = useMemo(
    () => (oneBills ?? []).filter(b => status === 'all' || ['enacted', 'active'].includes(b.status ?? '')).length,
    [oneBills, status],
  );
  const left = useButterfly(mode === 'compare' ? a : undefined, status);
  const right = useButterfly(mode === 'compare' ? b : undefined, status);
  const noun = status === 'enacted' ? 'laws in force' : 'laws and bills';

  const setModeTracked = (m: 'one' | 'compare') => { setMode(m); track('insights_butterfly_mode', { mode: m }); };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Seg label="View" value={mode} onChange={setModeTracked} options={[['one', 'One region'], ['compare', 'Compare two']]} />
        <Seg label="Status" value={status} onChange={setStatus} options={[['enacted', 'In force'], ['all', 'All bills']]} />
        {mode === 'one' ? (
          <RegionFilter selected={regions} onChange={setRegions} variant="toolbar" />
        ) : (
          <>
            <RegionSelect id="bf-a" label="A" value={a} onChange={v => { setA(v); track('insights_butterfly_compare', { a: v, b }); }} />
            <RegionSelect id="bf-b" label="B" value={b} onChange={v => { setB(v); track('insights_butterfly_compare', { a, b: v }); }} />
          </>
        )}
      </div>

      {mode === 'one' ? (
        <div className="space-y-3">
          <p className="text-sm text-text-secondary">
            {oneBills
              ? <><span className="font-mono text-text-primary">{inScope.toLocaleString()}</span> {noun} in {regions.length ? regions.map(regionLabel).join(', ') : 'every region'}. Each step counts the laws that sit there; hatched steps have none. Click a step to see its bills.</>
              : 'Loading…'}
          </p>
          <ButterflyExplorer
            bills={oneBills}
            groupByCountry={regions.length > 0}
            baseStatus={status === 'enacted' ? 'enacted' : 'all'}
            haloColor="var(--bg-secondary)"
          />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            {([[a, left], [b, right]] as const).map(([code, s], i) => (
              <div key={i} className="rounded-lg border border-border-default bg-bg-primary p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <h3 className="font-serif text-lg text-text-primary">{regionLabel(code)}</h3>
                  <span className="text-xs text-text-muted">
                    {s.data ? <><span className="font-mono text-text-primary">{s.data.total.toLocaleString()}</span> {noun}</> : s.error ? 'unavailable' : '…'}
                  </span>
                </div>
                <ButterflyDiagram counts={s.data} compact unit={noun} ariaLabel={`Coverage fingerprint for ${regionLabel(code)}`} />
              </div>
            ))}
          </div>
          <CompareTable aName={regionLabel(a)} bName={regionLabel(b)} a={left.data} b={right.data} />
        </div>
      )}
    </div>
  );
}

/** Step-by-step counts for the two jurisdictions, with the one-sided gaps called out. */
function CompareTable({ aName, bName, a, b }: { aName: string; bName: string; a: ButterflyCounts | null; b: ButterflyCounts | null }) {
  if (!a || !b) return null;
  const rows: Array<[string, string]> = [...STEP_ROWS.map(n => [n.id, n.name] as [string, string]), ...BOX_ROWS];
  const onlyA = rows.filter(([id]) => (a.steps[id] ?? 0) > 0 && !(b.steps[id] ?? 0)).map(([, n]) => n);
  const onlyB = rows.filter(([id]) => (b.steps[id] ?? 0) > 0 && !(a.steps[id] ?? 0)).map(([, n]) => n);
  return (
    <div className="space-y-3">
      {(onlyA.length > 0 || onlyB.length > 0) && (
        <div className="grid gap-2 text-sm sm:grid-cols-2">
          <p className="text-text-secondary"><span className="text-text-primary font-medium">Only {aName}:</span> {onlyA.length ? onlyA.join(', ') : 'none'}</p>
          <p className="text-text-secondary"><span className="text-text-primary font-medium">Only {bName}:</span> {onlyB.length ? onlyB.join(', ') : 'none'}</p>
        </div>
      )}
      <div className="overflow-x-auto rounded-lg border border-border-default">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-text-muted border-b border-border-default">
              <th className="px-3 py-2 font-medium">Step</th>
              <th className="px-3 py-2 font-medium text-right">{aName}</th>
              <th className="px-3 py-2 font-medium text-right">{bName}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([id, name]) => {
              const x = a.steps[id] ?? 0, y = b.steps[id] ?? 0;
              const gap = (x === 0) !== (y === 0);
              return (
                <tr key={id} className={`border-b border-border-default last:border-0 ${gap ? 'bg-[rgb(var(--green-accent))]/5' : ''}`}>
                  <td className="px-3 py-1.5 text-text-secondary">{name}</td>
                  <td className={`px-3 py-1.5 text-right font-mono ${x ? 'text-text-primary' : 'text-text-muted'}`}>{x ? x.toLocaleString() : '—'}</td>
                  <td className={`px-3 py-1.5 text-right font-mono ${y ? 'text-text-primary' : 'text-text-muted'}`}>{y ? y.toLocaleString() : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
