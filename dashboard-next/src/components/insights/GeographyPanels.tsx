'use client';

import { StateGapTable } from './StateGapTable';
import { StateCyclesView } from './StateCyclesView';
import { ChampionRoster } from './ChampionRoster';

/**
 * The US Geography views — passage-rate gap, the same gap per legislative cycle, and the champion
 * roster. Extracted out of the public Insights page and moved behind /admin: all three read
 * sponsor/vote analysis derived from the OpenStates dump, which is only backfilled for US states and
 * isn't a shipped product yet. They are staging-ground work, not member-facing findings, so they now
 * live in the admin console's "Pending Insights" tab alongside the unreviewed outcome queue.
 *
 * Kept as its own component (rather than inlined into the admin page) so promoting a view back onto
 * /insights is an import, not a rewrite — which is the direction of travel once the ingestion behind
 * it ships for enough jurisdictions to be worth selling.
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
    <section className="rounded-xl border border-border-default bg-bg-secondary p-5 space-y-4">
      <div>
        {kicker && (
          <p className="text-[rgb(var(--green-accent))] text-xs font-semibold uppercase tracking-wider">
            {kicker}
          </p>
        )}
        <h2 className="font-serif text-lg text-text-primary">{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function GeographyPanels() {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border-default bg-bg-primary px-4 py-3 text-sm text-text-secondary">
        <span className="font-semibold text-text-primary">United States only.</span> These views rank
        jurisdictions against a passage-rate baseline and sponsor record that we only have for US
        states — so they don&apos;t honor the region filter. An equivalent for EU member states is a
        future addition.
      </div>

      <Section kicker="Atlas Circular" title="Where circular-economy bills beat the odds">
        <p className="text-text-secondary text-body leading-relaxed">
          A state&apos;s circular-economy passage rate means little in isolation — Minnesota passes ~1% of{' '}
          <em>everything</em>. So we compare each state&apos;s advancing-CE rate against its <em>all-bills</em>{' '}
          baseline (computed from the full legislative record). The gap is the real signal: where CE bills
          clear the bar more readily than the average bill, and where they hit contested-policy drag.
        </p>
        <StateGapTable />
      </Section>

      <Section kicker="By legislative cycle" title="Is a state's circular-economy gap widening or closing?">
        <p className="text-text-secondary text-body leading-relaxed">
          The same gap, broken out by two-year legislative cycle, so you can see the trend — where
          circular-economy bills are gaining ground session over session, and where momentum has stalled.
          Pick a state to trace its cycles.
        </p>
        <StateCyclesView />
      </Section>

      <Section kicker="Champions" title="Who's carrying these bills">
        <p className="text-text-secondary text-body leading-relaxed">
          The legislators currently in office moving circular-economy bills, ranked by how many they
          lead-sponsor. Pick a state to see its delegation; expand anyone to see their bills and sources.
        </p>
        <div className="rounded-lg border border-border-default bg-bg-primary p-3 text-body text-text-secondary">
          <span className="font-semibold text-text-primary">One non-obvious pattern:</span> bipartisan bills
          (a sponsor from each party) become law at roughly <span className="text-text-primary font-semibold">
          twice the rate</span> of single-party bills (~17% vs ~9%) — the rare Republican co-sponsor is the
          strongest signal a CE bill will pass.
        </div>
        <ChampionRoster />
      </Section>
    </div>
  );
}
