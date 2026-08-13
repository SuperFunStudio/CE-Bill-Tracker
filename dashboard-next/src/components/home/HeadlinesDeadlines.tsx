'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { fetchBillOutcomes } from '@/lib/api';
import { useDeadlines } from '@/hooks/useDeadlines';
import { useAuth } from '@/components/auth/AuthContext';
import { track } from '@/lib/analytics';
import { formatDate, STATE_NAMES } from '@/lib/utils';
import { EU_MEMBERS, FOREIGN_COUNTRY_NAMES, REGION_LABELS } from '@/lib/jurisdictions';
import { CalendarIcon } from '@/components/ui/icons';
import type { BillOutcome } from '@/lib/types';

const ROTATE_MS = 8000;
const DEADLINE_ROWS = 5;

/** Outcomes and deadlines both carry a bare jurisdiction code whose family isn't in the row (a US
 *  state code and a country code share a namespace — "DE" is Delaware here and Germany there). These
 *  surfaces are jurisdiction-labelled only, so a best-effort resolution is enough: US states win, then
 *  EU members, then the non-EU countries we ingest, then the umbrella regions ("US" on a federal
 *  deadline, "EU" on an EU-wide one — both real codes here, neither a state or a country). */
function jurisdiction(code: string | null | undefined): string {
  if (!code) return '';
  const c = code.toUpperCase();
  return STATE_NAMES[c] ?? EU_MEMBERS[c] ?? FOREIGN_COUNTRY_NAMES[c] ?? REGION_LABELS[c] ?? c;
}

function metricText(o: BillOutcome): string | null {
  if (o.metric_display) return o.metric_display;
  if (o.metric_value != null) {
    const v = o.metric_value.toLocaleString();
    return o.metric_unit ? `${v} ${o.metric_unit}` : v;
  }
  return null;
}

/**
 * Left block: a slow rotation through the documented POSITIVE outcomes of enacted law — the answer to
 * "so does any of this actually work?", which nothing else on the front page answers.
 *
 * This is deliberately a teaser: the figure, what it measures, and whose law produced it. The summary,
 * the attribution knob (direct / program / associated) and the citation stay on the Pro Insights tab,
 * which is where a reader who wants to check the number should end up. Newest `as_of_date` leads, so
 * the block is date-relevant without any curation step.
 *
 * Rotation pauses on hover and on keyboard focus, and never starts at all under prefers-reduced-motion
 * — a figure that swaps itself out from under a reader who asked for less motion is just a bug.
 */
