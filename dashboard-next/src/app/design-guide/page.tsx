'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { CompassIcon, LockIcon } from '@/components/ui/icons';
import { CAP, useAuth } from '@/components/auth/AuthContext';
import { useBills } from '@/hooks/useBills';
import { BillModal } from '@/components/ui/BillModal';
import { PrincipleCard } from '@/components/design-guide/PrincipleCard';
import { GuidesTabs } from '@/components/guides/GuidesTabs';
import { openFullGuide, billingErrorMessage } from '@/lib/billing';
import { track } from '@/lib/analytics';
import { TEASER_LEVERS, GUIDE_COVERAGE, type TeaserLever } from '@/data/designGuideTeaser';

// The Free teaser surfaces the headline design imperative per lever — what to design for, three
// grounded examples, which products/materials it lands on, and the source bills behind it (each
// opens the same modal as the Bill Explorer). The full guide (every imperative, numeric targets,
// statutory evidence, printable) is the Pro deliverable; the SKU-scoped version is Enterprise.

const BOOKING_URL = 'https://calendar.app.google/QPXh1qXWhNWxXo9n6';

// Deck geometry: cards pin at DECK_TOP + i·HEADER_H so each header stacks below the previous one.
// HEADER_H must equal PrincipleCard's header-bar height for the collapsed strip to be exactly the header.
const DECK_TOP = 8;
const HEADER_H = 52;

// The deck is read as one sequence — the Re-X principles first (highest-value: reuse/repair down
// through recycling and composting), then the material & disclosure rules. Each card carries its
// reading group as an eyebrow so the grouping survives the flat scroll.
const DECK: { lever: string; group: string }[] = [
  { lever: 'reuse_refill', group: 'Keep it in the loop' },
  { lever: 'repairability_durability', group: 'Keep it in the loop' },
  { lever: 'source_reduction', group: 'Keep it in the loop' },
  { lever: 'design_for_recycling', group: 'Keep it in the loop' },
  { lever: 'recycled_content', group: 'Keep it in the loop' },
  { lever: 'compostability', group: 'Keep it in the loop' },
  { lever: 'material_restriction', group: 'Material & disclosure' },
  { lever: 'toxics_elimination', group: 'Material & disclosure' },
  { lever: 'labeling_marking', group: 'Material & disclosure' },
];

// Front-of-card "Design for …" framing for the Re-X principles. The card back keeps the canonical
// lever name so the source bills stay tied to the classified data; levers without an override fall
// back to lever.name on both faces.
const LEVER_DISPLAY_NAME: Record<string, string> = {
  reuse_refill: 'Design for Reuse & Refill',
  repairability_durability: 'Design for Repairability & Durability',
  source_reduction: 'Design for Reduction',
  design_for_recycling: 'Design for Recycling',
  compostability: 'Design for Regeneration',
};

const LEVER_BY_KEY = new Map<string, TeaserLever>(TEASER_LEVERS.map(l => [l.lever, l]));

