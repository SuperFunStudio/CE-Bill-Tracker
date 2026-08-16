'use client';

import { useEffect, useState } from 'react';
import { fetchBillOutcomes } from '@/lib/api';
// ATTRIBUTION_NOTE and the figure formatter are shared with the ticker and the bill page's impact
// block — a "program" caveat that reads differently on different surfaces is a claim that drifted.
import { ATTRIBUTION_NOTE, outcomeMetricText } from '@/lib/outcomeMetric';
import { track } from '@/lib/analytics';
import { useAuth } from '@/components/auth/AuthContext';
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


function OutcomeCard({ outcome }: { outcome: BillOutcome }) {
  const dir = DIRECTION_STYLES[outcome.direction] ?? DIRECTION_STYLES.mixed;
  const metric = outcomeMetricText(outcome);
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
          className={`shrink-0 inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-meta font-semibold ${dir.chip}`}
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

      <p className="text-text-secondary text-body leading-relaxed">{outcome.summary}</p>

      {outcome.direction !== 'positive' && outcome.remediation_note && (
        <div className="rounded-md border border-[rgb(var(--green-accent))]/40 bg-[rgb(var(--green-accent))]/5 px-3 py-2 text-sm">
          <span className="font-semibold text-[rgb(var(--green-accent))]">
            → Fixed by {outcome.remediation_bill_number || 'a later law'}:
          </span>{' '}
          <span className="text-text-secondary">{outcome.remediation_note}</span>
        </div>
      )}

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
  const { getToken } = useAuth();

  useEffect(() => {
    let cancelled = false;
    // reviewed_only: only human-vetted figures on the public page. Unvetted candidates
    // (reviewed=false, from scripts/propose_bill_outcomes.py) live only in the /admin console.
    // Token attached: the full documented set is CAP_INSIGHTS_IMPACT. Without it the API returns
    // only the teaser the free homepage ticker uses, so this table would silently show six rows.
    (async () => {
      try {
        const data = await fetchBillOutcomes({ reviewed_only: true }, await getToken());
        if (!cancelled) setOutcomes(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load outcomes.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [getToken]);

  if (error) return <p className="text-sm text-error">{error}</p>;
  if (!outcomes) {
    return <div className="h-32 w-full animate-pulse rounded-lg bg-bg-tertiary" />;
  }
  if (outcomes.length === 0) {
    return (
      <p className="text-text-secondary text-body">
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