function OutcomeTicker() {
  const { data: outcomes } = useQuery({
    // region 'all': outcomes span 11 regions and the endpoint defaults to US alone, which would drop
    // three quarters of the set on a page whose whole claim is global coverage.
    queryKey: ['billOutcomes', 'positive', 'all'],
    queryFn: () => fetchBillOutcomes({ direction: 'positive', region: 'all', reviewed_only: true }),
    staleTime: 30 * 60 * 1000,
  });

  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    setReduced(!!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  }, []);

  const items = useMemo(() => (outcomes ?? []).filter(o => metricText(o)), [outcomes]);

  useEffect(() => {
    if (reduced || paused || items.length < 2) return;
    const id = setInterval(() => setIdx(i => (i + 1) % items.length), ROTATE_MS);
    return () => clearInterval(id);
  }, [reduced, paused, items.length]);

  if (!items.length) return null;

  const o = items[idx % items.length];
  const metric = metricText(o);
  const place = jurisdiction(o.state);

  return (
    <div
      className="flex h-full flex-col rounded-lg border border-green-accent/30 bg-green-dark/20 px-4 py-3"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-meta uppercase tracking-wider text-green-accent">What the laws did</span>
        {items.length > 1 && (
          <span className="tabular-nums text-meta text-text-muted">{(idx % items.length) + 1}/{items.length}</span>
        )}
      </div>

      {/* aria-live so the rotation is announced rather than silently swapping under a screen reader. */}
      {/* justify-center: the card stretches to the deadline list's height, so the single figure sits in
          the middle of that space and reads as a deliberate stat card rather than top-aligned text with
          a hole under it. */}
      <div aria-live="polite" className="mt-1.5 flex flex-1 flex-col justify-center py-2">
        <p className="text-text-primary leading-snug">
          <span className="font-serif text-xl text-green-accent">{metric}</span>{' '}
          <span className="text-sm text-text-secondary">{o.metric_label}</span>
        </p>
        <p className="mt-1 text-xs text-text-muted">
          {[place, o.bill_number].filter(Boolean).join(' · ')}
          {o.as_of_date ? ` · as of ${formatDate(o.as_of_date)}` : ''}
        </p>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3">
        <Link
          href="/insights"
          onClick={() => track('cta_click', { entry_source: 'home_outcome_ticker', slug: o.slug })}
          className="text-sm text-green-accent hover:underline"
        >
          See the source &amp; the full record →
        </Link>
        {items.length > 1 && !reduced && (
          <button
            type="button"
            onClick={() => setIdx(i => (i + 1) % items.length)}
            aria-label="Next outcome"
            className="shrink-0 text-text-muted transition-colors hover:text-text-primary"
          >
            ›
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Right block: the next few dated obligations, newest deadline first. useDeadlines is server-gated —
 * a Pro seat gets the full calendar and everyone else the soonest few rows — so this renders whatever
 * the reader is entitled to without a client-side check of its own.
 */
function DeadlineList() {
  const { isPro } = useAuth();
  // region 'all' for the same reason as the ticker: US future deadlines alone are a fraction of the set.
  const { data: deadlines } = useDeadlines({ days_ahead: 365, region: 'all' });

  const rows = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return (deadlines ?? [])
      .filter(d => d.deadline_date >= today)
      .sort((a, b) => a.deadline_date.localeCompare(b.deadline_date))
      .slice(0, DEADLINE_ROWS);
  }, [deadlines]);

  if (!rows.length) return null;

  return (
    <div className="flex h-full flex-col rounded-lg border border-border-default bg-bg-secondary/60 px-4 py-3">
      <div className="flex items-center gap-2">
        <CalendarIcon className="text-text-muted shrink-0" />
        <span className="text-meta uppercase tracking-wider text-text-muted">Next up</span>
      </div>
      <ul className="mt-2 flex-1 space-y-2">
        {rows.map(d => (
          <li key={d.id} className="flex items-baseline gap-2.5 text-sm">
            <span className="shrink-0 tabular-nums font-medium text-text-primary">
              {formatDate(d.deadline_date)}
            </span>
            {/* Clamped to two lines: EU deadline descriptions are whole statutory paragraphs, and one
                of them unclamped is taller than the other four rows combined. The full text is on
                /compliance, which is where the link goes. */}
            <span className="line-clamp-2 min-w-0 text-text-secondary" title={d.description ?? d.bill_title ?? undefined}>
              <span className="text-text-primary">{jurisdiction(d.state)}</span>
              {d.description ? ` — ${d.description}` : d.bill_title ? ` — ${d.bill_title}` : ''}
            </span>
          </li>
        ))}
      </ul>
      <Link
        href="/compliance"
        onClick={() => track('cta_click', { entry_source: 'home_deadline_list' })}
        className="mt-2.5 inline-block text-sm text-green-accent hover:underline"
      >
        {isPro ? 'Open the full calendar →' : 'See every upcoming deadline →'}
      </Link>
    </div>
  );
}

/**
 * "Headlines & Deadlines" — the two date-relevant blocks that aren't bills: what enacted law has been
 * documented to produce (left) and what's coming due (right). Both degrade to nothing rather than to
 * an empty shell, so the section only appears when it has something to say; the banners passed as
 * `children` (the scoped deadline count, the federal preemption wildcard) sit below them.
 */
export function HeadlinesDeadlines({ children }: { children?: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-serif text-lg text-text-primary mb-3">Headlines &amp; Deadlines</h2>
      {/* No items-start: the two blocks stretch to a shared height so the shorter one (the ticker,
          which shows a single rotating figure) doesn't leave a hole beside the deadline list. */}
      <div className="grid gap-3 lg:grid-cols-2">
        <OutcomeTicker />
        <DeadlineList />
      </div>
      {children && <div className="mt-3 space-y-3">{children}</div>}
    </section>
  );
}
