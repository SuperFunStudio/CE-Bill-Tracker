'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { fetchBill, fetchBillOutcomes } from '@/lib/api';
import { track } from '@/lib/analytics';
import { formatDate, STATE_NAMES, billHref } from '@/lib/utils';
import { EU_MEMBERS, FOREIGN_COUNTRY_NAMES, REGION_LABELS } from '@/lib/jurisdictions';
import { outcomeMetricText } from '@/lib/outcomeMetric';
import { CheckIcon } from '@/components/ui/icons';
import type { BillOutcome } from '@/lib/types';
import { FeatureCard, Kicker, BigFigure } from './FeatureCard';

// How long a touch holds the rotation still. Long enough to read a card that a thumb landed on,
// short enough that scrolling past the block doesn't silently retire the ticker for the session —
// which is what an unbounded touch-pause does, since a phone has no mouseleave to undo it.
const TOUCH_PAUSE_MS = 30000;

// 14s, not 8s. Each card is now a figure, a clause explaining it, an equivalence to picture it by,
// and an attribution line with a link in it — four things to read and one to decide whether to click.
// Eight seconds was already tight for the figure alone; it swapped out mid-sentence with the rest.
const ROTATE_MS = 14000;

// The canonical origin for a shared link. Matches ShareBillButton / metadataBase in app/layout.tsx.
const SITE_URL = 'https://www.atlascircular.com';

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

// What a law's figure is ABOUT, for the kicker ("Vermont's impact on e-waste"). Instrument first where
// it names the stream better than the material tags do (a deposit law is about bottles & cans whatever
// its containers are made of), then the first material we have a plain word for.
const TOPIC_BY_INSTRUMENT: Record<string, string> = { deposit_return: 'bottles & cans', right_to_repair: 'repair' };
const TOPIC_BY_MATERIAL: Record<string, string> = {
  electronics: 'e-waste', batteries: 'batteries', mattresses: 'mattresses', paint: 'paint', carpet: 'carpet',
  tires: 'tires', textiles: 'textiles', plastic_packaging: 'packaging', paper_packaging: 'packaging',
  packaging: 'packaging', glass: 'packaging', metals: 'packaging', pharmaceuticals: 'medicines',
  solar_panels: 'solar panels', organics: 'food waste', construction: 'construction waste',
  thermostats: 'mercury thermostats', lighting: 'lamps', vehicles: 'vehicles', furniture: 'furniture',
};
function topicOf(o: BillOutcome): string {
  if (o.instrument_type && TOPIC_BY_INSTRUMENT[o.instrument_type]) return TOPIC_BY_INSTRUMENT[o.instrument_type];
  for (const m of o.material_categories ?? []) if (TOPIC_BY_MATERIAL[m]) return TOPIC_BY_MATERIAL[m];
  return 'waste';
}
const possessive = (place: string) => (place.endsWith('s') ? `${place}’` : `${place}’s`);

