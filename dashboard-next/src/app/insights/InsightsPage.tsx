'use client';

import { useEffect, useMemo, useState } from 'react';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { BillTimelineChart } from '@/components/insights/BillTimelineChart';
import { StanceMomentumChart } from '@/components/insights/StanceMomentumChart';
import { CollectionTargetBasisChart } from '@/components/insights/CollectionTargetBasisChart';
import { FeeCoverageChart } from '@/components/insights/FeeCoverageChart';
import { InstrumentMaterialMatrix } from '@/components/insights/InstrumentMaterialMatrix';
import { RegionInstrumentMatrix } from '@/components/insights/RegionInstrumentMatrix';
import { RealWorldImpact } from '@/components/insights/RealWorldImpact';
import { OutliersPlaylist } from '@/components/insights/OutliersPlaylist';
import { MaterialRegimeMap } from '@/components/insights/MaterialRegimeMap';
import { InsightsButterfly } from '@/components/insights/InsightsButterfly';
import { useRegion } from '@/components/layout/RegionContext';
import { RegionFilter } from '@/components/insights/RegionFilter';
import { useAuth } from '@/components/auth/AuthContext';
import { LockIcon } from '@/components/ui/icons';
import Link from 'next/link';
import { fetchBillTimeline } from '@/lib/api';
import { track } from '@/lib/analytics';
import type { BillTimelinePoint } from '@/lib/types';

// Tabs group the visualizations so the page isn't one long scroll.
//
// 2026-10-30: Butterfly LEADS — the most visual view, and the one that answers "what does this
// region's law actually cover" at a glance. One row of four equal tabs. Two views are ARCHIVED, not
// deleted (their components stay; restoring one is a tab entry + an import):
//   - Flows (BillFlowSankey) — tab removed.
//   - Momentum's "Shots on goal" timeline (BillTimelineChart, instrument pills) — removed from the
//     Momentum tab; the chart still renders in the non-member teaser below.
//
// Before that, Momentum led. The old first tab was "World", whose global-coverage choropleth said the same thing
// as the globe on Explore — so the briefing room opened on a restatement of the front page. Momentum
// (are these laws multiplying, and in which direction?) is the question the corpus can answer and the
// map can't, so it opens the page; Coverage — which instruments meet which materials — follows.
//
// "World" is gone. Its two sections split: the global map was a duplicate and is dropped, and the
// regulatory-personality matrix (region × instrument) moved into Coverage, where the other matrix
// already lived. Two tabs both called "coverage" was the confusion.
//
// The region multi-select applies to Momentum ALONE (see the filter inside that panel). Coverage now
// reads the whole corpus deliberately: it's a "what has ever been tried, anywhere" reference, and a
// region filter left on from another tab quietly emptied its cells.
//
// Geography · US has MOVED to the admin console's "Pending Insights" tab. It was admin-only here,
// which made this page carry a tab only one person could see, on top of analysis that isn't finished:
// the passage-gap, cycle, and champion views all rest on OpenStates sponsor/vote data backfilled for
// US states alone. Unfinished work belongs in the staging ground with the unreviewed outcome queue,
// not behind a hidden flap on a member-facing page. The views themselves live on in
// components/insights/GeographyPanels — promoting one back is an import.
// See memory: state-profile-pages / legislative-analytics-dump.
const TABS = [
  { id: 'butterfly', label: 'Butterfly' },
  { id: 'momentum', label: 'Momentum' },
  { id: 'coverage', label: 'Coverage' },
  { id: 'impact', label: 'Impact' },
] as const;
type TabId = (typeof TABS)[number]['id'];

