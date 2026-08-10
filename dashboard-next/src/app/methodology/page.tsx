'use client';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { useBills, useLawsInForce } from '@/hooks/useBills';
import { FAIR_QUESTIONS } from '@/lib/tiers';

// Public engine snapshot. Only observable facts live here — the numbers a reader could verify
// from the site itself (corpus scale, jurisdiction breadth, the live relevant count). The engine
// internals that make distillation possible — the exact pre-screen lexicon, its weighting/tiering,
// the model and prompts, confidence thresholds — are deliberately NOT surfaced. Keep it that way:
// describe the method, not the recipe.
// `relevant` and `inForce` are pulled live from the bill engine below; the values here are only a
// fallback for first paint / offline. `universe` is the OpenStates bulk corpus the engine screens
// wholesale — verified at 1,490,425 state/D.C./territory bills (1,560,420 incl. federal) in the
// 2026-06 monthly Postgres dump. `jurisdictions` is the global reach: U.S. states, the EU, and
// national governments now ingested from official sources — 37 distinct region codes carry relevant
// law as of 2026-08 (the EU plus 35 national governments across six continents), so 37 is the
// honest, still-growing count.
const ENGINE = {
  universe: '1.5 million',   // bills in the U.S. legislative corpus screened wholesale
  jurisdictions: '37',       // EU + national governments ingested worldwide (37 region codes live, 2026-08)
  relevant: '2,544',         // fallback only — live count comes from useBills() (~2,544 on 2026-08)
  inForce: '1,156',          // fallback only — live count comes from useLawsInForce() (~1,156 on 2026-08)
};

const INSTRUMENTS = [
  'Extended Producer Responsibility (EPR) — incl. shared-responsibility & reverse-logistics regimes abroad',
  'Deposit Return / bottle bills',
  'Right to Repair',
  'Recycled-Content mandates',
  'Financial incentives (grants, tax credits, procurement)',
  'Disposal & landfill bans',
  'Organics diversion / composting',
  'Labeling & Disclosure',
  'Preemption (tracked as a countervailing signal)',
];

const MATERIALS = [
  'plastic packaging', 'paper packaging', 'glass', 'metals', 'electronics', 'batteries',
  'paint', 'carpet', 'mattresses', 'tires', 'vehicles', 'construction', 'furniture',
  'used oil', 'pharmaceuticals', 'solar panels', 'textiles', 'organics', 'bio-based materials',
  'agriculture', 'hazardous materials', 'water', 'biodiversity',
];

