'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { fetchBillOutcomes } from '@/lib/api';
import { track } from '@/lib/analytics';
import { formatDate, STATE_NAMES, billHref } from '@/lib/utils';
import { EU_MEMBERS, FOREIGN_COUNTRY_NAMES, REGION_LABELS } from '@/lib/jurisdictions';
import { scaleComparison } from '@/lib/outcomeScale';
import { downloadOutcomeCard } from '@/lib/outcomeShareImage';
import { CheckIcon } from '@/components/ui/icons';
import type { BillOutcome } from '@/lib/types';

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
  const [shared, setShared] = useState(false);

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
  const metric = metricText(o)!;
  const place = jurisdiction(o.state);
  // Something a reader can picture. Pure unit arithmetic — see lib/outcomeScale for why this stops at
  // physical equivalence and doesn't attempt "harm avoided".
  const scale = scaleComparison(o.metric_value, o.metric_unit);
  // The law itself, on the Atlas. bill_id is a soft link: famous laws we haven't ingested as rows
  // carry the denormalized number only, and those stay plain text rather than linking nowhere.
  const billPath = o.bill_id
    ? billHref({ id: o.bill_id, bill_number: o.bill_number, title: o.law_title })
    : null;
  const attribution = [place, o.bill_number].filter(Boolean).join(' · ');

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
  const shareUrl =
    `${SITE_URL}${billPath ?? '/insights/'}` +
    `?utm_source=share&utm_medium=social&utm_campaign=outcome_headline&utm_content=${encodeURIComponent(o.slug)}`;
  const shareText = `${metric} ${o.metric_label ?? ''}${place ? ` — ${place}` : ''}`.trim();

  /** One shape for every share event, so the GA dimensions can't drift between the three channels. */
  const shareEvent = (channel: 'native' | 'copy' | 'image') => ({
    share_channel: channel,
    outcome_slug: o.slug,
    utm_campaign: 'outcome_headline',
    utm_content: o.slug,
  });

  async function share() {
    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({ title: shareText, text: shareText, url: shareUrl });
        track('outcome_share', shareEvent('native'));
        return;
      } catch {
        /* dismissed or unsupported — fall through to the clipboard */
      }
    }
    try {
      await navigator.clipboard.writeText(`${shareText} — ${shareUrl}`);
      setShared(true);
      setTimeout(() => setShared(false), 1800);
      track('outcome_share', shareEvent('copy'));
    } catch {
      window.prompt('Copy this link:', shareUrl);
    }
  }

  async function saveCard() {
    try {
      await downloadOutcomeCard(
        { metric, label: o.metric_label ?? '', comparison: scale?.text, attribution },
        `atlas-circular-${o.slug}.png`,
      );
      track('outcome_share', shareEvent('image'));
    } catch {
      /* canvas/blob unavailable — the link share above is always there as the fallback */
    }
  }

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
        {/* The figure, made picturable. Sits with the figure rather than in its own block — it's a
            restatement of the same number, not a second fact. Clamped and floored at two lines for
            the same reason the label above is: the card must be the same height whether the entry
            has an equivalence (the "…% of the way around the Earth" ones run to two lines) or none
            at all — money and bare rates convert to nothing and this line renders empty. */}
        <p
          className="mt-1.5 line-clamp-2 min-h-[2rem] text-xs leading-snug text-text-primary/80"
          title={scale?.basis}
        >
          {scale && (
            <>
              <span className="text-text-muted">That&apos;s </span>
              <span className="border-b border-dotted border-text-muted/50">{scale.text}</span>
            </>
          )}
        </p>
        <p className="mt-1 text-xs text-text-muted">
          {place}
          {place && o.bill_number && ' · '}
          {/* The law is the point of the figure, so it links to the law — this card used to name a
              bill number with nothing behind it. */}
          {o.bill_number &&
            (billPath ? (
              <Link
                href={billPath}
                onClick={() => track('cta_click', { entry_source: 'home_outcome_bill', slug: o.slug })}
                className="text-green-accent hover:underline"
              >
                {o.bill_number}
              </Link>
            ) : (
              o.bill_number
            ))}
          {o.as_of_date ? ` · as of ${formatDate(o.as_of_date)}` : ''}
        </p>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <Link
            href="/insights"
            onClick={() => track('cta_click', { entry_source: 'home_outcome_ticker', slug: o.slug })}
            className="text-sm text-green-accent hover:underline"
          >
            Discover more insights →
          </Link>
          {/* Sharing sits next to the read-more, because they're the same impulse: this figure landed,
              now what. Two channels — the tagged link for a message or a post, and a rendered card for
              a platform that wants an image. */}
          <span className="flex items-center gap-2 text-xs text-text-muted">
            <button
              type="button"
              onClick={share}
              aria-label="Copy a shareable link to this outcome"
              className={`inline-flex items-center gap-1 transition-colors ${
                shared ? 'text-green-accent' : 'hover:text-text-primary'
              }`}
            >
              {shared ? <CheckIcon /> : <LinkGlyph />}
              {shared ? 'Copied' : 'Share'}
            </button>
            <span className="text-border-default">|</span>
            <button
              type="button"
              onClick={saveCard}
              aria-label="Download this outcome as a social image"
              className="transition-colors hover:text-text-primary"
            >
              Save image
            </button>
          </span>
        </div>
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

/** Chain-link glyph, matching ShareBillButton's. */
function LinkGlyph() {
  return (
    <svg
      width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden
    >
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
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
