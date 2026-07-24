'use client';
import { useState } from 'react';
import type { TeaserLever } from '@/data/designGuideTeaser';
import { PrincipleIcon } from './leverVisuals';
import { track } from '@/lib/analytics';

interface PrincipleCardProps {
  lever: TeaserLever;
  /** Front-face title override (the "Design for …" framing). Falls back to lever.name. */
  displayName?: string;
  /** Small eyebrow label above the title (the reading group this principle belongs to). */
  group?: string;
  /** 1-based position in the deck, shown as "N / total". */
  index?: number;
  total?: number;
  /** Open the shared bill modal for a given bill id. */
  onOpenBill: (billId: number) => void;
}

// Front: the principle, three concrete design examples (each citing the bill behind it), and the
// fee direction. Back: the full source-bill list plus where fees are actually set. Every cited
// chip opens the same modal used in the Bill Explorer.
export function PrincipleCard({ lever, displayName, group, index, total, onOpenBill }: PrincipleCardProps) {
  const [flipped, setFlipped] = useState(false);
  const billCount = lever.bills.length;
  const title = displayName ?? lever.name;
  // Prefer the three cited examples; fall back to the single direction line if a lever has none.
  const examples =
    lever.examples.length > 0
      ? lever.examples
      : [{ action: lever.direction, state: lever.evidence?.state ?? '', billNumber: lever.evidence?.bill ?? '', billId: 0, quote: '' }];

  return (
    <div className="[perspective:1400px]">
      {/* Both faces share one grid cell so the card auto-sizes to the taller face and the height
          stays stable across the flip (no jump). */}
      <div
        className="grid min-h-[380px] transition-transform duration-500 [transform-style:preserve-3d]"
        style={{ transform: flipped ? 'rotateY(180deg)' : undefined }}
      >
        {/* ---- FRONT ---- */}
        <div
          className={`[grid-area:1/1] flex flex-col overflow-hidden rounded-2xl border border-border-default bg-bg-secondary p-5 sm:p-6 shadow-sm [backface-visibility:hidden] ${flipped ? 'pointer-events-none' : ''}`}
          aria-hidden={flipped}
        >
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex items-center gap-3 min-w-0">
              <span className="shrink-0 grid place-items-center h-10 w-10 rounded-xl bg-green-dark/20 text-green-accent text-xl">
                <PrincipleIcon lever={lever.lever} />
              </span>
              <div className="min-w-0">
                {group && (
                  <p className="text-meta uppercase tracking-wider text-text-muted truncate">{group}</p>
                )}
                <h3 className="font-serif text-lg text-text-primary leading-tight">{title}</h3>
              </div>
            </div>
            {index && total && (
              <span className="shrink-0 text-meta text-text-muted tabular-nums pt-1">
                {index} / {total}
              </span>
            )}
          </div>

          <p className="text-text-primary text-sm font-medium mb-3">{lever.headline}</p>

          {/* Three concrete examples — the heart of the card. Each cites the bill it came from. */}
          <p className="text-meta uppercase tracking-wider text-text-muted mb-2">In practice</p>
          <ol className="space-y-2.5 mb-4">
            {examples.map((ex, i) => (
              <li key={`${ex.billId}-${i}`} className="flex gap-2.5">
                <span className="mt-0.5 shrink-0 grid place-items-center h-5 w-5 rounded-full border border-green-accent/40 text-green-accent text-[11px] font-medium tabular-nums">
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <span className="text-text-secondary text-sm leading-relaxed">{ex.action}</span>{' '}
                  {ex.billId > 0 && ex.billNumber && (
                    <button
                      type="button"
                      onClick={() => {
                        track('design_source_bill_open', { lever: lever.lever, bill_id: ex.billId, state: ex.state });
                        onOpenBill(ex.billId);
                      }}
                      className="inline-flex items-center gap-1 align-baseline text-xs rounded-full border border-border-default bg-bg-tertiary px-1.5 py-0.5 text-text-muted hover:border-green-accent hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/50 transition-colors"
                      aria-label={`Open ${ex.state} ${ex.billNumber}`}
                    >
                      <span className="font-mono">{ex.state}</span> {ex.billNumber}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-auto space-y-3">
            {/* Fee direction (eco-modulation): does this lever raise or lower a producer's EPR fee.
                The where/how-much detail lives on the back. */}
            {lever.feeImpact && (lever.feeImpact.malus || lever.feeImpact.bonus) && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-meta uppercase tracking-wider text-text-muted mr-1">Fees</span>
                {lever.feeImpact.malus && (
                  <span className="text-xs rounded-full border border-border-default bg-bg-tertiary px-2 py-0.5 text-text-secondary">
                    ↑ Raises
                  </span>
                )}
                {lever.feeImpact.bonus && (
                  <span className="text-xs rounded-full border border-green-accent/40 bg-green-dark/20 px-2 py-0.5 text-green-accent">
                    ↓ Lowers
                  </span>
                )}
              </div>
            )}

            {/* Applies to — the products / materials a designer maps this onto */}
            <div>
              <p className="text-meta uppercase tracking-wider text-text-muted mb-1.5">Applies to</p>
              <div className="flex flex-wrap gap-1.5">
                {lever.focus.slice(0, 5).map(f => (
                  <span
                    key={f}
                    className="text-xs rounded-full border border-border-default bg-bg-tertiary px-2 py-0.5 text-text-secondary"
                  >
                    {f}
                  </span>
                ))}
                {lever.focus.length > 5 && (
                  <span className="text-xs text-text-muted px-1 py-0.5">+{lever.focus.length - 5}</span>
                )}
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
          className={`[grid-area:1/1] flex flex-col overflow-hidden rounded-2xl border border-green-accent/50 bg-bg-secondary p-5 sm:p-6 shadow-sm [transform:rotateY(180deg)] [backface-visibility:hidden] ${flipped ? '' : 'pointer-events-none'}`}
          aria-hidden={!flipped}
        >
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="shrink-0 text-green-accent text-lg">
                <PrincipleIcon lever={lever.lever} />
              </span>
              <h3 className="font-serif text-base text-text-primary leading-tight truncate">{lever.name} — sources</h3>
            </div>
            <button
              type="button"
              onClick={() => setFlipped(false)}
              className="shrink-0 flex items-center gap-1 text-text-muted text-xs hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/50 rounded-sm"
              aria-label="Back to principle"
            >
              <span aria-hidden>↩</span> Back
            </button>
          </div>

          {lever.evidence && lever.evidence.quote && (
            <blockquote className="border-l-2 border-green-accent/40 pl-3 text-text-muted text-xs italic leading-relaxed mb-3">
              “{lever.evidence.quote}”
            </blockquote>
          )}

          {/* Where fees are actually set (moved off the front to keep it focused). */}
          {lever.feeImpact && (lever.feeImpact.setJurisdictions.length > 0 || lever.feeImpact.usPending) && (
            <p className="text-meta text-text-muted mb-3">
              {lever.feeImpact.examples.length > 0 && (
                <span className="text-text-secondary">
                  {lever.feeImpact.examples.map(e => `${e.jurisdiction} ${e.amount}`).join(' · ')}
                  {' · '}
                </span>
              )}
              {lever.feeImpact.setJurisdictions.length > 0 && (
                <>Set in {lever.feeImpact.setJurisdictions.slice(0, 6).join(', ')}
                  {lever.feeImpact.setJurisdictions.length > 6 ? ` +${lever.feeImpact.setJurisdictions.length - 6}` : ''}</>
              )}
              {lever.feeImpact.usPending && <> · US: rate TBD (CAA)</>}
            </p>
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
