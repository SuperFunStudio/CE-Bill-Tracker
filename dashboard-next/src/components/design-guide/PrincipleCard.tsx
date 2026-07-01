'use client';
import { useState } from 'react';
import type { TeaserLever } from '@/data/designGuideTeaser';
import { track } from '@/lib/analytics';

interface PrincipleCardProps {
  lever: TeaserLever;
  /** Front-face title override (the "Design for …" framing). Falls back to lever.name. */
  displayName?: string;
  /** Open the shared bill modal for a given bill id. */
  onOpenBill: (billId: number) => void;
}

// Front: what to design and which products/materials it applies to.
// Back: the grounded source bills — each tag opens the same modal used in the Bill Explorer.
export function PrincipleCard({ lever, displayName, onOpenBill }: PrincipleCardProps) {
  const [flipped, setFlipped] = useState(false);
  const billCount = lever.bills.length;
  // The front face carries the principle framing; the back stays tied to the canonical lever name.
  const title = displayName ?? lever.name;

  return (
    <div className="[perspective:1400px] min-h-[320px]">
      <div
        className="relative h-full min-h-[320px] transition-transform duration-500 [transform-style:preserve-3d]"
        style={{ transform: flipped ? 'rotateY(180deg)' : undefined }}
      >
        {/* ---- FRONT ---- */}
        <div
          className="absolute inset-0 flex flex-col overflow-hidden rounded-xl border border-border-default bg-bg-secondary p-5 [backface-visibility:hidden]"
          aria-hidden={flipped}
        >
          <h3 className="font-serif text-lg text-text-primary leading-tight mb-2">{title}</h3>
          <p className="text-text-primary text-sm font-medium mb-1.5">{lever.headline}</p>
          {lever.direction && (
            <p className="text-text-secondary text-body leading-relaxed mb-4">{lever.direction}</p>
          )}

          <div className="mt-auto space-y-3">
            {/* Fee impact (eco-modulation): does this design dimension raise or lower a producer's
                EPR fee, where is it a set rate (EU/foreign), and where is it still directional (US). */}
            {lever.feeImpact && (
              <div>
                <p className="text-meta uppercase tracking-wider text-text-muted mb-1.5">
                  Fee impact <span className="normal-case tracking-normal text-text-muted/70">· eco-modulation</span>
                </p>
                <div className="flex flex-wrap items-center gap-1.5">
                  {lever.feeImpact.malus && (
                    <span className="text-xs rounded-full border border-border-default bg-bg-tertiary px-2 py-0.5 text-text-secondary">
                      ↑ Malus · poor design costs more
                    </span>
                  )}
                  {lever.feeImpact.bonus && (
                    <span className="text-xs rounded-full border border-green-accent/40 bg-green-dark/20 px-2 py-0.5 text-green-accent">
                      ↓ Bonus · good design pays less
                    </span>
                  )}
                </div>
                {lever.feeImpact.examples.length > 0 && (
                  <p className="text-xs text-text-secondary mt-1.5">
                    {lever.feeImpact.examples.map(e => `${e.jurisdiction} ${e.amount}`).join(' · ')}
                  </p>
                )}
                <p className="text-meta text-text-muted mt-1">
                  {lever.feeImpact.setJurisdictions.length > 0 && (
                    <>Set in {lever.feeImpact.setJurisdictions.slice(0, 5).join(', ')}
                      {lever.feeImpact.setJurisdictions.length > 5 ? ` +${lever.feeImpact.setJurisdictions.length - 5}` : ''}</>
                  )}
                  {lever.feeImpact.usPending && <> · US: rate TBD (CAA)</>}
                </p>
              </div>
            )}

            {/* Applies to — the products / materials a designer should map this onto */}
            <div>
              <p className="text-meta uppercase tracking-wider text-text-muted mb-1.5">Applies to</p>
              <div className="flex flex-wrap gap-1.5">
                {lever.focus.map(f => (
                  <span
                    key={f}
                    className="text-xs rounded-full border border-border-default bg-bg-tertiary px-2 py-0.5 text-text-secondary"
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              track('design_card_flip', { lever: lever.lever, name: lever.name, bill_count: billCount });
              setFlipped(true);
            }}
            className="mt-4 pt-3 border-t border-border-default flex items-center justify-between gap-2 text-left text-green-accent text-xs font-medium hover:opacity-80 focus:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/50 rounded-sm transition-opacity"
            aria-label={`Show the ${billCount} bills behind ${title}`}
          >
            <span>Sourced from {billCount} bill{billCount === 1 ? '' : 's'}</span>
            <span aria-hidden className="text-sm">↻</span>
          </button>
        </div>

        {/* ---- BACK ---- */}
        <div
          className="absolute inset-0 flex flex-col overflow-hidden rounded-xl border border-green-accent/50 bg-bg-secondary p-5 [transform:rotateY(180deg)] [backface-visibility:hidden]"
          aria-hidden={!flipped}
        >
          <div className="flex items-center justify-between gap-2 mb-2">
            <h3 className="font-serif text-base text-text-primary leading-tight">{lever.name} — sources</h3>
            <button
              type="button"
              onClick={() => setFlipped(false)}
              className="shrink-0 flex items-center gap-1 text-text-muted text-xs hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/50 rounded-sm"
              aria-label="Back to principle"
            >
              <span aria-hidden>↩</span> Back
            </button>
          </div>

          {lever.evidence && (
            <blockquote className="border-l-2 border-green-accent/40 pl-3 text-text-muted text-xs italic leading-relaxed mb-3">
              “{lever.evidence.quote}”
            </blockquote>
          )}

          <p className="text-meta uppercase tracking-wider text-text-muted mb-1.5">
            {billCount} bill{billCount === 1 ? '' : 's'} · tap to read
          </p>
          <div className="flex flex-wrap content-start gap-1.5 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
            {lever.bills.map(b => (
              <button
                key={b.billId}
                type="button"
                onClick={() => {
                  track('design_source_bill_open', { lever: lever.lever, bill_id: b.billId, state: b.state });
                  onOpenBill(b.billId);
                }}
                className="text-xs rounded-full border border-border-default bg-bg-tertiary px-2 py-0.5 text-text-secondary hover:border-green-accent hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/50 transition-colors"
              >
                <span className="font-mono text-meta text-text-muted">{b.state}</span> {b.billNumber}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
