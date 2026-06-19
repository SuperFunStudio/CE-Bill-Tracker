'use client';
import { useEffect, useMemo, useState } from 'react';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { CompassIcon, LockIcon } from '@/components/ui/icons';
import { useAuth } from '@/components/auth/AuthContext';
import { useBills } from '@/hooks/useBills';
import { BillModal } from '@/components/ui/BillModal';
import { PrincipleCard } from '@/components/design-guide/PrincipleCard';
import { startProCheckout, openFullGuide } from '@/lib/billing';
import { upgradeLabel } from '@/lib/tiers';
import { track } from '@/lib/analytics';
import { TEASER_LEVERS, GUIDE_COVERAGE, type TeaserLever } from '@/data/designGuideTeaser';

// The Free teaser surfaces the headline design imperative per lever — what to design for, which
// products/materials it lands on, and the grounded source bills behind it (each opens the same
// modal as the Bill Explorer). The full guide (every imperative, numeric targets, statutory
// evidence, printable) is the Pro deliverable; the SKU/portfolio-scoped version is Enterprise.

const BOOKING_URL = 'https://calendar.app.google/QPXh1qXWhNWxXo9n6';

// Two reading groups, ordered deliberately (not the raw dataset order). First: the Re-X design
// principles — strategies that keep material in use, highest-value at the top (reuse/repair)
// descending to the recovery pathways (recycle → recycled content → compost). Then the material &
// disclosure rules: what a product is made of and what must be declared on it.
const GROUPS: { label: string; blurb: string; levers: string[] }[] = [
  {
    label: 'Keep it in the loop',
    blurb:
      'The Re-X Design Principles extracted from enacted bills. Design for material circulation, highest-value first: reuse and repair down through recycling and composting.',
    levers: [
      'reuse_refill',
      'repairability_durability',
      'source_reduction',
      'design_for_recycling',
      'recycled_content',
      'compostability',
    ],
  },
  {
    label: 'Material & disclosure',
    blurb: 'What a product is made of — and what you have to declare on it.',
    levers: ['material_restriction', 'toxics_elimination', 'labeling_marking'],
  },
];

// Front-of-card "Design for …" framing for the Re-X principles. The card back keeps the canonical
// lever name (lever.name, e.g. "Compostability — sources") so the source bills stay tied to the
// classified data; levers without an override fall back to lever.name on both faces.
const LEVER_DISPLAY_NAME: Record<string, string> = {
  reuse_refill: 'Design for Reuse & Refill',
  repairability_durability: 'Design for Repairability & Durability',
  source_reduction: 'Design for Reduction',
  design_for_recycling: 'Design for Recycling',
  compostability: 'Design for regeneration',
};

const LEVER_BY_KEY = new Map<string, TeaserLever>(TEASER_LEVERS.map(l => [l.lever, l]));

export default function DesignGuidePage() {
  const { user, isPro, loading, openAuth, getToken, refreshEntitlement } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Bill tags on a flipped principle card open the shared BillModal. We resolve a bill id to a
  // full BillSummary from the same dataset the Bill Explorer uses.
  const { data: bills = [] } = useBills({ ce_relevant: true, limit: 5000 });
  const billsById = useMemo(() => new Map(bills.map(b => [b.id, b])), [bills]);
  const [selectedBillId, setSelectedBillId] = useState<number | null>(null);
  const selectedBill = selectedBillId != null ? billsById.get(selectedBillId) ?? null : null;

  // Returning from Stripe Checkout: the webhook may have just upgraded this account, so re-check
  // entitlement a few times (webhook delivery can lag the redirect by a second or two).
  useEffect(() => {
    if (typeof window === 'undefined' || !window.location.search.includes('checkout=success')) return;
    let n = 0;
    const t = setInterval(() => {
      refreshEntitlement();
      if (++n >= 4) clearInterval(t);
    }, 1500);
    return () => clearInterval(t);
  }, [refreshEntitlement]);

  async function handlePrimary() {
    setError('');
    // The Pro-gate CTA: which action it resolves to is the conversion intent on this page —
    // sign_in (anon), upgrade (free user), or open_guide (already Pro).
    track('design_guide_cta', { action: !user ? 'sign_in' : isPro ? 'open_guide' : 'upgrade' });
    if (!user) {
      openAuth();
      return;
    }
    setBusy(true);
    try {
      if (isPro) await openFullGuide(getToken);
      else await startProCheckout(getToken);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  const ctaLabel = !user
    ? 'Sign in to unlock →'
    : isPro
      ? 'Open the full guide →'
      : upgradeLabel();

  return (
    <div className="p-6 space-y-8 max-w-6xl mx-auto">
      <GazetteHeader
        title="Design Guide"
        subtitle="What circular-economy law already requires you to design for — and what ignoring it will cost."
      />

      <p className="text-text-secondary text-sm leading-relaxed max-w-3xl">
        The Battle of the Bills online design guide is built dynamically from the bills ingested into
        the foundational database. Every design principle below is sourced from enacted and proposed
        US bills and it stays current as legislation moves. Stay ahead of non-compliant SKUs, fee
        penalties, and ensure you adapt to changing market conditions. Assembled from{' '}
        <span className="text-text-primary font-medium">{GUIDE_COVERAGE.bills} bills</span> across{' '}
        <span className="text-text-primary font-medium">{GUIDE_COVERAGE.states} states</span>.
      </p>

      <p className="text-text-muted text-xs -mt-4">
        Flip any card (↻) to see the bills it’s sourced from — each opens the full bill detail.
      </p>

      {GROUPS.map(group => {
        const levers = group.levers
          .map(k => LEVER_BY_KEY.get(k))
          .filter((l): l is TeaserLever => Boolean(l));
        if (!levers.length) return null;
        return (
          <section key={group.label} className="space-y-3">
            <div className="flex items-baseline gap-3 flex-wrap">
              <h2 className="font-serif text-lg text-text-primary">{group.label}</h2>
              <p className="text-text-muted text-xs leading-relaxed">{group.blurb}</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
              {levers.map(l => (
                <PrincipleCard
                  key={l.lever}
                  lever={l}
                  displayName={LEVER_DISPLAY_NAME[l.lever]}
                  onOpenBill={setSelectedBillId}
                />
              ))}
            </div>
          </section>
        );
      })}

      <BillModal bill={selectedBill} onClose={() => setSelectedBillId(null)} />

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
        <div className="shrink-0 flex flex-col items-stretch gap-1.5">
          <button
            onClick={handlePrimary}
            disabled={busy || loading}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-green-accent text-bg-primary px-5 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {isPro ? <CompassIcon className="text-sm" /> : <LockIcon className="text-sm" />}
            {busy ? 'Working…' : ctaLabel}
          </button>
          {isPro && <span className="text-green-accent text-xs text-center">✓ Pro — full access</span>}
          {error && <span className="text-urgency-high text-xs text-center max-w-[14rem]">{error}</span>}
        </div>
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
          Get in touch →
        </a>
      </section>
    </div>
  );
}
