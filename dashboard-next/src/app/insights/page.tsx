'use client';

import { useEffect, useMemo, useState } from 'react';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { BillTimelineChart } from '@/components/insights/BillTimelineChart';
import { LawsInForceChart } from '@/components/insights/LawsInForceChart';
import { StanceMomentumChart } from '@/components/insights/StanceMomentumChart';
import { CollectionTargetBasisChart } from '@/components/insights/CollectionTargetBasisChart';
import { InstrumentMaterialMatrix } from '@/components/insights/InstrumentMaterialMatrix';
import { WorldCoverageMap } from '@/components/insights/WorldCoverageMap';
import { RegionInstrumentMatrix } from '@/components/insights/RegionInstrumentMatrix';
import { StateGapTable } from '@/components/insights/StateGapTable';
import { StateCyclesView } from '@/components/insights/StateCyclesView';
import { ChampionRoster } from '@/components/insights/ChampionRoster';
import { RealWorldImpact } from '@/components/insights/RealWorldImpact';
import { OutliersPlaylist } from '@/components/insights/OutliersPlaylist';
import { MaterialRegimeMap } from '@/components/insights/MaterialRegimeMap';
import { useRegion } from '@/components/layout/RegionContext';
import { useAuth } from '@/components/auth/AuthContext';
import Link from 'next/link';
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

// Tabs group the visualizations so the page isn't one long scroll. The region filter applies to the
// region-generalizable tabs (Momentum, Coverage); Geography is US-only by construction — see below.
const TABS = [
  { id: 'world', label: 'World' },
  { id: 'momentum', label: 'Momentum' },
  { id: 'coverage', label: 'Coverage' },
  { id: 'geography', label: 'Geography · US' },
  { id: 'impact', label: 'Impact' },
] as const;
type TabId = (typeof TABS)[number]['id'];

