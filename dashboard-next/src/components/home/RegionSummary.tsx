'use client';
import { useMemo, type ReactNode } from 'react';
import Link from 'next/link';
import type { BillSummary, CompliancePathway } from '@/lib/types';
import { formatDate, daysUntil } from '@/lib/utils';
import { fmtCount } from '@/lib/mapScale';
import { ACTION_LABEL } from '@/components/compliance/PathwayCard';

// Status buckets for the summary strip. "In progress" folds the US funnel stages together and
// "Stopped" covers failed + vetoed — the summary is a glance, the profile page carries the detail.
const BUCKETS: { key: string; label: string; match: (s: string) => boolean; tone: string; tab: string }[] = [
  { key: 'enacted', label: 'Enacted', match: s => s === 'enacted', tone: 'var(--status-enacted)', tab: 'bills' },
  {
    key: 'progress', label: 'In progress',
    match: s => ['introduced', 'in_committee', 'passed_chamber', 'passed'].includes(s),
    tone: 'var(--status-introduced)', tab: 'activity',
  },
  { key: 'stopped', label: 'Stopped', match: s => s === 'failed' || s === 'vetoed', tone: 'var(--status-dormant)', tab: 'bills' },
];

// Producer obligations worth calling a "next step" (vs. monitor / none).
const ACTIONABLE = new Set(['join_pro', 'file_individual_plan', 'register_with_state', 'pay_into_program', 'arrange_collection']);

/**
 * The jurisdiction stat card — highlights only. The headline lives at the top of the page and the
 * full picture lives on the jurisdiction profile (the title's region name links there); every
 * figure here is a door into the matching tab of that page (#bills, #activity, #comply, #cities).
 */
export function RegionSummary({
  name, kind, bills, crumbs, locator, profileHref, pathways = [], cityCount = 0,
}: {
  name: string;
  /** "National law", "US state", "EU-wide law"… */
  kind: string;
  /** The bills in focus — the table's current set. */
  bills: BillSummary[];
  /** Breadcrumb controls ("All regions / European Union"). */
  crumbs?: ReactNode;
  /** Small locator map, for a lone country. */
  locator?: ReactNode;
  /** The jurisdiction's profile page; metrics deep-link into its tabs. */
  profileHref?: string;
  /** Compliance pathways for the jurisdiction — the next step + next deadline come from here. */
  pathways?: CompliancePathway[];
  /** City ordinances (US states). */
  cityCount?: number;
}) {
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const b of bills) {
      const s = (b.status ?? '').toLowerCase();
      const bucket = BUCKETS.find(x => x.match(s));
      if (bucket) c[bucket.key] = (c[bucket.key] ?? 0) + 1;
    }
    return c;
  }, [bills]);

  const { nextStep, nextDeadline } = useMemo(() => {
    const actionable = pathways.filter(p => ACTIONABLE.has(p.action_type ?? ''));
    // Prefer joining a PRO — the step most producers take first — then any other obligation.
    const step = actionable.find(p => p.action_type === 'join_pro') ?? actionable[0] ?? null;
    const upcoming = pathways
      .filter(p => p.next_deadline_date && (daysUntil(p.next_deadline_date) ?? -1) >= 0)
      .sort((a, b) => a.next_deadline_date!.localeCompare(b.next_deadline_date!))[0] ?? null;
    return { nextStep: step, nextDeadline: upcoming };
  }, [pathways]);

  const to = (tab: string) => (profileHref ? `${profileHref}#${tab}` : undefined);
  const cell = (href: string | undefined, className: string, children: ReactNode, key?: string) =>
    href
      ? <Link key={key} href={href} className={`group block rounded transition-colors hover:bg-bg-tertiary/60 ${className}`}>{children}</Link>
      : <div key={key} className={className}>{children}</div>;

  const metrics = [
    ...BUCKETS.map(b => ({ key: b.key, label: b.label, tone: b.tone as string | null, n: counts[b.key] ?? 0, tab: b.tab })),
    ...(cityCount > 0 ? [{ key: 'cities', label: 'City laws', tone: null, n: cityCount, tab: 'cities' }] : []),
  ];

  return (
    <section className="surface-card p-4" aria-label={`${name} highlights`}>
      {crumbs && <div className="mb-2 flex flex-wrap items-center gap-1 text-xs text-text-muted">{crumbs}</div>}
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="font-serif text-xl leading-tight text-text-primary">{name}</h2>
          <p className="mt-0.5 text-xs text-text-muted">{kind}</p>
        </div>
        {/* Locator only where there's width for it; on a phone the card stays three lines tall. */}
        {locator && <div className="hidden w-36 shrink-0 sm:block">{locator}</div>}
      </div>

      <div className={`mt-3 grid gap-x-2 ${metrics.length > 3 ? 'grid-cols-4' : 'grid-cols-3'}`}>
        {metrics.map(m => cell(to(m.tab), '-mx-1 min-w-0 px-1 py-0.5', (
          <>
            <div className="flex items-center gap-1.5 truncate text-xs text-text-muted">
              {m.tone && <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: m.tone }} aria-hidden />}
              {m.label}
            </div>
            <div className="text-lg font-semibold text-text-primary tabular-nums group-hover:underline">{fmtCount(m.n)}</div>
          </>
        ), m.key))}
      </div>

      {(nextStep || nextDeadline) && (
        <div className="mt-3 space-y-1 border-t border-border-default pt-2.5 text-sm">
          {nextStep && cell(to('comply'), '-mx-1 flex items-baseline gap-2 px-1 py-0.5', (
            <>
              <span className="field-label w-24 shrink-0">Next step</span>
              <span className="min-w-0 truncate text-text-primary group-hover:underline">
                {ACTION_LABEL[nextStep.action_type ?? ''] ?? 'Comply'}
                {nextStep.entity?.name && <span className="text-text-secondary"> · {nextStep.entity.name}</span>}
              </span>
            </>
          ))}
          {nextDeadline && cell(to('comply'), '-mx-1 flex items-baseline gap-2 px-1 py-0.5', (
            <>
              <span className="field-label w-24 shrink-0">Deadline</span>
              <span className="min-w-0 truncate text-text-primary group-hover:underline">
                {formatDate(nextDeadline.next_deadline_date)}
                {nextDeadline.bill_number && <span className="text-text-secondary"> · {nextDeadline.bill_number}</span>}
              </span>
            </>
          ))}
        </div>
      )}
    </section>
  );
}
