'use client';

import { useEffect, useState } from 'react';
import { fetchBillOutcomes } from '@/lib/api';
import { track } from '@/lib/analytics';
import type { BillOutcome } from '@/lib/types';

/**
 * "Real-World Impact" — the curated feed of documented outcomes of enacted laws (positive,
 * negative, or mixed), each anchored to a citation. The product answer to "we track what laws
 * REQUIRE; here's what they actually DID." Seeded with TX HB3487 → Sink Your Shucks reef acreage;
 * backfilled by research. Renders one card per bill_outcome from GET /bills/outcomes.
 */

const DIRECTION_STYLES: Record<string, { dot: string; label: string; chip: string }> = {
  positive: {
    dot: 'bg-[rgb(var(--green-accent))]',
    label: 'Positive',
    chip: 'border-[rgb(var(--green-accent))] text-[rgb(var(--green-accent))]',
  },
  negative: {
    dot: 'bg-red-500',
    label: 'Negative',
    chip: 'border-red-500 text-red-600 dark:text-red-400',
  },
  mixed: {
    dot: 'bg-amber-500',
    label: 'Mixed',
    chip: 'border-amber-500 text-amber-600 dark:text-amber-400',
  },
};

// How tightly the figure ties to the statute — surfaced so a "program" number isn't read as
// "the law did this single-handedly".
const ATTRIBUTION_NOTE: Record<string, string> = {
  direct: 'Directly produced by the law',
  program: 'Produced by a program the law funds or incentivizes',
  associated: 'Associated with the law (correlation)',
};

function metricText(o: BillOutcome): string | null {
  if (o.metric_display) return o.metric_display;
  if (o.metric_value != null) {
    const v = o.metric_value.toLocaleString();
    return o.metric_unit ? `${v} ${o.metric_unit}` : v;
  }
  return null;
}

function OutcomeCard({ outcome }: { outcome: BillOutcome }) {
  const dir = DIRECTION_STYLES[outcome.direction] ?? DIRECTION_STYLES.mixed;
  const metric = metricText(outcome);
  const lawLabel = [outcome.state, outcome.bill_number].filter(Boolean).join(' ');

  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {lawLabel && (
            <p className="text-text-muted text-xs font-medium uppercase tracking-wide">{lawLabel}</p>
          )}
          {outcome.law_title && (
            <p className="text-text-secondary text-sm leading-snug mt-0.5">{outcome.law_title}</p>
          )}
        </div>
        <span
          className={`shrink-0 inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${dir.chip}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${dir.dot}`} />
          {dir.label}
        </span>
      </div>

      {(metric || outcome.metric_label) && (
        <div className="flex items-baseline gap-2">
          {metric && <span className="font-bold text-text-primary text-2xl">{metric}</span>}
          {outcome.metric_label && (
            <span className="text-text-secondary text-sm">{outcome.metric_label}</span>
          )}
        </div>
      )}

      <p className="text-text-secondary text-sm leading-relaxed">{outcome.summary}</p>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
        {outcome.attribution && ATTRIBUTION_NOTE[outcome.attribution] && (
          <span title="How tightly the figure ties to the statute">
            {ATTRIBUTION_NOTE[outcome.attribution]}
          </span>
        )}
        {outcome.as_of_date && <span>As of {outcome.as_of_date}</span>}
        {!outcome.reviewed && <span className="italic">Unverified — pending review</span>}
        {outcome.source_url && (
          <a
            href={outcome.source_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => track('insights_outcome_source', { slug: outcome.slug })}
            className="text-[rgb(var(--green-accent))] hover:underline"
          >
            Source{outcome.source_name ? `: ${outcome.source_name}` : ''} ↗
          </a>
        )}
      </div>
    </div>
  );
}

export function RealWorldImpact() {
  const [outcomes, setOutcomes] = useState<BillOutcome[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchBillOutcomes()
      .then((d) => {
        if (!cancelled) setOutcomes(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load outcomes.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <p className="text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!outcomes) {
    return <div className="h-32 w-full animate-pulse rounded-lg bg-bg-tertiary" />;
  }
  if (outcomes.length === 0) {
    return (
      <p className="text-text-muted text-sm">
        No documented outcomes recorded yet — measured impacts are rare and get added as they surface.
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {outcomes.map((o) => (
        <OutcomeCard key={o.id} outcome={o} />
      ))}
    </div>
  );
}
