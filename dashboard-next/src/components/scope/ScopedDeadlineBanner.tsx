'use client';
import { useMemo } from 'react';
import Link from 'next/link';
import { useDeadlines } from '@/hooks/useDeadlines';
import { deadlineInScope, isEmptyScope } from '@/lib/scope';
import { formatDate, daysUntil } from '@/lib/utils';
import { CalendarIcon, AlertIcon } from '@/components/ui/icons';
import type { BillSummary, DeadlineSummary } from '@/lib/types';
import { useScope, useScopeActive } from './ScopeContext';
import { formatMaterial } from './ScopeOnboarding';

const THREE_YEARS = 1095;

/**
 * The conversion artifact, in two voices:
 *  • Scoped → loss-framed urgency: "⚠ 2 deadlines affecting your materials (plastic packaging) in
 *    CA, IL within 30 days. Nearest: Jul 1, 2026."
 *  • Unscoped → a de-escalated hook: "33 deadlines nationwide over the next 3 years. Tell us your
 *    states and materials to see which ones are yours →" (opens onboarding).
 * Materials live on the linked bill, not the deadline, so we resolve them through the loaded bills.
 */
export function ScopedDeadlineBanner({ bills }: { bills: BillSummary[] }) {
  const active = useScopeActive();
  const { scope, openEditor } = useScope();
  const { data: deadlines = [] } = useDeadlines({ days_ahead: THREE_YEARS });

  const billMaterials = useMemo(() => {
    const map = new Map<number, string[]>();
    for (const b of bills) map.set(b.id, b.material_categories ?? []);
    return map;
  }, [bills]);

  const resolve = (d: DeadlineSummary) => (d.bill_id != null ? billMaterials.get(d.bill_id) : null);

  const upcoming = useMemo(
    () => deadlines.filter(d => { const n = daysUntil(d.deadline_date); return n !== null && n >= 0; }),
    [deadlines],
  );

  const scoped = useMemo(
    () => (active ? upcoming.filter(d => deadlineInScope(d, scope, resolve)) : []),
    [active, upcoming, scope, billMaterials],
  );

  // ── Scoped: lead with the 30-day window, fall back to 90 ──
  if (active) {
    const within = (days: number) =>
      scoped.filter(d => { const n = daysUntil(d.deadline_date); return n !== null && n <= days; });
    const w30 = within(30);
    const list = w30.length > 0 ? w30 : within(90);
    if (list.length === 0) return null;

    const states = Array.from(new Set(list.map(d => d.state)));
    const nearest = list.reduce((a, b) => (a.deadline_date <= b.deadline_date ? a : b));
    const matPhrase =
      scope.materials.length > 0
        ? ` affecting your materials (${scope.materials.map(formatMaterial).join(', ')})`
        : '';
    const statePhrase = states.length > 0 ? ` in ${states.join(', ')}` : '';
    const urgent = w30.length > 0;
    const horizon = urgent ? 'within 30 days' : 'in the next 90 days';

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
              {list.length}
            </span>{' '}
            {list.length === 1 ? 'deadline' : 'deadlines'}
            {matPhrase}
            {statePhrase} {horizon}.{' '}
            <span className="text-text-secondary">Nearest: {formatDate(nearest.deadline_date)}.</span>{' '}
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
  if (upcoming.length === 0) return null;

  return (
    <button
      onClick={openEditor}
      className="block w-full text-left rounded-lg border border-border-default bg-bg-secondary/60 px-4 py-3 hover:border-green-accent/40 transition-colors"
    >
      <div className="flex items-center gap-3">
        <CalendarIcon className="text-text-muted text-xl shrink-0" />
        <p className="text-sm sm:text-base text-text-secondary">
          <span className="font-serif font-semibold text-text-primary">{upcoming.length}</span>{' '}
          deadlines nationwide over the next 3 years.{' '}
          <span className="text-green-accent">
            Tell us your states and materials to see which ones are yours →
          </span>
        </p>
      </div>
    </button>
  );
}
