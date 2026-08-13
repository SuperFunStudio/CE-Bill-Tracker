'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { fetchBillOutcomes } from '@/lib/api';
import { track } from '@/lib/analytics';
import { formatDate, STATE_NAMES } from '@/lib/utils';
import { EU_MEMBERS, FOREIGN_COUNTRY_NAMES, REGION_LABELS } from '@/lib/jurisdictions';
import type { BillOutcome } from '@/lib/types';

const ROTATE_MS = 8000;

/** An outcome carries a bare jurisdiction code whose family isn't in the row (a US state code and a
 *  country code share a namespace — "DE" is Delaware here and Germany there). This surface is
 *  jurisdiction-labelled only, so a best-effort resolution is enough: US states win, then
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
 * A slow rotation through the documented POSITIVE outcomes of enacted law — the answer to "so does
 * any of this actually work?", which nothing else on the front page answers.
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
      {items.length > 1 && (
        <div className="flex justify-end">
          <span className="tabular-nums text-meta text-text-muted">{(idx % items.length) + 1}/{items.length}</span>
        </div>
      )}

      {/* aria-live so the rotation is announced rather than silently swapping under a screen reader. */}
      {/* The figure gets its OWN line, at a fixed line-height, with the label under it. Sharing a line
          meant the layout was hostage to the widest entry — a short figure next to a long label wrapped
          to two lines while the next entry fit on one, so the whole card jumped every 8 seconds. Fixed
          rows for the figure and the label mean the card is the same height for every entry in the
          rotation, whatever the string lengths; min-h on the label reserves its second line rather
          than growing into it. */}
      <div aria-live="polite" className="mt-1.5 flex flex-1 flex-col justify-center py-2">
        <p className="min-h-[2.5rem] font-serif text-3xl leading-tight text-green-accent tabular-nums">{metric}</p>
        {/* Clamped AND floored at two lines: the clamp stops a long metric_label from growing the card,
            the min-height stops a short one from shrinking it. Both are needed — either alone still
            lets the card change size between entries, which is the jump. */}
        <p className="mt-2 line-clamp-2 min-h-[2.5rem] text-sm leading-snug text-text-secondary" title={o.metric_label ?? undefined}>
          {o.metric_label}
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
          Discover more insights →
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
 * "Headlines & Deadlines" — the date-relevant material that isn't a bill: what enacted law has been
 * documented to produce, above the deadline banners passed as `children`.
 *
 * There used to be a second block beside the ticker — the next five dated obligations, linking to
 * /compliance. It was cut (2026-08-13) as a duplicate: the ScopedDeadlineBanner immediately below it
 * already counts the reader's upcoming deadlines and links to the same calendar, so the section said
 * "deadlines →" twice in a row with the second one adding only five rows the calendar shows anyway.
 * The ticker degrades to nothing rather than to an empty shell, so the section only appears when it
 * has something to say.
 */
export function HeadlinesDeadlines({ children }: { children?: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-serif text-lg text-text-primary mb-3">Headlines &amp; Deadlines</h2>
      <OutcomeTicker />
      {children && <div className="mt-3 space-y-3">{children}</div>}
    </section>
  );
}