/**
 * Insights — a curated, link-shareable briefing room for legislative staffers. A Pro membership
 * feature: surfaced in the nav for Pro members/admins, gated with the standard sign-up-or-purchase
 * card for everyone else (still reachable by URL, where the gate does the selling). Organized into
 * tabs (World / Momentum / Coverage / Geography / Impact) with a region filter on the
 * cross-jurisdiction views.
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
  const [tab, setTab] = useState<TabId>('world');
  // The global region filter (the bar under the nav) scopes the timeline + momentum + coverage.
  const { regionsParam: regionsCsv } = useRegion();
  const { isPro, isAdmin, user, openAuth } = useAuth();

  const [points, setPoints] = useState<BillTimelinePoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [instrument, setInstrument] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setPoints(null);
    fetchBillTimeline({ instrument_type: instrument, regions: regionsCsv })
      .then((d) => {
        if (!cancelled) setPoints(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load timeline.');
      });
    return () => {
      cancelled = true;
    };
  }, [instrument, regionsCsv]);

  // Headline figures: total laws on the books, and the most recent full year's introductions.
  // points are region-grouped now, so sum across regions for the aggregate stat.
  const stats = useMemo(() => {
    if (!points) return null;
    const enacted = points.filter((p) => p.status === 'enacted').reduce((s, p) => s + p.count, 0);
    const introByYear = new Map<number, number>();
    for (const p of points) {
      if (p.status === 'introduced') introByYear.set(p.year, (introByYear.get(p.year) ?? 0) + p.count);
    }
    let peak = { year: 0, count: 0 };
    for (const [year, count] of introByYear) if (count > peak.count) peak = { year, count };
    const firstYear = points.reduce((m, p) => Math.min(m, p.year), Infinity);
    return { enacted, peak, firstYear: Number.isFinite(firstYear) ? firstYear : null };
  }, [points]);

  // Insights is a Pro membership feature — non-members get the same sign-up-or-purchase gate as
  // Federal Actions / Packaging Studio (see federal/page.tsx). Kept after the hooks above so the
  // rules-of-hooks order is stable; the timeline fetch is a public snapshot, so it's harmless.
  if (!isPro && !isAdmin) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10">
        <GazetteHeader
          title="Insights"
          subtitle="Field notes on the circular-economy policy landscape — for the people writing it."
        />
        <div className="surface-card p-6 mt-6 space-y-3 text-center">
          <h2 className="font-serif text-xl text-text-primary">A Pro membership feature</h2>
          <p className="text-text-secondary max-w-xl mx-auto">
            The Insights briefing room — global coverage maps, policy momentum and stance charts,
            state scorecards, and documented real-world outcomes — is included with a Pro membership.
          </p>
          <div className="flex justify-center gap-2 pt-1">
            {!user && (
              <button
                type="button"
                onClick={openAuth}
                className="rounded-full border border-border-default px-5 py-2 text-sm text-text-secondary hover:text-text-primary"
              >
                Sign in
              </button>
            )}
            <Link href="/pricing" className="rounded-full bg-green-accent px-5 py-2 text-sm font-medium text-bg-primary hover:opacity-90">
              See memberships
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <GazetteHeader
        title="Insights"
        subtitle="Field notes on the circular-economy policy landscape — for the people writing it."
      />

      {/* Tab bar. The region filter is the global one (the bar under the nav). */}
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border-default">
        <div className="flex flex-wrap gap-1 -mb-px" role="tablist">
          {TABS.map((t) => {
            const active = t.id === tab;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={active}
                onClick={() => {
                  setTab(t.id);
                  track('insights_tab', { tab: t.id });
                }}
                className={`border-b-2 px-4 py-2 text-sm transition-colors ${
                  active
                    ? 'border-[rgb(var(--green-accent))] text-text-primary font-semibold'
                    : 'border-transparent text-text-muted hover:text-text-secondary'
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {tab === 'world' && (
        <>
          <div className="rounded-lg border border-border-default bg-bg-primary px-4 py-3 text-sm text-text-secondary">
            <span className="font-semibold text-text-primary">Every region.</span> This is the cross-jurisdiction
            overview — it spans the whole tracked corpus regardless of the region filter above. Use it to compare
            jurisdictions, then click into one to scope the rest of the site.
          </div>

          <Section kicker="Global coverage" title="Circular-economy laws in force around the world">
            <p className="text-text-secondary text-body leading-relaxed">
              The reach of enacted circular-economy law, jurisdiction by jurisdiction — the United States and
              its states, the EU-central body binding all 27 members, and the national laws we track across
              Europe, Asia-Pacific, and the Americas. Each country is shaded by how many in-force laws apply
              there; hover for the count, or click to filter the whole site to that jurisdiction.
            </p>
            <WorldCoverageMap />
          </Section>

          <Section kicker="Regulatory personality" title="Which instruments each jurisdiction leans on">
            <p className="text-text-secondary text-body leading-relaxed">
              Every jurisdiction regulates circularity with a different toolkit. Read across a row to see the
              mix — where a region reaches first for extended-producer-responsibility, where for deposit-return,
              recycled-content mandates, or right-to-repair. The contrasts are the story: the EU&apos;s ecodesign
              tilt, the US EPR build-out, France&apos;s repairability push.
            </p>
            <RegionInstrumentMatrix />
          </Section>
        </>
      )}

      {tab === 'momentum' && (
        <>
          <Section kicker="Laws on the books" title="Circular-economy laws in force over time">
            <p className="text-text-secondary text-body leading-relaxed">
              The running count of enacted laws on the books, by the year each came into force. Unlike
              the pipeline view below (a US introduced-through-enacted funnel), this works for every
              jurisdiction — including the EU and national regulations that have no legislative pipeline —
              so it&apos;s the one momentum view you can compare across regions. Pick regions in the filter
              above to trace their trajectories side by side.
            </p>
            <LawsInForceChart regions={regionsCsv} />
          </Section>

          <Section
            kicker="Timeline"
            title={
              instrument
                ? `Shots on goal: ${formatInstrumentType(instrument)} bills, introduced through enacted`
                : 'Shots on goal: circularity bills, introduced through enacted'
            }
          >
            <p className="text-text-secondary text-body leading-relaxed">
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
              <p className="text-sm text-error">{error}</p>
            ) : !points ? (
              <div className="h-[360px] w-full animate-pulse rounded-lg bg-bg-tertiary" />
            ) : (
              <BillTimelineChart points={points} instrument={instrument} />
            )}
          </Section>

          <Section kicker="Momentum" title="Policy momentum: advancing vs. being rolled back">
            <p className="text-text-secondary text-body leading-relaxed">
              Counting bills misses the most important question: which direction are they pushing? Above
              the line are bills that <em>establish or strengthen</em> a circular-economy obligation; below
              it, bills that <em>exempt, narrow, repeal, or preempt</em> one. Slice by instrument to see
              where the field is gaining ground and where the backlash is concentrated.
            </p>
            <StanceMomentumChart regions={regionsCsv} />
          </Section>
        </>
      )}

      {tab === 'coverage' && (
        <>
          <Section kicker="Coverage" title="Where instruments meet materials">
            <p className="text-text-secondary text-body leading-relaxed">
              Which policy tools have been aimed at which materials. The dense cells are well-trodden
              ground; the empty ones are the white space — a material with deposit-return or labeling
              precedent but no EPR yet is often where the next wave of bills lands.
            </p>
            <InstrumentMaterialMatrix regions={regionsCsv} />
          </Section>

          <Section kicker="Intervention regime" title="Which materials can go circular incrementally — and which need critical mass">
            <p className="text-text-secondary text-body leading-relaxed">
              Not every material needs the same law. High-value, concentrated ones with an established
              reverse channel (lead-acid batteries, aluminium, precious metals) cross the collection valley
              on their own economics — legislation only has to stop penalizing the first mover. Low-value,
              dispersed ones (textiles, footwear, flexible film) have no incremental path: their unit
              economics never close below near-total coverage, so a law has to engineer critical mass
              deliberately — mandated collection, pooled PRO financing, and design intervention at once.
              Where a material sits here is which of those two playbooks its bills should carry.
            </p>
            <MaterialRegimeMap />
          </Section>

          <Section kicker="Coverage" title="How collection targets are measured">
            <p className="text-text-secondary text-body leading-relaxed">
              When a law sets a collection or recovery target, what is it measured against? Most set a
              <em> weight</em> (tonnage) target — but a minority measure <em>value recovered</em> (the
              critical-metals angle) or apply <em>material-specific</em> mandates. Extracted per target
              from each bill&apos;s text, so a bill with several targets contributes several.
            </p>
            <CollectionTargetBasisChart regions={regionsCsv} />
          </Section>

          <Section kicker="Outliers" title="The 'Other' bucket: emergent instruments to watch">
            <p className="text-text-secondary text-body leading-relaxed">
              In-scope bills that don&apos;t map to a named instrument yet — disposal bans, reuse/refill
              mandates, product standards. Mining this bucket is how new instrument categories surface
              before they&apos;re formalized.
            </p>
            <OutliersPlaylist />
          </Section>
        </>
      )}

      {tab === 'geography' && (
        <>
          <div className="rounded-lg border border-border-default bg-bg-primary px-4 py-3 text-sm text-text-secondary">
            <span className="font-semibold text-text-primary">United States only.</span> These views rank
            jurisdictions against a passage-rate baseline and sponsor record that we only have for US
            states — so they don&apos;t honor the region filter. An equivalent for EU member states is a
            future addition.
          </div>

          <Section
            kicker="State passage gap"
            title="Does each state pass circular-economy bills above or below its own average?"
          >
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
        </>
      )}

      {tab === 'impact' && (
        <Section kicker="Field notes" title="Real-world impact: what enacted laws actually did">
          <p className="text-text-secondary text-body leading-relaxed">
            Everywhere else we track what a law <em>requires</em>. This is what enacted laws have been
            documented to <em>produce</em> — measured outcomes, positive and negative, each anchored to
            a citation. Measured impacts are rare and uneven, so the list grows as evidence surfaces.
          </p>
          <RealWorldImpact />
        </Section>
      )}
    </div>
  );
}
