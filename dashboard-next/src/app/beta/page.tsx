'use client';
import { useMemo, useState } from 'react';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { LockIcon } from '@/components/ui/icons';
import { useAuth } from '@/components/auth/AuthContext';
import { useBills } from '@/hooks/useBills';
import { STATE_NAMES, formatInstrumentType, formatDate, fixEncoding } from '@/lib/utils';
import type { BillSummary } from '@/lib/types';
import { LegislativeTimeline } from '@/components/beta/LegislativeTimeline';

/**
 * Hidden internal preview for features in development — gated exactly like /admin (a signed-in
 * non-admin gets a plain 404, and it's not linked in nav). Things land here while we decide if
 * they're trustworthy enough for the live site. First resident: the Weakening Watch, moved off
 * the public state pages because a mislabeled "weakens" is more harmful than no flag.
 */
export default function BetaPage() {
  const { user, loading, isAdmin, openAuth } = useAuth();

  if (loading) return <Shell><p className="text-text-muted text-sm">Loading…</p></Shell>;
  if (!user) {
    return (
      <Shell>
        <div className="rounded-xl border border-green-accent bg-green-dark/20 p-8 text-center space-y-3 max-w-xl mx-auto">
          <LockIcon className="text-2xl text-green-accent mx-auto" />
          <h2 className="font-serif text-xl text-text-primary">Sign in required</h2>
          <button
            onClick={openAuth}
            className="inline-flex items-center gap-2 rounded-lg bg-green-accent text-bg-primary px-5 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity"
          >
            Sign in
          </button>
        </div>
      </Shell>
    );
  }
  if (!isAdmin) {
    return <Shell><p className="text-text-muted text-sm text-center">404 — This page could not be found.</p></Shell>;
  }
  return (
    <Shell>
      <LegislativeTimeline />
      <WeakeningWatch />
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="p-6 space-y-8 max-w-5xl mx-auto">
      <GazetteHeader title="Beta" subtitle="Features in development — internal preview, not on the live site." />
      {children}
    </div>
  );
}

// ── Weakening Watch ───────────────────────────────────────────────────────────

function WeakeningWatch() {
  const { data: bills = [], isLoading } = useBills({ ce_relevant: true, limit: 5000 });
  const [stateFilter, setStateFilter] = useState('');

  const weakening = useMemo(() => {
    return bills
      .filter(b => b.policy_stance === 'weakens')
      .filter(b => !stateFilter || b.state === stateFilter)
      // Lowest relevance confidence first — the most suspect calls float to the top for review.
      .sort((a, b) => (a.confidence_score ?? 1) - (b.confidence_score ?? 1));
  }, [bills, stateFilter]);

  const states = useMemo(
    () => Array.from(new Set(bills.filter(b => b.policy_stance === 'weakens').map(b => b.state))).sort(),
    [bills],
  );

  return (
    <section className="rounded-xl border border-border-default bg-bg-secondary p-5 space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="font-serif text-lg text-text-primary">
          Weakening Watch <span className="text-text-muted text-sm">({weakening.length})</span>
        </h2>
        <select
          value={stateFilter}
          onChange={e => setStateFilter(e.target.value)}
          className="rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-primary focus:border-green-accent focus:outline-none"
        >
          <option value="">All states</option>
          {states.map(s => <option key={s} value={s}>{s} — {STATE_NAMES[s] ?? s}</option>)}
        </select>
      </div>

      {/* Honest caveat — the whole reason this is internal-only. */}
      <div className="rounded-lg border border-amber-400/40 bg-amber-400/5 p-3 text-xs text-text-secondary leading-relaxed">
        <span className="text-amber-400 font-medium uppercase tracking-wider text-[10px]">Unverified</span>{' '}
        These are AI-flagged <span className="text-text-primary">&ldquo;weakens&rdquo;</span> calls. The confidence shown
        is the bill&rsquo;s <span className="text-text-primary">relevance</span> score —{' '}
        <span className="text-text-primary">there is no separate confidence for the stance</span>, and the call is made
        from the bill caption + first 2,000 characters. Measured precision is{' '}
        <span className="text-text-primary">~75%</span> (scripts/measure_stance_precision.py) — about 1 in 4 is wrong,
        and the errors skew toward branding EPR-<span className="text-text-primary">establishing</span> bills as harmful.
        Treat as a review queue, not a verdict: verify against full text, then mark the bill{' '}
        <span className="text-text-primary">reviewed</span> to earn it a public red flag. Known false positives:
        RI HB-7023 (establishes packaging EPR), CA SB-1341 (deposit-pricing calibration, not a rollback).
      </div>

      {isLoading ? (
        <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="h-10 bg-bg-primary rounded animate-pulse" />)}</div>
      ) : weakening.length === 0 ? (
        <p className="text-text-muted text-sm">No bills flagged as weakening{stateFilter ? ` in ${stateFilter}` : ''}.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead><tr className="border-b border-border-default text-left text-text-muted">
              <th className="px-2 py-1.5 font-medium">State</th>
              <th className="px-2 py-1.5 font-medium">Bill</th>
              <th className="px-2 py-1.5 font-medium">Title</th>
              <th className="px-2 py-1.5 font-medium">Instrument</th>
              <th className="px-2 py-1.5 font-medium">Status</th>
              <th className="px-2 py-1.5 font-medium whitespace-nowrap">Rel. conf.</th>
              <th className="px-2 py-1.5 font-medium">Why (AI)</th>
            </tr></thead>
            <tbody>
              {weakening.map(b => <WeakeningRow key={b.id} b={b} />)}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function WeakeningRow({ b }: { b: BillSummary }) {
  const conf = b.confidence_score ?? null;
  const low = conf !== null && conf < 0.85;
  return (
    <tr className="border-b border-border-default/50 align-top">
      <td className="px-2 py-1.5 text-green-accent font-mono">{b.state}</td>
      <td className="px-2 py-1.5 text-text-secondary font-mono whitespace-nowrap">{b.bill_number ?? '—'}</td>
      <td className="px-2 py-1.5 text-text-primary max-w-[18rem]">{fixEncoding(b.title) || '—'}</td>
      <td className="px-2 py-1.5 text-text-muted whitespace-nowrap">{formatInstrumentType(b.instrument_type)}</td>
      <td className="px-2 py-1.5 text-text-muted whitespace-nowrap">{b.status ?? '—'}</td>
      <td className={`px-2 py-1.5 tabular-nums whitespace-nowrap ${low ? 'text-amber-400' : 'text-text-secondary'}`}>
        {conf !== null ? conf.toFixed(2) : '—'}
      </td>
      <td className="px-2 py-1.5 text-text-muted max-w-[20rem]">
        {b.ai_summary || '—'}
        {b.last_action_date && <span className="block text-[10px] text-text-muted/70">last action {formatDate(b.last_action_date)}</span>}
      </td>
    </tr>
  );
}
