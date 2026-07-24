'use client';
import { useState } from 'react';
import type { TeaserLever } from '@/data/designGuideTeaser';
import { PrincipleIcon } from './leverVisuals';
import { track } from '@/lib/analytics';

interface PrincipleCardProps {
  lever: TeaserLever;
  /** Front-face title override (the "Design for …" framing). Falls back to lever.name. */
  displayName?: string;
  /** 1-based position in the deck, shown as "N / total". */
  index?: number;
  total?: number;
  /** Open the shared bill modal for a given bill id. */
  onOpenBill: (billId: number) => void;
  /** Scroll this card into its pinned position — the header bar acts as a table-of-contents link. */
  onFocusCard?: () => void;
  /** 0..1 activity level (this lever's bill count / the deck max) — drives the card's accent depth. */
  activity?: number;
  /** Fixed header-bar height in px; MUST match the deck's cascade offset so headers stack cleanly. */
  headerHeight?: number;
}

// The card has a flush, fixed-height HEADER BAR and a padded BODY. In the deck the header pins at a
// cascading offset, so scrolling leaves a stack of headers (each a link back to its card). The body
// holds the principle: three cited examples + fee direction on the front; the full source-bill list
// on the back. Accent reuses the maps' activity gradient — brand green at an alpha scaled by how
// much law backs the principle — as a colored top edge, a header wash, and the icon tile.
export function PrincipleCard({
  lever,
  displayName,
  index,
  total,
  onOpenBill,
  onFocusCard,
  activity = 0,
  headerHeight = 52,
}: PrincipleCardProps) {
  const [flipped, setFlipped] = useState(false);
  const billCount = lever.bills.length;
  const title = displayName ?? lever.name;
  const examples =
    lever.examples.length > 0
      ? lever.examples
      : [{ action: lever.direction, state: lever.evidence?.state ?? '', billNumber: lever.evidence?.bill ?? '', billId: 0, quote: '' }];

  const a01 = Math.max(0, Math.min(1, activity));
  const accentA = 0.25 + 0.7 * Math.sqrt(a01);
  const acc = (a: number) => `rgb(var(--green-accent) / ${a.toFixed(3)})`;
  const faceAccent = { borderTopColor: acc(accentA), borderTopWidth: 3 } as const;
  const headerStyle = { height: headerHeight, background: acc(accentA * 0.16) } as const;
  const iconTile = { background: acc(accentA * 0.24) } as const;

  const faceCls =
    '[grid-area:1/1] flex flex-col overflow-hidden rounded-2xl border bg-bg-secondary shadow-lg [backface-visibility:hidden]';

  return (
    <div className="[perspective:1400px]">
      {/* Both faces share one grid cell so the card auto-sizes to the taller face and the height
          stays stable across the flip (no jump). */}
      <div
        className="grid min-h-[360px] transition-transform duration-500 [transform-style:preserve-3d]"
        style={{ transform: flipped ? 'rotateY(180deg)' : undefined }}
      >
        {/* ---- FRONT ---- */}
        <div
          className={`${faceCls} border-border-default ${flipped ? 'pointer-events-none' : ''}`}
          style={faceAccent}
          aria-hidden={flipped}
        >
          {/* Header bar — flush, fixed height; pins & stacks in the deck and links back to this card. */}
          <button
            type="button"
            onClick={onFocusCard}
            style={headerStyle}
            className="group shrink-0 w-full flex items-center gap-3 px-5 sm:px-6 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-green-accent/50"
            aria-label={`Scroll to ${title}`}
          >
            <span className="shrink-0 grid place-items-center h-8 w-8 rounded-lg text-green-accent text-lg" style={iconTile}>
              <PrincipleIcon lever={lever.lever} />
            </span>
            <h3 className="flex-1 min-w-0 font-serif text-base sm:text-lg text-text-primary leading-tight truncate group-hover:text-green-accent transition-colors">
              {title}
            </h3>
            {index && total && (
              <span className="shrink-0 text-meta text-text-muted tabular-nums">{index} / {total}</span>
            )}
          </button>

          {/* Body */}
          <div className="flex-1 flex flex-col px-5 sm:px-6 pb-5 sm:pb-6 pt-1">
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
        </div>

        {/* ---- BACK ---- */}
        <div
          className={`${faceCls} border-green-accent/50 [transform:rotateY(180deg)] ${flipped ? '' : 'pointer-events-none'}`}
          style={faceAccent}
          aria-hidden={!flipped}
        >
          <div style={headerStyle} className="shrink-0 w-full flex items-center gap-3 px-5 sm:px-6">
            <span className="shrink-0 grid place-items-center h-8 w-8 rounded-lg text-green-accent text-lg" style={iconTile}>
              <PrincipleIcon lever={lever.lever} />
            </span>
            <button
              type="button"
              onClick={onFocusCard}
              className="flex-1 min-w-0 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/50 rounded-sm"
              aria-label={`Scroll to ${lever.name}`}
            >
              <h3 className="font-serif text-base text-text-primary leading-tight truncate">{lever.name} — sources</h3>
            </button>
            <button
              type="button"
              onClick={() => setFlipped(false)}
              className="shrink-0 flex items-center gap-1 text-text-muted text-xs hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/50 rounded-sm"
              aria-label="Back to principle"
            >
              <span aria-hidden>↩</span> Back
            </button>
          </div>

          <div className="flex-1 flex flex-col min-h-0 px-5 sm:px-6 pb-5 sm:pb-6 pt-2">
            {lever.evidence && lever.evidence.quote && (
              <blockquote className="border-l-2 border-green-accent/40 pl-3 text-text-muted text-xs italic leading-relaxed mb-3">
                “{lever.evidence.quote}”
              </blockquote>
            )}

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
              {billCount} bill{billCount === 1 ? '' : 's'} · scroll · tap to read
            </p>
            {/* Capped + scrollable so a lever with 200+ cited bills doesn't stretch the shared card
                cell (which would push the front's flip button below the fold and open a blank gap). */}
            <div className="flex flex-wrap content-start gap-1.5 max-h-[190px] overflow-y-auto -mr-1 pr-1">
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
    </div>
  );
}
