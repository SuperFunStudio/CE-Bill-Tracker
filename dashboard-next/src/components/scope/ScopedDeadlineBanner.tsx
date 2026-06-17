'use client';
import Link from 'next/link';
import { useDeadlineStats } from '@/hooks/useDeadlines';
import { isEmptyScope } from '@/lib/scope';
import { formatDate } from '@/lib/utils';
import { CalendarIcon, AlertIcon } from '@/components/ui/icons';
import { useScope, useScopeActive } from './ScopeContext';
import { formatMaterial } from './ScopeOnboarding';

const THREE_YEARS = 1095;

/**
 * The conversion artifact, in two voices:
 *  • Scoped → loss-framed urgency: "⚠ 2 deadlines affecting your materials (plastic packaging) in
 *    CA, IL within 30 days. Nearest: Jul 1, 2026."
 *  • Unscoped → a de-escalated hook: "33 deadlines nationwide over the next 3 years. Tell us your
 *    states and materials to see which ones are yours →" (opens onboarding).
 * It runs entirely off the ungated /deadlines/summary counts — no deadline rows are fetched here, so
 * this works for anonymous visitors without exposing the Pro-gated calendar.
 */
export function ScopedDeadlineBanner() {
  const active = useScopeActive();
  const { scope, openEditor } = useScope();
  const { data: stats } = useDeadlineStats({
    days_ahead: THREE_YEARS,
    materials: active && scope.materials.length ? scope.materials.join(',') : undefined,
    states: active && scope.states.length ? scope.states.join(',') : undefined,
  });

  if (!stats) return null;

  // ── Scoped: lead with the 30-day window, fall back to 90 ──
  if (active) {
    const count = stats.within_30 > 0 ? stats.within_30 : stats.within_90;
    if (count === 0) return null;
    const urgent = stats.within_30 > 0;
    const horizon = urgent ? 'within 30 days' : 'in the next 90 days';
    const matPhrase =
      scope.materials.length > 0
        ? ` affecting your products & materials (${scope.materials.map(formatMaterial).join(', ')})`
        : '';
    const statePhrase = stats.states.length > 0 ? ` in ${stats.states.join(', ')}` : '';

    return (
      <Link
        href="/compliance"
        className={`block rounded-lg border px-4 py-3 transition-colors ${
          urgent
            ? 'border-urgency-high/50 bg-red-50 dark:bg-red-950/30 hover:border-urgency-high'
            : 'border-green-accent/40 bg-green-dark/30 hover:border-green-accent'
        }`}
      >
        <div className="flex items-center gap-3">
          {urgent ? (
            <AlertIcon className="text-urgency-high text-xl shrink-0" />
          ) : (
            <CalendarIcon className="text-green-accent text-xl shrink-0" />
          )}
          <p className="text-sm sm:text-base text-text-primary">
            <span className={`font-serif font-semibold ${urgent ? 'text-urgency-high' : 'text-green-accent'}`}>
              {count}
            </span>{' '}
            {count === 1 ? 'deadline' : 'deadlines'}
            {matPhrase}
            {statePhrase} {horizon}.{' '}
            {stats.next_date && (
              <span className="text-text-secondary">Nearest: {formatDate(stats.next_date)}.</span>
            )}{' '}
            <span className={urgent ? 'text-urgency-high' : 'text-green-accent'}>
              See what&apos;s required →
            </span>
          </p>
        </div>
      </Link>
    );
  }

  // ── Unscoped: the de-escalated hook ──
  // A reader with a scope who toggled "show everything" gets nothing here (the ScopeBar owns that
  // state); only a genuinely unscoped reader (never set one, or skipped) sees the hook.
  if (!isEmptyScope(scope)) return null;
  if (stats.total_upcoming === 0) return null;

  return (
    <button
      onClick={openEditor}
      className="block w-full text-left rounded-lg border border-border-default bg-bg-secondary/60 px-4 py-3 hover:border-green-accent/40 transition-colors"
    >
      <div className="flex items-center gap-3">
        <CalendarIcon className="text-text-muted text-xl shrink-0" />
        <p className="text-sm sm:text-base text-text-secondary">
          <span className="font-serif font-semibold text-text-primary">{stats.total_upcoming}</span>{' '}
          deadlines nationwide over the next 3 years.{' '}
          <span className="text-green-accent">
            Tell us your states, products &amp; materials to see which ones are yours →
          </span>
        </p>
      </div>
    </button>
  );
}
