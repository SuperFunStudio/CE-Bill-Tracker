'use client';
import { useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { CompassIcon, LockIcon } from '@/components/ui/icons';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { TEASER_LEVERS, GUIDE_COVERAGE } from '@/data/designGuideTeaser';

// The Free teaser surfaces the headline design imperative per lever — enough to know what the law
// already requires you to design for. The full guide (every imperative, numeric targets, statutory
// evidence, printable) is the Pro deliverable; the SKU/portfolio-scoped version is Enterprise.
// Interim gating = the request-access capture (no billing yet) — see gating-and-monetization-plan.

const BOOKING_URL = 'https://calendar.app.google/QPXh1qXWhNWxXo9n6';

const OBLIGATION_STYLE: Record<string, string> = {
  Required: 'text-urgency-high border-urgency-high/40',
  Prohibited: 'text-urgency-high border-urgency-high/40',
  'Fee-penalized': 'text-amber-500 border-amber-500/40',
  'Fee-advantaged': 'text-green-accent border-green-accent/40',
};

export default function DesignGuidePage() {
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <div className="p-6 space-y-8 max-w-6xl mx-auto">
      <GazetteHeader
        title="Design Guide"
        subtitle="What circular-economy law already requires you to design for — and what ignoring it will cost."
      />

      <p className="text-text-secondary text-sm leading-relaxed max-w-3xl">
        Every imperative below is pulled verbatim from enacted and proposed US bills — no
        opinion, no invented thresholds. Miss one and it shows up as a non-compliant SKU, a
        fee penalty, or a market you can no longer sell into. Derived from{' '}
        <span className="text-text-primary font-medium">{GUIDE_COVERAGE.bills} bills</span> across{' '}
        <span className="text-text-primary font-medium">{GUIDE_COVERAGE.states} states</span>.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 items-stretch">
        {TEASER_LEVERS.map(l => (
          <div
            key={l.lever}
            className="flex flex-col rounded-xl border border-border-default bg-bg-secondary p-5"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <h2 className="font-serif text-lg text-text-primary leading-tight">{l.name}</h2>
              <span
                className={`shrink-0 text-[10px] uppercase tracking-wider rounded-full border px-2 py-0.5 ${
                  OBLIGATION_STYLE[l.obligation] ?? 'text-text-muted border-border-default'
                }`}
              >
                {l.obligation}
              </span>
            </div>
            <p className="text-text-primary text-sm font-medium mb-2">{l.headline}</p>
            {l.direction && (
              <p className="text-text-secondary text-sm leading-relaxed mb-3">{l.direction}</p>
            )}
            {l.evidence && (
              <blockquote className="mt-auto border-l-2 border-green-accent/40 pl-3 text-text-muted text-xs italic leading-relaxed">
                “{l.evidence.quote}”
                <span className="not-italic block mt-1 text-text-secondary">
                  — {l.evidence.state} {l.evidence.bill}
                </span>
              </blockquote>
            )}
            <p className="mt-3 pt-3 border-t border-border-default text-text-muted text-xs">
              {l.billCount} bills · {l.states.length} states
            </p>
          </div>
        ))}
      </div>

      {/* Pro gate — the full guide */}
      <section className="rounded-xl border border-green-accent bg-green-dark/20 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-5">
        <div className="max-w-2xl">
          <div className="flex items-center gap-2 mb-1">
            <CompassIcon className="text-green-accent text-lg" />
            <h3 className="font-serif text-xl text-text-primary">The full Design Guide</h3>
            <span className="text-[10px] uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
              Pro
            </span>
          </div>
          <p className="text-text-secondary text-sm leading-relaxed">
            Every lever, 3–6 canonical imperatives each, the concrete numeric targets (recycled-content
            %, dates), and the verbatim statutory language behind every line — print-ready and kept
            current as bills move. The teaser is the headline; this is the playbook.
          </p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="shrink-0 inline-flex items-center gap-2 rounded-lg bg-green-accent text-bg-primary px-5 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity"
        >
          <LockIcon className="text-sm" />
          Get the full guide →
        </button>
      </section>

      {/* Enterprise / consulting line */}
      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <p className="text-text-secondary text-sm leading-relaxed max-w-2xl">
          Need this scoped to your own products and the states you sell in — your SKUs mapped to the
          exact imperatives and deadlines that hit them? That&apos;s built per engagement.
        </p>
        <a
          href={BOOKING_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          Have a worthy challenge? →
        </a>
      </section>

      {modalOpen && (
        <RequestAccessModal
          plan="pro"
          planLabel="Design Guide (Pro)"
          source="design_guide"
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}