export default function DesignGuidePage() {
  const { user, hasCapability, loading, openAuth, getToken, refreshEntitlement } = useAuth();
  const canGuide = hasCapability(CAP.DESIGN_GUIDE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const { data: bills = [] } = useBills({ ce_relevant: true, limit: 5000, regions: 'all' });
  const billsById = useMemo(() => new Map(bills.map(b => [b.id, b])), [bills]);
  const [selectedBillId, setSelectedBillId] = useState<number | null>(null);
  const selectedBill = selectedBillId != null ? billsById.get(selectedBillId) ?? null : null;

  // The ordered, resolved deck (drops any lever missing from the teaser data).
  const deck = useMemo(
    () =>
      DECK.map(d => ({ ...d, lever: LEVER_BY_KEY.get(d.lever) }))
        .filter((d): d is { lever: TeaserLever; group: string } => Boolean(d.lever)),
    [],
  );
  // Deck-wide max bill count — normalizes each card's activity level (0..1) for its accent color.
  const maxBills = useMemo(() => Math.max(1, ...deck.map(d => d.lever.bills.length)), [deck]);

  // Each card's header bar pins at a cascading offset (DECK_TOP + i·HEADER_H) so every previous
  // header stays stacked as you scroll — the accumulated stack is the table of contents, and each
  // header links back to its card. HEADER_H must match PrincipleCard's header-bar height.
  const slotRefs = useRef<(HTMLDivElement | null)[]>([]);
  const focusCard = (i: number) => slotRefs.current[i]?.scrollIntoView({ behavior: 'smooth', block: 'start' });

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
    track('design_guide_cta', { action: !user ? 'sign_in' : canGuide ? 'open_guide' : 'upgrade' });
    if (!user) {
      openAuth();
      return;
    }
    if (!canGuide) {
      window.location.href = '/pricing';
      return;
    }
    setBusy(true);
    try {
      await openFullGuide(getToken);
    } catch (e) {
      setError(billingErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const ctaLabel = !user ? 'Sign in to unlock →' : canGuide ? 'Open the full guide →' : 'See memberships →';

  return (
    <div className="p-6 space-y-8 max-w-6xl mx-auto">
      <GazetteHeader
        title="Guides"
        subtitle="What circular-economy law already requires you to design for — and what ignoring it will cost."
      />

      <GuidesTabs />

      <p className="text-text-secondary text-body leading-relaxed max-w-3xl">
        Every principle here is sourced from enacted and proposed bills &mdash;{' '}
        <span className="text-text-primary font-medium">{GUIDE_COVERAGE.bills} bills</span> across{' '}
        <span className="text-text-primary font-medium">{GUIDE_COVERAGE.states} states &amp; regions</span>, read
        line by line. Scroll to move through each principle; flip any card (&#8635;) to see the source
        bills. The guide stays current as legislation moves.
      </p>

      {/* ── The deck: each card's header pins at a cascading offset, so scrolling leaves a growing
             stack of headers. Those stacked headers double as the table of contents — click one to
             jump back to its card — which is why there's no separate index grid below. ── */}
      <div className="relative">
        {deck.map((d, i) => {
          const top = DECK_TOP + i * HEADER_H;
          return (
            <div
              key={d.lever.lever}
              ref={el => {
                slotRefs.current[i] = el;
              }}
              className="sticky"
              style={{ top, scrollMarginTop: top, zIndex: i + 1 }}
            >
              <PrincipleCard
                lever={d.lever}
                displayName={LEVER_DISPLAY_NAME[d.lever.lever]}
                index={i + 1}
                total={deck.length}
                activity={d.lever.bills.length / maxBills}
                headerHeight={HEADER_H}
                onFocusCard={() => {
                  track('design_header_jump', { lever: d.lever.lever, index: i });
                  focusCard(i);
                }}
                onOpenBill={setSelectedBillId}
              />
            </div>
          );
        })}
      </div>

      <BillModal bill={selectedBill} onClose={() => setSelectedBillId(null)} />

      {/* Pro gate — the full guide */}
      <section className="rounded-xl border border-green-accent bg-green-dark/20 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-5">
        <div className="max-w-2xl">
          <div className="flex items-center gap-2 mb-1">
            <CompassIcon className="text-green-accent text-lg" />
            <h3 className="font-serif text-xl text-text-primary">The full Design Guide</h3>
            <span className="text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
              Pro
            </span>
          </div>
          <p className="text-text-secondary text-body leading-relaxed">
            Each card above shows the headline imperative for one design lever. This is the full
            stack — every imperative, the exact numeric targets (percentages, dates), and the
            verbatim statutory language behind each line. Print-ready and kept current as bills move.
          </p>
        </div>
        <div className="shrink-0 flex flex-col items-stretch gap-1.5">
          <button
            onClick={handlePrimary}
            disabled={busy || loading}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-green-accent text-bg-primary px-5 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {canGuide ? <CompassIcon className="text-sm" /> : <LockIcon className="text-sm" />}
            {busy ? 'Working…' : ctaLabel}
          </button>
          {canGuide && <span className="text-green-accent text-xs text-center">✓ Member — full access</span>}
          {error && <span className="text-urgency-high text-xs text-center max-w-[14rem]">{error}</span>}
        </div>
      </section>

      {/* Enterprise / consulting line */}
      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <p className="text-text-secondary text-body leading-relaxed max-w-2xl">
          Need this scoped to your own products and the states you sell in — your SKUs mapped to
          the exact imperatives and deadlines that hit them? We build that per engagement.
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
