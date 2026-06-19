'use client';

import { useEffect, useMemo, useState } from 'react';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { BillTimelineChart } from '@/components/insights/BillTimelineChart';
import { StanceMomentumChart } from '@/components/insights/StanceMomentumChart';
import { InstrumentMaterialMatrix } from '@/components/insights/InstrumentMaterialMatrix';
import { StateGapTable } from '@/components/insights/StateGapTable';
import { StateCyclesView } from '@/components/insights/StateCyclesView';
import { ChampionRoster } from '@/components/insights/ChampionRoster';
import { RealWorldImpact } from '@/components/insights/RealWorldImpact';
import { OutliersPlaylist } from '@/components/insights/OutliersPlaylist';
import { fetchBillTimeline } from '@/lib/api';
import { formatInstrumentType } from '@/lib/utils';
import { track } from '@/lib/analytics';
import type { BillTimelinePoint } from '@/lib/types';

// In-scope circular-economy instruments, canonical list mirrors INSTRUMENT_TYPES in
// components/bills/BillFilters.tsx. `undefined` is the "All instruments" view (the running total).
const INSTRUMENT_OPTIONS: Array<{ value: string | undefined; label: string }> = [
  { value: undefined, label: 'All instruments' },
  ...['epr', 'deposit_return', 'right_to_repair', 'recycled_content', 'incentives', 'labeling', 'preemption', 'other'].map(
    (v) => ({ value: v, label: formatInstrumentType(v) }),
  ),
];

/**
 * Insights — a curated, link-shareable briefing room for legislative staffers. Hidden from the
 * main nav (reachable by URL only, like /admin) so we can hand it out deliberately. Structured as
 * stacked sections so we can keep adding visualizations, flagship-bill spotlights, and field notes
 * as patterns emerge. The first section is the EPR "shots on goal" timeline.
 */

function Section({
  title,
  kicker,
  children,
}: {
  title: string;
  kicker?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border-default bg-bg-secondary p-5 sm:p-6 space-y-4">
      <div>
        {kicker && (
          <p className="text-[rgb(var(--green-accent))] text-xs font-semibold uppercase tracking-wider">
            {kicker}
          </p>
        )}
        <h2 className="font-serif text-xl text-text-primary">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-4">
      <div className="font-bold text-text-primary text-2xl">{value}</div>
      <div className="text-text-muted text-xs mt-0.5">{label}</div>
    </div>
  );
}

