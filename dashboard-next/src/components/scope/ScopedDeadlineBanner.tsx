'use client';
import Link from 'next/link';
import { useDeadlineStats } from '@/hooks/useDeadlines';
import { isEmptyScope, scopeJurisdictionCodes } from '@/lib/scope';
import { formatDate } from '@/lib/utils';
import { FeatureCard, Kicker, BigFigure } from '@/components/home/FeatureCard';
import { useScope, useScopeActive } from './ScopeContext';
import { formatMaterial } from './ScopeOnboarding';

const THREE_YEARS = 1095;

/**
 * The conversion artifact, in two voices:
 *  • Scoped → loss-framed urgency: "⚠ 2 deadlines affecting your materials (plastic packaging) in
 *    CA, IL within 30 days. Nearest: Jul 1, 2026."
 *  • Unscoped → a de-escalated hook: "33 compliance deadlines worldwide over the next 3 years. See
 *    the full calendar →". Coverage is global now, so "nationwide" was simply wrong; and setting a
 *    scope is its own button on the Explore filter row ("Set your regional & material scope"), so
 *    this banner sends readers to the deadlines they were just told about instead.
 * It runs entirely off the ungated /deadlines/summary counts — no deadline rows are fetched here, so
 * this works for anonymous visitors without exposing the Pro-gated calendar.
 */
export function ScopedDeadlineBanner() {
  const active = useScopeActive();
  const { scope } = useScope();
  const { data: stats } = useDeadlineStats({
    days_ahead: THREE_YEARS,
    materials: active && scope.materials.length ? scope.materials.join(',') : undefined,
    // Regions + US states in one list — the deadline row has a single jurisdiction column.
    states: active && scopeJurisdictionCodes(scope).length ? scopeJurisdictionCodes(scope).join(',') : undefined,
  });

  if (!stats) return null;

  // ── Scoped: lead with the 30-day window, fall back to 90 ──
  if (active) {
    const count = stats.within_30 > 0 ? stats.within_30 : stats.within_90;
    if (count === 0) return null;
    const urgent = stats.within_30 > 0;
    const matPhrase =
      scope.materials.length > 0 ? ` affecting ${scope.materials.map(formatMaterial).join(', ')}` : '';
    const statePhrase = stats.states.length > 0 ? ` in ${stats.states.join(', ')}` : '';
    return (
      <DeadlineCard
        tone={urgent ? 'var(--status-weakens)' : 'var(--status-committee)'}
        horizon={urgent ? 'Next 30 days' : 'Next 90 days'}
        label="Your deadlines"
        count={count}
        unit={count === 1 ? 'deadline for you' : 'deadlines for you'}
        sentence={`Upcoming obligations${matPhrase}${statePhrase}.`}
        nextDate={stats.next_date}
        cta="See what’s required"
      />
    );
  }

  // ── Unscoped: the de-escalated hook ──
  // A reader with a scope who toggled "show everything" gets nothing here (the ScopeBar owns that
  // state); only a genuinely unscoped reader (never set one, or skipped) sees the hook.
  if (!isEmptyScope(scope)) return null;
  if (stats.total_upcoming === 0) return null;
  return (
    <DeadlineCard
      tone="var(--status-committee)"
      horizon="Next 3 years"
      label="Deadlines"
      count={stats.total_upcoming}
      unit="compliance deadlines"
      sentence="Registrations, reports and fees coming due under enacted law, worldwide."
      nextDate={stats.next_date}
      cta="See the full calendar"
    />
  );
}

/** The deadlines half of the Headlines & Deadlines spread — same card language as the outcome card. */
function DeadlineCard({
  tone, horizon, label, count, unit, sentence, nextDate, cta,
}: {
  tone: string; horizon: string; label: string; count: number; unit: string;
  sentence: string; nextDate: string | null | undefined; cta: string;
}) {
  return (
    <FeatureCard>
      <Kicker tone={tone}>
        {label}
        <span className="text-text-muted">{' · '}{horizon}</span>
      </Kicker>
      <div className="mt-5 flex flex-1 flex-col">
        <BigFigure text={`${count.toLocaleString('en-US')} ${unit}`} tone={tone} />
        <p className="mt-4 line-clamp-3 min-h-[4.6rem] text-lg leading-snug text-text-secondary">{sentence}</p>
      </div>
      <div className="mt-5 border-t border-border-default pt-4">
        <p className="min-h-[1.25rem] text-sm text-text-muted">{nextDate ? `Nearest: ${formatDate(nextDate)}` : ''}</p>
        <div className="mt-3">
          <Link href="/compliance" className="text-base font-medium text-text-primary underline-offset-4 hover:underline">
            {cta} <span aria-hidden>→</span>
          </Link>
        </div>
      </div>
    </FeatureCard>
  );
}
