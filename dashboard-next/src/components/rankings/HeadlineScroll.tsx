'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { track } from '@/lib/analytics';
import { formatDate } from '@/lib/utils';
import { outcomeMetricText } from '@/lib/outcomeMetric';
import { CheckIcon } from '@/components/ui/icons';
import {
  usePositiveOutcomes, useOutcomeShare, jurisdiction, topicOf, possessive, LinkGlyph,
} from '@/components/home/HeadlinesDeadlines';
import { FeatureCard, Kicker, BigFigure } from '@/components/home/FeatureCard';
import type { BillOutcome } from '@/lib/types';

const ACCENT = 'rgb(var(--green-accent))';
// How many headlines the scroll walks through, and how much page each one gets. Six at ~45vh is a
// couple of screens of scroll: long enough to read each figure, short of trapping the reader.
const MAX_HEADLINES = 6;
const VH_PER_HEADLINE = 45;

/**
 * The documented outcomes of enacted law, stepped through by scrolling: the section is several screens
 * tall, the card sticks, and the reader's scroll position picks which headline it shows. Arrows do the
 * same for anyone who'd rather click. Each card shares on its own, and the foot links to the full set
 * on Insights.
 */
export function HeadlineScroll() {
  const items = usePositiveOutcomes().slice(0, MAX_HEADLINES);
  const trackRef = useRef<HTMLDivElement>(null);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (items.length < 2) return;
    const onScroll = () => {
      const el = trackRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const span = r.height - window.innerHeight;
      if (span <= 0) return;
      const progress = Math.min(1, Math.max(0, -r.top / span));
      setIdx(Math.min(items.length - 1, Math.floor(progress * items.length)));
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [items.length]);

  /** Arrow steps scroll the page to that headline's slice, so scroll position and card never disagree. */
  const goTo = (i: number) => {
    const el = trackRef.current;
    if (!el) return;
    const span = el.getBoundingClientRect().height - window.innerHeight;
    const top = el.getBoundingClientRect().top + window.scrollY + (span * (i + 0.5)) / items.length;
    window.scrollTo({ top, behavior: 'smooth' });
  };

  if (items.length === 0) return null;
  const current = items[Math.min(idx, items.length - 1)];

  return (
    <section aria-labelledby="rank-headlines-title">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="rank-headlines-title" className="font-serif text-2xl text-text-primary">Headlines</h2>
        <Link
          href="/insights"
          onClick={() => track('cta_click', { entry_source: 'rankings_all_headlines' })}
          className="link-arrow text-sm"
        >
          See all headlines
        </Link>
      </div>
      <p className="mt-1 text-sm text-text-muted">What enacted law has been documented to produce. Scroll to step through.</p>

      <div ref={trackRef} className="relative mt-4" style={{ height: items.length > 1 ? `calc(${items.length * VH_PER_HEADLINE}vh + 24rem)` : undefined }}>
        <div className="sticky top-20">
          <HeadlineCard
            o={current}
            position={{ i: Math.min(idx, items.length - 1), n: items.length }}
            onStep={d => goTo(Math.min(items.length - 1, Math.max(0, idx + d)))}
          />
        </div>
      </div>
    </section>
  );
}

function HeadlineCard({ o, position, onStep }: {
  o: BillOutcome; position: { i: number; n: number }; onStep: (delta: number) => void;
}) {
  const { billPath, share, shared } = useOutcomeShare(o);
  const metric = outcomeMetricText(o)!;
  const place = jurisdiction(o.state);

  return (
    <FeatureCard className="min-h-[22rem]">
      <div className="flex items-start justify-between gap-4">
        <Kicker tone={ACCENT}>
          {place ? `${possessive(place)} impact on ${topicOf(o)}` : `Impact on ${topicOf(o)}`}
          {o.bill_number && (
            <>
              {': '}
              {billPath ? (
                <Link
                  href={billPath}
                  onClick={() => track('cta_click', { entry_source: 'rankings_outcome_bill', slug: o.slug })}
                  className="text-text-primary underline decoration-1 underline-offset-4 hover:decoration-2"
                >
                  {o.bill_number}
                </Link>
              ) : (
                <span className="text-text-primary">{o.bill_number}</span>
              )}
            </>
          )}
        </Kicker>
        <button
          type="button"
          onClick={share}
          aria-label={shared ? 'Link copied' : 'Copy a shareable link to this outcome'}
          title={shared ? 'Copied' : 'Share'}
          className={`-mr-1 -mt-1 inline-flex shrink-0 items-center p-1 text-lg transition-colors ${shared ? 'text-text-primary' : 'text-text-muted hover:text-text-primary'}`}
        >
          {shared ? <CheckIcon /> : <LinkGlyph />}
        </button>
      </div>

      <div key={o.slug} aria-live="polite" className="region-title-in mt-5 flex flex-1 flex-col">
        <BigFigure text={metric} tone={ACCENT} />
        <p className="mt-4 line-clamp-3 text-lg leading-snug text-text-secondary">{o.metric_label}</p>
      </div>

      <div className="mt-5 flex items-center justify-between gap-3 border-t border-border-default pt-4 text-sm text-text-muted">
        <span>{o.as_of_date ? `As of ${formatDate(o.as_of_date)}` : ''}</span>
        {position.n > 1 && (
          <div className="flex shrink-0 items-center gap-3">
            <button type="button" onClick={() => onStep(-1)} disabled={position.i === 0} aria-label="Previous headline" className="px-1 text-xl transition-colors hover:text-text-primary disabled:opacity-30">‹</button>
            <span className="tabular-nums">{position.i + 1} / {position.n}</span>
            <button type="button" onClick={() => onStep(1)} disabled={position.i === position.n - 1} aria-label="Next headline" className="px-1 text-xl transition-colors hover:text-text-primary disabled:opacity-30">›</button>
          </div>
        )}
      </div>
    </FeatureCard>
  );
}
