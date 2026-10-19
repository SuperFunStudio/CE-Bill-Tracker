'use client';
import { useMemo } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { fetchBillOutcomeIndex } from '@/lib/api';
import { outcomeMetricText } from '@/lib/outcomeMetric';
import { billHref, fixEncoding } from '@/lib/utils';
import { jurisdictionCell } from '@/lib/jurisdictions';
import { fmtCount } from '@/lib/mapScale';
import type { BillOutcome, BillSummary } from '@/lib/types';

/**
 * The gazette line at the top of Explore and of every jurisdiction page: one figure, one sentence.
 *
 * Source order:
 *  1. A documented real-world outcome (bill_outcome — reviewed research, 80 rows across 22
 *     jurisdictions as of 2026-10). The ungated /bills/outcomes/by-bill index is the same one every
 *     bill page reads; we show figure + one line, which is the public teaser (source and attribution
 *     detail stay on the bill page / Insights).
 *  2. Otherwise a computed headline from our own corpus ("50 circular-economy laws in force"), so
 *     every jurisdiction gets a headline today and a researched outcome replaces it as it lands.
 *
 * Outcomes are matched to the jurisdiction THROUGH their bill (region + state), never on the bare
 * `state` code — outcome rows carry "CA" for both California and Canada.
 * With several candidates the pick rotates daily, so a returning reader sees a fresh front page.
 */

export interface HeadlineFocus {
  /** Region code in focus, or null for "All". */
  region: string | null;
  /** US state in focus (region === 'US'). */
  state: string | null;
  /** Display name ("Poland", "California", "All"). */
  name: string;
}

interface Headline {
  kicker: string;
  figure: string;
  text: string;
  href?: string;
}

const dayIndex = () => Math.floor(Date.now() / 86_400_000);

export function useOutcomeIndex() {
  return useQuery({
    queryKey: ['bill-outcome-index'],
    queryFn: fetchBillOutcomeIndex,
    staleTime: 30 * 60 * 1000,
  });
}

function pickHeadline(focus: HeadlineFocus, bills: BillSummary[], index: Record<string, BillOutcome[]> | undefined): Headline | null {
  const byId = new Map(bills.map(b => [b.id, b]));
  const inFocus = (b: BillSummary | undefined) => {
    if (!b) return false;
    if (!focus.region) return true;
    if (b.region !== focus.region) return false;
    return focus.state ? b.state === focus.state : true;
  };

  if (index) {
    const candidates = Object.values(index)
      .flat()
      .filter(o => o.bill_id != null && inFocus(byId.get(o.bill_id)) && outcomeMetricText(o))
      .sort((a, b) => (b.as_of_date ?? '').localeCompare(a.as_of_date ?? '') || a.id - b.id);
    if (candidates.length) {
      const o = candidates[dayIndex() % candidates.length];
      const bill = byId.get(o.bill_id!)!;
      const where = focus.region ? '' : ` · ${jurisdictionCell(bill.region, bill.state).name}`;
      return {
        kicker: `Documented outcome${where}`,
        figure: outcomeMetricText(o)!,
        text: `${o.metric_label ?? ''}${o.bill_number ? ` — ${o.bill_number}` : ''}`.trim(),
        href: billHref({ id: bill.id, bill_number: bill.bill_number, title: bill.title }),
      };
    }
  }

  // Computed fallback: always available.
  const scoped = bills.filter(b => inFocus(b) && b.ce_relevant !== false);
  const enacted = scoped.filter(b => (b.status ?? '').toLowerCase() === 'enacted');
  if (enacted.length === 0) {
    if (scoped.length === 0) return null;
    return {
      kicker: 'By the numbers',
      figure: fmtCount(scoped.length),
      text: `circular-economy ${scoped.length === 1 ? 'bill' : 'bills'} moving in ${focus.name} — none enacted yet`,
    };
  }
  const newest = [...enacted].sort((a, b) =>
    (b.last_action_date ?? b.status_date ?? '').localeCompare(a.last_action_date ?? a.status_date ?? ''))[0];
  const yr = (newest.last_action_date ?? newest.status_date ?? '').slice(0, 4);
  const title = fixEncoding(newest.title) || newest.bill_number || 'Untitled';
  return {
    kicker: 'By the numbers',
    figure: fmtCount(enacted.length),
    text: `circular-economy laws in force${focus.region ? ` in ${focus.name}` : ''} — newest: ${title.length > 80 ? `${title.slice(0, 80)}…` : title}${yr ? ` (${yr})` : ''}`,
    href: billHref(newest),
  };
}

export function RegionHeadline({ focus, bills, className = '' }: { focus: HeadlineFocus; bills: BillSummary[]; className?: string }) {
  const { data: index } = useOutcomeIndex();
  const h = useMemo(() => pickHeadline(focus, bills, index), [focus, bills, index]);
  if (!h) return <div className={`h-px bg-text-primary/70 ${className}`} />;

  const body = (
    <>
      <span className="field-label shrink-0">{h.kicker}</span>
      <span className="font-serif text-lg leading-tight text-text-primary tabular-nums sm:text-xl">{h.figure}</span>
      {/* One line, always: on a phone it drops under the figure and truncates, so the headline never
          costs more than two lines above the first law. */}
      <span className="w-full min-w-0 truncate text-sm text-text-secondary sm:w-auto">{h.text}</span>
    </>
  );
  // Newspaper rules: a heavy rule over the line, a hairline under it.
  return (
    <section aria-label="Headline" className={`border-t-2 border-b border-t-text-primary/80 border-b-border-default py-2 ${className}`}>
      {h.href ? (
        <Link href={h.href} className="group flex flex-wrap items-baseline gap-x-3 gap-y-0.5 sm:flex-nowrap">
          {body}
          <span aria-hidden className="ml-auto hidden shrink-0 text-sm text-text-muted transition-colors group-hover:text-text-primary sm:inline">→</span>
        </Link>
      ) : (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 sm:flex-nowrap">{body}</div>
      )}
    </section>
  );
}