const ACCENT = 'rgb(var(--green-accent))';

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
 * — a figure that swaps itself out from under a reader who asked for less motion is just a bug. It
 * also stops — for 30 seconds on a touch, for good once an arrow is pressed. Hover is the desktop
 * signal for "I'm reading this" and a phone doesn't send it, so a phone reader had no way to hold a
 * card still, and a card that changes mid-read is how a figure gets read against the wrong caption.
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
  /** The reader took the wheel (arrows or a tap). Auto-advance doesn't come back. */
  const [manual, setManual] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [shared, setShared] = useState(false);

  useEffect(() => {
    setReduced(!!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  }, []);

  const items = useMemo(() => (outcomes ?? []).filter(o => outcomeMetricText(o)), [outcomes]);

  useEffect(() => {
    if (reduced || paused || manual || items.length < 2) return;
    const id = setInterval(() => setIdx(i => (i + 1) % items.length), ROTATE_MS);
    return () => clearInterval(id);
  }, [reduced, paused, manual, items.length]);

  /** Touch is the only "I'm reading this" signal a phone sends. Hold the card, then let go —
   *  pressing an arrow is the deliberate version and stops the rotation outright. */
  const touchPause = useRef<ReturnType<typeof setTimeout> | null>(null);
  const holdForTouch = () => {
    setPaused(true);
    if (touchPause.current) clearTimeout(touchPause.current);
    touchPause.current = setTimeout(() => setPaused(false), TOUCH_PAUSE_MS);
  };
  useEffect(() => () => { if (touchPause.current) clearTimeout(touchPause.current); }, []);

  /** Step the rotation by hand. `+ items.length` before the modulo: JS keeps the sign on -1 % n. */
  const step = (delta: number) => {
    setManual(true);
    setIdx(i => (i + delta + items.length) % items.length);
  };

  const current = items.length ? items[idx % items.length] : null;

  // The canonical bill row, fetched for its TITLE and nothing else. An outcome carries a
  // denormalized law_title written for this card — "…Redemption Law (Bottle Bill)", "…Act 2022
  // (Tasmania)" — which is free to differ from bills.title, and did on 4 of 6 rows. The bill page is
  // a static export whose slug generateStaticParams built from bills.title, so a slug derived from
  // law_title addresses a file that was never generated and there is no fallback route to catch it:
  // every shared headline landed on a 404. Slug from the same field the build did.
  const { data: bill } = useQuery({
    queryKey: ['bill', current?.bill_id],
    queryFn: () => fetchBill(current!.bill_id!),
    enabled: current?.bill_id != null,
    staleTime: 30 * 60 * 1000,
  });

  if (!current) return null;

  const o = current;
  const metric = outcomeMetricText(o)!;
  const place = jurisdiction(o.state);
  // The law itself, on the Atlas. bill_id is a soft link: famous laws we haven't ingested as rows
  // carry the denormalized number only, and those stay plain text rather than linking nowhere — as
  // does a bill whose row hasn't loaded yet, or one outside the ce_relevant set the pages are built
  // from, since neither has a page at the other end.
  const billPath = bill && bill.ce_relevant !== false ? billHref(bill) : null;

  // Share the LAW's page, not the homepage: it's the durable, indexable URL, and it's where someone
  // arriving from the post can check the figure against the statute.
  //
  // UTM-TAGGED, and the tags are the whole point of tagging them here rather than leaving it to
  // whoever pastes the link. lib/attribution reads utm_* off the landing URL and stores it, and
  // AuthContext spreads that into every later signup event — so a session that started on a shared
  // headline is attributable end-to-end in GA4 (utm_campaign=outcome_headline as the campaign
  // dimension, utm_content as the WHICH-headline breakdown). Untagged, those arrivals land in Direct
  // and the loop is unmeasurable. utm_* param names are GA-safe; bare `campaign`/`content` are not —
  // see the reserved-name rule in lib/analytics.
  //
  // #impact is load-bearing, not decoration: it lands the reader ON the block that repeats the figure
  // they tapped. Without it a shared "$16 million/year" opens a page whose first screen is the bill's
  // identity and metadata, and the promise the share made goes unkept.
  const shareUrl =
    `${SITE_URL}${billPath ?? '/insights/'}` +
    `?utm_source=share&utm_medium=social&utm_campaign=outcome_headline&utm_content=${encodeURIComponent(o.slug)}` +
    (billPath ? '#impact' : '');
  const shareText = `${metric} ${o.metric_label ?? ''}${place ? ` — ${place}` : ''}`.trim();

  /** One shape for every share event, so the GA dimensions can't drift between the two channels. */
  const shareEvent = (channel: 'native' | 'copy') => ({
    share_channel: channel,
    outcome_slug: o.slug,
    utm_campaign: 'outcome_headline',
    utm_content: o.slug,
  });

  // LINK ONLY, in both channels. Every target worth sharing to renders a preview card off the URL —
  // headline, description, image — so a `text` payload that restates the figure gets typed into the
  // message body ABOVE that card and says the same thing twice. `title` stays: share sheets label
  // themselves with it, and the apps that ignore it were the ones duplicating the body.
  async function share() {
    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({ title: shareText, url: shareUrl });
        track('outcome_share', shareEvent('native'));
        return;
      } catch {
        /* dismissed or unsupported — fall through to the clipboard */
      }
    }
    try {
      await navigator.clipboard.writeText(shareUrl);
      setShared(true);
      setTimeout(() => setShared(false), 1800);
      track('outcome_share', shareEvent('copy'));
    } catch {
      window.prompt('Copy this link:', shareUrl);
    }
  }

  return (
    <FeatureCard
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      onTouchStart={holdForTouch}
    >
      <Kicker tone={ACCENT}>
        {place ? `${possessive(place)} impact on ${topicOf(o)}` : `Impact on ${topicOf(o)}`}
        {o.bill_number && (
          <>
            {': '}
            {/* The law is the point of the figure, so it links to the law. */}
            {billPath ? (
              <Link
                href={billPath}
                onClick={() => track('cta_click', { entry_source: 'home_outcome_bill', slug: o.slug })}
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

      {/* aria-live so the rotation is announced rather than silently swapping under a screen reader.
          Fixed rows (figure at a set size, the sentence clamped AND floored) keep the card the same
          height for every entry, so the rotation never makes the page jump. */}
      <div aria-live="polite" className="mt-5 flex flex-1 flex-col">
        <BigFigure text={metric} tone={ACCENT} />
        <p
          className="mt-4 line-clamp-3 min-h-[4.6rem] text-lg leading-snug text-text-secondary"
          title={o.metric_label ?? undefined}
        >
          {o.metric_label}
        </p>
      </div>

      <div className="mt-5 border-t border-border-default pt-4">
        <p className="min-h-[1.25rem] text-sm text-text-muted">
          {o.as_of_date ? `As of ${formatDate(o.as_of_date)}` : ''}
        </p>
        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-5">
            <Link
              href="/insights"
              onClick={() => track('cta_click', { entry_source: 'home_outcome_ticker', slug: o.slug })}
              className="text-base font-medium text-text-primary underline-offset-4 hover:underline"
            >
              More insights <span aria-hidden>→</span>
            </Link>
            {/* One share channel: the tagged link, which every target expands into a preview card. */}
            <button
              type="button"
              onClick={share}
              aria-label={shared ? 'Link copied' : 'Copy a shareable link to this outcome'}
              title={shared ? 'Copied' : 'Share'}
              className={`inline-flex items-center text-lg transition-colors ${shared ? 'text-text-primary' : 'text-text-muted hover:text-text-primary'}`}
            >
              {shared ? <CheckIcon /> : <LinkGlyph />}
            </button>
          </div>
          {/* Both directions; stepping stops the auto-advance (see `manual`). */}
          {items.length > 1 && (
            <div className="flex shrink-0 items-center gap-3 text-text-muted">
              <button type="button" onClick={() => step(-1)} aria-label="Previous outcome" className="px-1 text-xl transition-colors hover:text-text-primary">‹</button>
              <span className="tabular-nums text-sm">{(idx % items.length) + 1} / {items.length}</span>
              <button type="button" onClick={() => step(1)} aria-label="Next outcome" className="px-1 text-xl transition-colors hover:text-text-primary">›</button>
            </div>
          )}
        </div>
      </div>
    </FeatureCard>
  );
}

/** Chain-link glyph, matching ShareBillButton's. */
function LinkGlyph() {
  return (
    <svg
      width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden
    >
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

/**
 * "Headlines & Deadlines" — the front-page spread at the foot of Explore: what enacted law has been
 * documented to produce (the outcome card) beside what's coming due (the deadlines card), with any
 * standing notices beneath. Built from FeatureCard so the two cards read as one design.
 *
 * The outcome card degrades to nothing rather than an empty shell; with only one card the grid
 * collapses to a single column.
 */
export function HeadlinesDeadlines({ deadlines, notices }: { deadlines?: React.ReactNode; notices?: React.ReactNode }) {
  return (
    <section aria-labelledby="hd-title">
      <h2 id="hd-title" className="font-serif text-4xl leading-tight text-text-primary sm:text-5xl">
        Headlines <span className="italic" style={{ color: ACCENT }}>&amp;</span> Deadlines
      </h2>
      <p className="mt-1 text-lg text-text-muted">What moved, and what&rsquo;s due.</p>
      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <OutcomeTicker />
        {deadlines}
      </div>
      {notices && <div className="mt-5 space-y-3">{notices}</div>}
    </section>
  );
}

