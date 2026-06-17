'use client';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { useBills } from '@/hooks/useBills';

// Engine snapshot. `relevant` is pulled live from the bill engine below; the value
// here is only a fallback for first paint / offline. `universe` is the OpenStates bulk
// corpus the engine draws from — verified at 1,490,425 state/D.C./territory bills
// (1,560,420 incl. federal) in the 2026-06 monthly Postgres dump. `terms` & `categories`
// describe the pre-screen lexicon.
const ENGINE = {
  universe: '1.5 million',   // bills in the U.S. legislative corpus the engine draws from
  relevant: '1,535',         // fallback only — live count comes from useBills()
  terms: '440+',             // circular-economy terms in the pre-screen lexicon
  categories: 16,            // signal categories the terms are grouped into
};

const INSTRUMENTS = [
  'Extended Producer Responsibility (EPR)',
  'Deposit Return / bottle bills',
  'Right to Repair',
  'Recycled-Content mandates',
  'Labeling & Disclosure',
];

const MATERIALS = [
  'plastic packaging', 'paper packaging', 'glass', 'metals', 'electronics', 'batteries',
  'paint', 'carpet', 'mattresses', 'tires', 'pharmaceuticals', 'solar panels', 'textiles',
  'organics', 'other',
];

export default function MethodologyPage() {
  // Same query (and cache) the states page uses; snapshot-backed so it's never 0.
  const { data: bills } = useBills({ epr_relevant: true, limit: 5000 });
  const relevant = bills?.length ? bills.length.toLocaleString() : ENGINE.relevant;

  return (
    <div className="p-6 space-y-8 max-w-3xl mx-auto">
      <GazetteHeader title="How we decide what counts" subtitle="The classification behind every relevance call" />

      <p className="text-text-secondary leading-relaxed">
        This page is powered by the <strong className="text-text-primary">SignalScout</strong> bill-tracker
        and analysis engine — the same pipeline behind the API. It ingests the full U.S. legislative
        universe, screens every bill against a fixed set of circularity criteria — EPR, deposit-return,
        right-to-repair, recycled-content, and labeling instruments across 15 material &amp; product streams —
        and auto-classifies the matches before a human spot-review. The goal is a judgment you can audit,
        not a black box.
      </p>

      <section className="grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-border-default bg-border-default">
        <div className="bg-bg-card p-4 text-center">
          <div className="font-serif text-2xl text-text-primary">{ENGINE.universe}</div>
          <div className="mt-1 text-xs text-text-muted leading-snug">bills in the U.S. legislative universe — 50 states, D.C. &amp; federal</div>
        </div>
        <div className="bg-bg-card p-4 text-center">
          <div className="font-serif text-2xl text-text-primary">{ENGINE.terms}</div>
          <div className="mt-1 text-xs text-text-muted leading-snug">circular-economy terms in {ENGINE.categories} signal categories</div>
        </div>
        <div className="bg-bg-card p-4 text-center">
          <div className="font-serif text-2xl text-green-accent">{relevant}</div>
          <div className="mt-1 text-xs text-text-muted leading-snug">flagged as circularity-relevant legislation</div>
        </div>
      </section>
      <p className="-mt-4 text-center text-xs text-text-muted">
        A live snapshot — the engine re-runs as bills move and new sessions open.
      </p>

      <section className="space-y-3">
        <h2 className="font-serif text-xl text-text-primary">What we screen for</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <div className="text-text-muted text-xs uppercase tracking-wide mb-1">Instruments</div>
            <ul className="space-y-1 text-sm text-text-secondary">
              {INSTRUMENTS.map(i => <li key={i}>· {i}</li>)}
            </ul>
          </div>
          <div>
            <div className="text-text-muted text-xs uppercase tracking-wide mb-1">Material &amp; product streams (15)</div>
            <p className="text-sm text-text-secondary leading-relaxed">
              {MATERIALS.join(', ')}.
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-serif text-xl text-text-primary">How a bill gets classified</h2>
        <ol className="space-y-3 text-sm text-text-secondary">
          <li>
            <span className="text-text-primary font-medium">1. Ingest.</span> Every bill from all 50
            states and D.C. is pulled from Open States and refreshed as it moves.
          </li>
          <li>
            <span className="text-text-primary font-medium">2. Pre-screen.</span> A curated
            circular-economy lexicon — {ENGINE.terms} terms across {ENGINE.categories} signal
            categories, tiered and weighted — narrows the full legislative universe to plausible
            candidates, so deeper analysis is spent only on bills that might be relevant.
          </li>
          <li>
            <span className="text-text-primary font-medium">3. Classify.</span> Each candidate is
            evaluated against the fixed criteria above and either flagged relevant — with a
            confidence score, policy instrument, and material tags — or set aside.
          </li>
          <li>
            <span className="text-text-primary font-medium">4. Extract.</span> Relevant bills have
            their compliance specifics pulled from the bill text: deadlines, covered products,
            producer obligations, fees, and preemption signals.
          </li>
          <li>
            <span className="text-text-primary font-medium">5. Review.</span> A growing subset is
            spot-checked by a human, which flips the bill&apos;s <span className="text-green-accent">reviewed</span> marker.
          </li>
          <li>
            <span className="text-text-primary font-medium">6. Re-screen.</span> As a bill advances
            or its text changes, it&apos;s re-evaluated so the record stays current.
          </li>
        </ol>
      </section>

      <section className="space-y-3">
        <h2 className="font-serif text-xl text-text-primary">Auto-classified vs. reviewed</h2>
        <p className="text-text-secondary text-sm leading-relaxed">
          Each bill is first <strong className="text-text-primary">auto-classified</strong>: a language
          model reads the title, summary, and text and decides whether it touches one of the tracked
          instruments, with a confidence score and the material streams it affects. Compliance details
          (deadlines, covered products, producer obligations) are then extracted from the bill text.
        </p>
        <p className="text-text-secondary text-sm leading-relaxed">
          A bill marked <span className="text-green-accent">reviewed</span> has additionally been
          spot-checked by a human. Anything not yet reviewed carries only the automated call — shown
          on each bill so you always know which is which.
        </p>
        <p className="text-text-muted text-sm leading-relaxed">
          Classifications are automated and can contain errors; always verify against the primary
          source before acting. We continuously expand the reviewed set.
        </p>
      </section>

      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <p className="text-text-secondary text-sm">See a miscall? Help us correct it.</p>
        <a
          href="mailto:kenny@superfun.studio?subject=SignalScout%20classification%20flag&body=Bill%20(state%20%2B%20number):%0AWhat%20looks%20wrong:%0A"
          className="shrink-0 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity text-center"
        >
          Flag it →
        </a>
      </section>

      <footer className="border-t border-border-default pt-6 text-center">
        <Link href="/about" className="text-sm text-green-accent hover:underline">
          More about the project →
        </Link>
      </footer>
    </div>
  );
}