/**
 * Insights — a curated, link-shareable briefing room for legislative staffers. A Pro membership
 * feature: surfaced in the nav for Pro members/admins, gated with the standard sign-up-or-purchase
 * card for everyone else (still reachable by URL, where the gate does the selling). Organized into
 * tabs (Butterfly / Momentum / Coverage / Impact) with a region filter on the
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
  const [tab, setTab] = useState<TabId>('butterfly');
  // The region selection now lives IN the Momentum panel rather than in the site-wide bar under the
  // nav (which /insights no longer renders — see REGION_BAR_HIDDEN in AppShell). It's still the same
  // shared RegionContext, so a selection made here survives a nav to Explore and back.
  const { regions, setRegions, regionsParam: regionsCsv } = useRegion();
  const { isPro, isAdmin, user, openAuth } = useAuth();

  const [points, setPoints] = useState<BillTimelinePoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setPoints(null);
    fetchBillTimeline({ regions: regionsCsv })
      .then((d) => {
        if (!cancelled) setPoints(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load timeline.');
      });
    return () => {
      cancelled = true;
    };
  }, [regionsCsv]);

  // Headline figures: total laws on the books, and the current year's introductions.
  // points are region-grouped now, so sum across regions for the aggregate stat.
  //
  // The introductions figure used to be labelled "(peak year)", picked by max(). That was a coverage
  // artifact dressed up as a finding: continuous bill tracking only starts ~2019, so the peak is
  // always the newest year and the label implied a record where there was only a deeper dataset.
  // Now it names the year plainly and lets the chart carry the trend.
  const stats = useMemo(() => {
    if (!points) return null;
    const enacted = points.filter((p) => p.status === 'enacted').reduce((s, p) => s + p.count, 0);
    const introByYear = new Map<number, number>();
    for (const p of points) {
      if (p.status === 'introduced') introByYear.set(p.year, (introByYear.get(p.year) ?? 0) + p.count);
    }
    const latestIntroYear = introByYear.size ? Math.max(...introByYear.keys()) : 0;
    const latestIntro = { year: latestIntroYear, count: introByYear.get(latestIntroYear) ?? 0 };
    const firstYear = points.reduce((m, p) => Math.min(m, p.year), Infinity);
    return { enacted, latestIntro, firstYear: Number.isFinite(firstYear) ? firstYear : null };
  }, [points]);

  // Insights is a Pro membership feature, but a locked door sells nothing — a visitor who can't see
  // any of it has no way to judge whether it's worth paying for. So non-members get one real chart
  // rather than a wall: the enacted-laws-over-time view, with the headline figures above it.
  //
  // The teaser is built from data that is ALREADY PUBLIC (/bills/timeline — the same aggregate the
  // pricing ledger sums), not from a softened version of the gated routes. That distinction is what
  // lets the server gate stay absolute: /insights/* still 403s, and nothing here asks it to bend.
  // Kept after the hooks above so the rules-of-hooks order is stable.
  if (!isPro && !isAdmin) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10 space-y-6">
        <GazetteHeader
          title="Insights"
          subtitle="Tracking impacts from circular economy policy trends."
        />

        <section className="space-y-4">
          <div>
            <p className="text-[rgb(var(--green-accent))] text-xs font-semibold uppercase tracking-wider">
              Free preview
            </p>
            <h2 className="font-serif text-xl text-text-primary">
              Twenty years of circular-economy law, in one line
            </h2>
            <p className="text-text-secondary text-body leading-relaxed mt-1">
              Every measure the Atlas tracks, by the year it moved. This is one chart of the briefing
              room — the rest is below.
            </p>
          </div>

          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <Stat
                value={stats.enacted.toLocaleString()}
                label="Circular-economy laws enacted to date"
              />
              {stats.latestIntro.year > 0 && (
                <Stat
                  value={stats.latestIntro.count.toLocaleString()}
                  label={`Bills introduced in ${stats.latestIntro.year} so far`}
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
            <BillTimelineChart points={points} />
          )}
        </section>

        {/* What's behind the gate, named specifically. "Global coverage maps, momentum charts,
            scorecards" is a list of nouns; saying what each one answers is what makes the price
            legible to someone deciding. */}
        <section className="surface-card p-6 space-y-4">
          <div>
            <h2 className="font-serif text-xl text-text-primary">The rest of the briefing room</h2>
            <p className="text-text-secondary text-body mt-1">Included with a Pro membership.</p>
          </div>
          <ul className="grid gap-x-6 gap-y-2 sm:grid-cols-2 text-body text-text-secondary">
            {[
              ['Momentum', 'whether bills are strengthening obligations or rolling them back'],
              ['Region-by-region trajectories', 'scope the enacted line to any set of jurisdictions'],
              ['Regulatory personality', 'which instrument each jurisdiction reaches for first'],
              ['Instrument × material', 'which policy tools are aimed at which materials'],
              ['Producer fees', 'what compliance costs, read from the enacting text'],
              ['Real-world impact', 'documented outcomes of enacted laws, with citations'],
            ].map(([title, desc]) => (
              <li key={title} className="flex gap-2">
                <LockIcon className="text-xs mt-1 shrink-0 text-text-muted" />
                <span>
                  <span className="text-text-primary font-medium">{title}</span> — {desc}
                </span>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2 pt-1">
            {!user && (
              <button
                type="button"
                onClick={() => { track('cta_click', { entry_source: 'insights_teaser_signin' }); openAuth(); }}
                className="rounded-full border border-border-default px-5 py-2 text-sm text-text-secondary hover:text-text-primary"
              >
                Sign in
              </button>
            )}
            <Link
              href="/pricing"
              onClick={() => track('cta_click', { entry_source: 'insights_teaser_pricing' })}
              className="rounded-full bg-green-accent px-5 py-2 text-sm font-medium text-bg-primary hover:opacity-90"
            >
              See memberships
            </Link>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <GazetteHeader
        title="Insights"
        subtitle="Tracking impacts from circular economy policy trends."
      />

      {/* Tab bar. The region filter is not here — it belongs to Momentum, the only view it changes. */}
      <div className="border-b border-border-default">
        <div className="-mb-px grid grid-cols-4" role="tablist">
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
                className={`border-b-2 px-2 py-2.5 text-center text-sm transition-colors ${
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

      {tab === 'butterfly' && (
        <Section kicker="Circularity" title="Where a jurisdiction's law sits on the circular economy">
          <p className="text-text-secondary text-body">
            The law we track, placed on the Ellen MacArthur butterfly. Pick a region, or compare two.
          </p>
          <InsightsButterfly />
        </Section>
      )}

      {tab === 'momentum' && (
        <>
          {/* The region multi-select, at the top of the one tab that reads it. As the site-wide bar it
              sat above every tab and changed three charts out of a dozen — so on the tabs it did
              nothing it was noise, and on the tabs it DID something the effect was invisible. */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border-default bg-bg-primary px-4 py-3">
            <RegionFilter selected={regions} onChange={setRegions} />
            <p className="text-xs text-text-muted">
              {regions.length === 0
                ? 'Every tracked region, aggregated. Pick regions to trace their trajectories side by side.'
                : 'Scoping the chart below. The other tabs read the whole corpus.'}
            </p>
            {regions.length > 0 && (
              <button
                onClick={() => setRegions([])}
                className="ml-auto text-xs text-green-accent hover:underline"
              >
                All regions
              </button>
            )}
          </div>

          <Section kicker="Momentum" title="Policy momentum: advancing vs. being rolled back">
            <p className="text-text-secondary text-body">
              Above the line, bills that <em>strengthen</em> a circular-economy obligation; below it, bills
              that <em>roll one back</em>.
            </p>
            <StanceMomentumChart regions={regionsCsv} />
          </Section>
        </>
      )}

      {tab === 'coverage' && (
        <>
          <div className="rounded-lg border border-border-default bg-bg-primary px-4 py-3 text-sm text-text-secondary">
            <span className="font-semibold text-text-primary">Every region.</span> Coverage is a reference
            for what has been tried anywhere, so these views read the whole tracked corpus. The region
            filter lives on the Momentum tab, where it changes what you see.
          </div>

          <Section kicker="Regulatory personality" title="Which instruments each jurisdiction leans on">
            <p className="text-text-secondary text-body">
              Read across a row to see which tool each region reaches for first.
            </p>
            <RegionInstrumentMatrix />
          </Section>

          <Section kicker="Coverage" title="Where instruments meet materials">
            <p className="text-text-secondary text-body leading-relaxed">
              Dense cells are well-trodden ground; empty ones are where the next wave often lands.
            </p>
            <InstrumentMaterialMatrix />
          </Section>

          <Section kicker="Intervention regime" title="Which materials can go circular incrementally — and which need critical mass">
            <p className="text-text-secondary text-body leading-relaxed">
              High-value materials close on their own economics; low-value, dispersed ones need a law that
              engineers critical mass.
            </p>
            <MaterialRegimeMap />
          </Section>

          <Section kicker="Coverage" title="How collection targets are measured">
            <p className="text-text-secondary text-body leading-relaxed">
              Most targets are by <em>weight</em>; a minority measure <em>value recovered</em> or set
              material-specific mandates.
            </p>
            <CollectionTargetBasisChart />
          </Section>

          <Section kicker="Producer fees" title="What compliance actually costs: fees across jurisdictions">
            <p className="text-text-secondary text-body leading-relaxed">
              What a producer owes, read from the enacting text and cited to it.
            </p>
            <FeeCoverageChart />
          </Section>

          <Section kicker="Outliers" title="The 'Other' bucket: emergent instruments to watch">
            <p className="text-text-secondary text-body leading-relaxed">
              Bills that don&apos;t fit a named instrument yet — where new categories surface first.
            </p>
            <OutliersPlaylist />
          </Section>
        </>
      )}

      {tab === 'impact' && (
        <Section kicker="Field notes" title="Real-world impact: what enacted laws actually did">
          <p className="text-text-secondary text-body leading-relaxed">
            What enacted laws have been documented to <em>produce</em>, positive and negative, each cited.
          </p>
          <RealWorldImpact />
        </Section>
      )}
    </div>
  );
}