export default function MethodologyPage() {
  // regions:'all' — the SAME query the homepage explorer headlines with ("Explore · N bills"), so the
  // relevance count here is the whole corpus rather than the US-only default (which read ~900 low and
  // silently contradicted every other surface). Snapshot-backed, so it's never 0.
  const { data: bills } = useBills({ ce_relevant: true, limit: 5000, regions: 'all' });
  const relevant = bills?.length ? bills.length.toLocaleString() : ENGINE.relevant;
  // The globe's headline: enacted laws currently in force, from the same endpoint it shades from.
  // Shown alongside the tracked total so the two figures read as one story, not two conflicting ones.
  const { data: lawsInForce } = useLawsInForce();
  const inForce = lawsInForce?.length
    ? lawsInForce.reduce((s, p) => s + p.count, 0).toLocaleString()
    : ENGINE.inForce;
  // Distinct regions carrying relevant law — the same derivation the pricing page uses, so the FAQ's
  // breadth answer and ENGINE.jurisdictions can't tell two different stories.
  const regionCount = lawsInForce?.length
    ? new Set(lawsInForce.map(p => p.region)).size
    : Number(ENGINE.jurisdictions);

  return (
    <div className="p-6 space-y-8 max-w-3xl mx-auto">
      <GazetteHeader title="How we decide what counts" subtitle="The classification behind every relevance call" />

      <p className="text-text-secondary leading-relaxed">
        This page is powered by the <strong className="text-text-primary">Atlas Circular</strong> bill-tracker
        and analysis engine — the same pipeline behind the API. It screens the full U.S. legislative
        universe and ingests circular-economy law from the EU and national governments worldwide, testing
        every measure against a consistent set of circularity criteria — EPR, deposit-return,
        right-to-repair, recycled-content, financial-incentive, and labeling instruments across two dozen
        material &amp; product streams — and auto-classifies the matches before a human spot-review. The goal
        is a judgment you can audit, not a black box.
      </p>

      <p className="text-text-secondary leading-relaxed">
        We&apos;re transparent about <em className="text-text-primary">how</em> a call is made — the scope
        below, the pipeline, and the auto-classified-vs-reviewed marker on every bill. The engine itself —
        the exact screening lexicon, the model and prompts, and the confidence logic that ranks a match — is
        proprietary. That&apos;s the line: enough to trust and check a result, not enough to clone the system
        behind it.
      </p>

      <section className="grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-border-default bg-border-default">
        <div className="bg-bg-card p-4 text-center">
          <div className="font-serif text-2xl text-text-primary">{ENGINE.universe}</div>
          <div className="mt-1 text-xs text-text-muted leading-snug">U.S. bills screened wholesale — 50 states, D.C. &amp; federal</div>
        </div>
        <div className="bg-bg-card p-4 text-center">
          <div className="font-serif text-2xl text-text-primary">{ENGINE.jurisdictions}</div>
          <div className="mt-1 text-xs text-text-muted leading-snug">jurisdictions worldwide — the EU &amp; national governments across six continents</div>
        </div>
        <div className="bg-bg-card p-4 text-center">
          <div className="font-serif text-2xl text-green-accent">{relevant}</div>
          <div className="mt-1 text-xs text-text-muted leading-snug">measures flagged as circularity-relevant — the tracked corpus</div>
        </div>
      </section>
      <p className="-mt-4 text-center text-xs text-text-muted">
        A live snapshot — the engine re-runs as bills move and new sessions open. Of the {relevant} tracked
        measures, <span className="text-text-secondary">{inForce}</span> are enacted laws in force — the
        figure the <Link href="/" className="text-green-accent hover:underline">homepage globe</Link> shades
        jurisdictions by. The rest are pending, failed, or superseded bills we keep on the record.
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
            <div className="text-text-muted text-xs uppercase tracking-wide mb-1">Material &amp; product streams ({MATERIALS.length})</div>
            <p className="text-body text-text-secondary leading-relaxed">
              {MATERIALS.join(', ')}.
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-serif text-xl text-text-primary">How a bill gets classified</h2>
        <ol className="space-y-3 text-body text-text-secondary">
          <li>
            <span className="text-text-primary font-medium">1. Ingest.</span> Every bill from all 50
            states and D.C. is pulled from Open States and refreshed as it moves, alongside circular-economy
            law from the EU and national governments worldwide, drawn from each jurisdiction&apos;s official
            source.
          </li>
          <li>
            <span className="text-text-primary font-medium">2. Pre-screen.</span> A curated, weighted
            circular-economy lexicon narrows the full legislative universe to plausible candidates, so the
            deeper analysis is spent only on bills that might be relevant. (The specific terms and weights
            are proprietary.)
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
        <h2 className="font-serif text-xl text-text-primary">Beyond the flag — what we build on it</h2>
        <p className="text-text-secondary text-body leading-relaxed">
          Classification is the foundation, not the finish. Once a bill is flagged relevant, the same
          engine turns it into working intelligence across the platform:
        </p>
        <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-body text-text-secondary">
          <li>
            <span className="text-text-primary font-medium">Compliance extraction</span> — deadlines,
            covered products, producer obligations, fees, and penalties pulled from the bill text, on
            each bill&apos;s{' '}
            <Link href="/compliance" className="text-green-accent hover:underline">deadline &amp; obligation view</Link>.
          </li>
          <li>
            <span className="text-text-primary font-medium">Structured dimensions</span> — eco-modulation,
            recycled-content and collection targets captured as comparable, citation-backed envelopes.
          </li>
          <li>
            <span className="text-text-primary font-medium">Full-text search</span> — the ingested
            statute text is indexed, so a search reaches inside the law, not just its title.
          </li>
          <li>
            <span className="text-text-primary font-medium">Jurisdiction profiles</span> — bill activity
            rolled up per{' '}
            <Link href="/states" className="text-green-accent hover:underline">state</Link> and{' '}
            <Link href="/jurisdictions" className="text-green-accent hover:underline">country</Link>,
            with cross-border comparison in{' '}
            <Link href="/insights" className="text-green-accent hover:underline">Insights</Link>.
          </li>
          <li>
            <span className="text-text-primary font-medium">Litigation signals</span> — federal
            preemption and related cases tracked alongside the bills they touch on{' '}
            <Link href="/federal" className="text-green-accent hover:underline">Federal Actions</Link>.
          </li>
          <li>
            <span className="text-text-primary font-medium">Research</span> — natural-language questions
            answered against the corpus with cited sources in{' '}
            <Link href="/ask" className="text-green-accent hover:underline">Ask the Atlas</Link>.
          </li>
        </ul>
        <p className="text-text-muted text-xs leading-relaxed">
          Every layer above is traceable to the classified bill and its primary source — the same
          auditable standard as the relevance call itself.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="font-serif text-xl text-text-primary">Auto-classified vs. reviewed</h2>
        <p className="text-text-secondary text-body leading-relaxed">
          Each bill is first <strong className="text-text-primary">auto-classified</strong>: a language
          model reads the title, summary, and text and decides whether it touches one of the tracked
          instruments, with a confidence score and the material streams it affects. Compliance details
          (deadlines, covered products, producer obligations) are then extracted from the bill text.
        </p>
        <p className="text-text-secondary text-body leading-relaxed">
          A bill marked <span className="text-green-accent">reviewed</span> has additionally been
          spot-checked by a human. Anything not yet reviewed carries only the automated call — shown
          on each bill so you always know which is which.
        </p>
        <p className="text-text-secondary text-body leading-relaxed">
          Classifications are automated and can contain errors; always verify against the primary
          source before acting. We continuously expand the reviewed set.
        </p>
      </section>

      {/* FAQ — the objections a reader arrives with, answered where the method is already being
          explained. Copy is shared with the pricing tiers (lib/tiers FAIR_QUESTIONS) so the scale and
          coverage answers can't drift from the prices they justify; the counts are the live ones above. */}
      <section className="border-t border-border-default pt-6 space-y-4">
        <div>
          <h2 className="font-serif text-xl text-text-primary">{FAIR_QUESTIONS.title}</h2>
          <p className="text-text-secondary text-body leading-relaxed mt-1">{FAIR_QUESTIONS.lede}</p>
        </div>
        <div className="space-y-5">
          {FAIR_QUESTIONS.items({ measures: relevant, regions: regionCount }).map(item => (
            <div key={item.q}>
              <h3 className="font-serif text-base text-text-primary leading-snug">{item.q}</h3>
              <p className="text-text-secondary text-body leading-relaxed mt-1">{item.a}</p>
            </div>
          ))}
        </div>
        <p className="text-meta text-text-muted">
          More questions? The <Link href="/faq" className="text-green-accent hover:underline">full FAQ</Link>{' '}
          covers what&apos;s free vs. Pro, alerts, and the API.
        </p>
      </section>

      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <p className="text-text-secondary text-body">See a miscall? Help us correct it.</p>
        <a
          href="mailto:kenny@superfun.studio?subject=Atlas%20Circular%20classification%20flag&body=Bill%20(state%20%2B%20number):%0AWhat%20looks%20wrong:%0A"
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