export default function InsightsPage() {
  const [points, setPoints] = useState<BillTimelinePoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [instrument, setInstrument] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetchBillTimeline({ instrument_type: instrument })
      .then((d) => {
        if (!cancelled) setPoints(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load timeline.');
      });
    return () => {
      cancelled = true;
    };
  }, [instrument]);

  // Headline figures: total laws on the books, and the most recent full year's introductions.
  const stats = useMemo(() => {
    if (!points) return null;
    const enacted = points.filter((p) => p.status === 'enacted').reduce((s, p) => s + p.count, 0);
    const introYears = points.filter((p) => p.status === 'introduced');
    const peak = introYears.reduce(
      (best, p) => (p.count > best.count ? p : best),
      { year: 0, count: 0 } as BillTimelinePoint,
    );
    const firstYear = points.reduce((m, p) => Math.min(m, p.year), Infinity);
    return { enacted, peak, firstYear: Number.isFinite(firstYear) ? firstYear : null };
  }, [points]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <GazetteHeader
        title="Insights"
        subtitle="Field notes on the circular-economy policy landscape — for the people writing it."
      />

      <Section
        kicker="Timeline"
        title={
          instrument
            ? `Shots on goal: ${formatInstrumentType(instrument)} bills, introduced through enacted`
            : 'Shots on goal: circularity bills, introduced through enacted'
        }
      >
        <p className="text-text-secondary text-sm leading-relaxed">
          The headline line is the running count of circular-economy laws on the books — across every
          instrument we track (EPR, deposit-return, right-to-repair, recycled-content, and more), not
          EPR alone. Toggle the upstream statuses to see the full pipeline — how many bills get
          introduced, advance through committee, and pass a chamber for each one that finally becomes
          law. Pick a policy instrument to slice the same total.
        </p>

        {/* Instrument selector — another view on the same running total. */}
        <div className="flex flex-wrap gap-2">
          {INSTRUMENT_OPTIONS.map((opt) => {
            const active = opt.value === instrument;
            return (
              <button
                key={opt.label}
                onClick={() => {
                  setInstrument(opt.value);
                  track('insights_timeline_instrument', { instrument: opt.value ?? 'all' });
                }}
                aria-pressed={active}
                className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                  active
                    ? 'border-[rgb(var(--green-accent))] bg-[rgb(var(--green-accent))] text-white'
                    : 'border-border-default bg-bg-primary text-text-secondary hover:bg-bg-tertiary'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        <p className="text-text-muted text-xs">
          <span className="font-semibold text-text-secondary">Other</span> — in-scope circular-economy
          bills that don&apos;t map to one of the named instruments above (e.g. disposal/landfill
          bans, product or packaging standards, reuse/refill mandates, and organics-diversion or
          composting requirements).
        </p>

        <OutliersPlaylist />

        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Stat
              value={stats.enacted.toLocaleString()}
              label={instrument ? `${formatInstrumentType(instrument)} laws enacted to date` : 'Circular-economy laws enacted to date'}
            />
            {stats.peak.year > 0 && (
              <Stat
                value={stats.peak.count.toLocaleString()}
                label={`Bills introduced in ${stats.peak.year} (peak year)`}
              />
            )}
            {stats.firstYear && <Stat value={`${stats.firstYear}`} label="Earliest law tracked" />}
          </div>
        )}

        {error ? (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        ) : !points ? (
          <div className="h-[360px] w-full animate-pulse rounded-lg bg-bg-tertiary" />
        ) : (
          <BillTimelineChart points={points} instrument={instrument} />
        )}
      </Section>

      <Section
        kicker="Momentum"
        title="Policy momentum: advancing vs. being rolled back"
      >
        <p className="text-text-secondary text-sm leading-relaxed">
          Counting bills misses the most important question: which direction are they pushing? Above
          the line are bills that <em>establish or strengthen</em> a circular-economy obligation; below
          it, bills that <em>exempt, narrow, repeal, or preempt</em> one. Slice by instrument to see
          where the field is gaining ground and where the backlash is concentrated.
        </p>
        <StanceMomentumChart />
      </Section>

      <Section
        kicker="Coverage"
        title="Where instruments meet materials"
      >
        <p className="text-text-secondary text-sm leading-relaxed">
          Which policy tools have been aimed at which materials. The dense cells are well-trodden
          ground; the empty ones are the white space — a material with deposit-return or labeling
          precedent but no EPR yet is often where the next wave of bills lands.
        </p>
        <InstrumentMaterialMatrix />
      </Section>

      <Section
        kicker="Battle of the bills"
        title="Does each state pass circular-economy bills above or below its own average?"
      >
        <p className="text-text-secondary text-sm leading-relaxed">
          A state&apos;s circular-economy passage rate means little in isolation — Minnesota passes ~1% of{' '}
          <em>everything</em>. So we compare each state&apos;s advancing-CE rate against its <em>all-bills</em>{' '}
          baseline (computed from the full legislative record). The gap is the real signal: where CE bills
          clear the bar more readily than the average bill, and where they hit contested-policy drag.
        </p>
        <StateGapTable />
      </Section>

      <Section
        kicker="By legislative cycle"
        title="Is a state's circular-economy gap widening or closing?"
      >
        <p className="text-text-secondary text-sm leading-relaxed">
          The same gap, broken out by two-year legislative cycle, so you can see the trend — where
          circular-economy bills are gaining ground session over session, and where momentum has stalled.
          Pick a state to trace its cycles.
        </p>
        <StateCyclesView />
      </Section>

      <Section
        kicker="Champions"
        title="Who's carrying these bills"
      >
        <p className="text-text-secondary text-sm leading-relaxed">
          The legislators currently in office moving circular-economy bills, ranked by how many they
          lead-sponsor. Pick a state to see its delegation; expand anyone to see their bills and sources.
        </p>
        <div className="rounded-lg border border-border-default bg-bg-primary p-3 text-sm text-text-secondary">
          <span className="font-semibold text-text-primary">One non-obvious pattern:</span> bipartisan bills
          (a sponsor from each party) become law at roughly <span className="text-text-primary font-semibold">
          twice the rate</span> of single-party bills (~17% vs ~9%) — the rare Republican co-sponsor is the
          strongest signal a CE bill will pass.
        </div>
        <ChampionRoster />
      </Section>

      <Section
        kicker="Field notes"
        title="Real-world impact: what enacted laws actually did"
      >
        <p className="text-text-secondary text-sm leading-relaxed">
          Everywhere else we track what a law <em>requires</em>. This is what enacted laws have been
          documented to <em>produce</em> — measured outcomes, positive and negative, each anchored to
          a citation. Measured impacts are rare and uneven, so the list grows as evidence surfaces.
        </p>
        <RealWorldImpact />
      </Section>

      {/* Future sections (more flagship-bill spotlights, best practices) slot in here as
          additional <Section> blocks — the page is built to grow. */}
    </div>
  );
}
