'use client';

import { useId } from 'react';
import type { KeyboardEvent, MouseEvent } from 'react';
import type { ButterflyCounts } from '@/lib/types';
import { BUTTERFLY_ICONS } from './butterflyIcons';

/**
 * The Ellen MacArthur "butterfly" (circular economy systems diagram), filled in with how many tracked
 * laws sit at each step. Counts come from /bills/butterfly (step placement: app/classification/butterfly.py).
 *
 * Geometry is fixed: the loops, boxes and node positions are the ones the butterfly explorer prototype
 * draws (docs/butterfly-explorer). The nine nodes that sit ON a loop were placed there by path length
 * and are hard-coded below so this renders without measuring the DOM.
 *
 * Two sizes: `full` (labels beside every node) and `compact` (the coverage fingerprint: no labels,
 * bigger nodes with icon + count). Shading is depth, not transparency: the quietest step is a soft
 * pastel of its wing colour, the busiest deepens toward ink, and every count is white with a thin dark
 * halo so it reads on all of them. A counted step with zero laws in scope is hatched, like a true gap.
 */

export type ButterflyStepId =
  | 'maintain' | 'share' | 'reuse' | 'refurb' | 'recycle' | 'content' | 'collect' | 'leak'
  | 'parts' | 'service' | 'compost' | 'extract' | 'cascade' | 'regen' | 'farm' | 'biogas';

type Wing = 'tech' | 'bio' | 'out';
type Side = 'right' | 'left' | 'above' | 'below';

interface NodeSpec {
  id: ButterflyStepId;
  name: string;           // for titles and the HTML legend
  wing: Wing;
  x: number;
  y: number;
  r: number;
  label: string;          // "\n" breaks the line
  side: Side;
  sub?: string;
  icon: string;
  /** No law maps to this step at all (Share), or it's out of scope by design (Biogas). */
  noSource?: boolean;
}

// Node layout from the explorer prototype (viewBox 0 0 1300 760).
export const BUTTERFLY_NODES: NodeSpec[] = [
  { id: 'recycle', name: 'Recycle', wing: 'tech', x: 1107.1, y: 213.6, r: 38, label: 'Recycle', side: 'right', sub: 'recycling & recovery targets', icon: 'recycle' },
  { id: 'content', name: 'Recycled content', wing: 'tech', x: 885.5, y: 75.3, r: 30, label: 'Recycled content', side: 'right', sub: 'minimums in new products', icon: 'package-plus' },
  { id: 'refurb', name: 'Refurbish / remanufacture', wing: 'tech', x: 1047.4, y: 314.7, r: 36, label: 'Refurbish /\nremanufacture', side: 'right', sub: 'repurpose · upcycle', icon: 'hammer' },
  { id: 'reuse', name: 'Reuse / redistribute', wing: 'tech', x: 971.9, y: 410.2, r: 38, label: 'Reuse /\nredistribute', side: 'right', sub: 'deposit-return', icon: 'repeat' },
  { id: 'maintain', name: 'Maintain / prolong', wing: 'tech', x: 817.7, y: 511.0, r: 40, label: 'Maintain /\nprolong', side: 'right', sub: 'right to repair', icon: 'wrench' },
  { id: 'share', name: 'Share', wing: 'tech', x: 860, y: 352, r: 26, label: 'Share', side: 'above', icon: 'share-2', noSource: true },
  { id: 'collect', name: 'Collection · EPR take-back', wing: 'tech', x: 714, y: 630, r: 44, label: 'Collection', side: 'right', sub: 'EPR take-back', icon: 'truck' },
  { id: 'leak', name: 'Minimise leakage', wing: 'tech', x: 650, y: 712, r: 30, label: 'Minimise leakage', side: 'right', sub: 'disposal bans', icon: 'trash-2' },
  { id: 'farm', name: 'Farming / collection', wing: 'bio', x: 343.5, y: 103.1, r: 36, label: 'Farming /\ncollection', side: 'above', icon: 'wheat' },
  { id: 'regen', name: 'Regeneration', wing: 'bio', x: 185.0, y: 350.8, r: 48, label: 'Regeneration', side: 'left', sub: 'biosphere', icon: 'earth' },
  { id: 'compost', name: 'Composting / anaerobic digestion', wing: 'bio', x: 295.4, y: 498.1, r: 38, label: 'Composting /\nanaerobic digestion', side: 'below', icon: 'sprout' },
  { id: 'extract', name: 'Biochemical feedstock', wing: 'bio', x: 334.9, y: 369.8, r: 32, label: 'Biochemical\nfeedstock', side: 'right', sub: 'extraction', icon: 'flask-conical' },
  { id: 'cascade', name: 'Cascades', wing: 'bio', x: 478, y: 486, r: 22, label: 'Cascades', side: 'above', icon: 'layers' },
  { id: 'biogas', name: 'Biogas / energy recovery', wing: 'out', x: 139.4, y: 386.1, r: 26, label: 'Biogas', side: 'left', sub: 'out of scope', icon: 'flame', noSource: true },
];

const BOXES: Array<{ y: number; title: string; step: ButterflyStepId | null; caption: string; icon: string }> = [
  { y: 46, title: 'Parts manufacturer', step: 'parts', caption: ' chemical restrictions', icon: 'factory' },
  { y: 136, title: 'Product manufacturer', step: null, caption: 'eco-modulated fees · inside EPR', icon: 'package' },
  { y: 226, title: 'Service provider', step: 'service', caption: ' labeling rules', icon: 'store' },
];

// Colours. Nodes keep these tones in both themes so the white counts always read; lines and text use
// the site's theme tokens.
const NODE = { tech: '#1e6ae9', bio: '#637c25', out: '#9aa1ab', ink: '#0b1633' };
const LINE = { tech: '#1e6ae9', bio: '#6f8a2e', out: '#9aa1ab' };

const BASE = 568;
// One user, where both cycles meet: the biological loops leave from its left (x 590), the technical
// from its right (x 710). Earlier drafts had separate Consumer and User circles at those two x's.
const CON = { x: 590, y: 440 };
const USR = { x: 710, y: 440 };
const USER = { x: 650, y: 440, r: 62 };
const BOX = { x: 520, w: 260, h: 54 };
const loop = (x0: number, yIn: number, xIn: number, rx: number, sweep: 0 | 1) =>
  `M ${x0} ${BASE} A ${rx} ${(BASE - yIn) / 2} 0 0 ${sweep} ${xIn} ${yIn}`;

const fmt = (n: number) => n.toLocaleString('en-US');

// The quietest step is a lightened wing hue, but no lighter than white text can sit on without an
// outline (70% hue at the pale end); the busiest deepens toward ink.
function nodeFill(base: string, n: number, max: number) {
  const t = Math.sqrt(n / Math.max(1, max));
  return t < 0.5
    ? `color-mix(in srgb, ${base} ${Math.round(70 + 60 * t)}%, #ffffff)`
    : `color-mix(in srgb, ${base} ${Math.round(100 - 80 * (t - 0.5))}%, ${NODE.ink})`;
}

function Icon({ name, cx, cy, size, color }: { name: string; cx: number; cy: number; size: number; color: string }) {
  return (
    <svg
      x={cx - size / 2}
      y={cy - size / 2}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: BUTTERFLY_ICONS[name] ?? '' }}
    />
  );
}

export function ButterflyDiagram({
  counts,
  compact = false,
  haloColor = 'var(--bg-secondary)',
  unit = 'laws',
  className,
  ariaLabel,
  onStepClick,
}: {
  counts: ButterflyCounts | null;
  /** Makes every counted step a button (mouse + keyboard); gets the step and the clicked element. */
  onStepClick?: (id: ButterflyStepId, el: SVGGElement) => void;
  /** The coverage-fingerprint size: icons and counts, no labels. */
  compact?: boolean;
  /** Background behind the drawing, used to halo labels where they cross a line. */
  haloColor?: string;
  /** Noun for tooltips ("laws", "laws in force", ...). */
  unit?: string;
  className?: string;
  ariaLabel?: string;
}) {
  const uid = useId().replace(/:/g, '');
  const hatch = `bf-hatch-${uid}`;
  const steps = counts?.steps ?? {};
  const get = (id: string) => steps[id] ?? 0;
  // Shade against the busiest wing step in this scope, so a small country still uses the full range.
  const max = Math.max(1, ...BUTTERFLY_NODES.filter(n => !n.noSource).map(n => get(n.id)));
  const marker = (w: keyof typeof LINE) => `url(#bf-ar-${w}-${uid})`;
  const lineProps = (w: keyof typeof LINE, width = 3.5) => ({ fill: 'none', stroke: LINE[w], strokeWidth: width });

  const labelStyle = {
    fontSize: 12.5, fontWeight: 700, letterSpacing: '.05em', textTransform: 'uppercase' as const,
    fill: 'var(--text-primary)', paintOrder: 'stroke' as const, stroke: haloColor, strokeWidth: 5, strokeLinejoin: 'round' as const,
  };
  const subStyle = { fontSize: 11.5, fill: 'var(--text-muted)', paintOrder: 'stroke' as const, stroke: haloColor, strokeWidth: 4 };
  const serif = 'var(--font-serif), Georgia, serif';
  const stepHandlers = (id: ButterflyStepId) => ({
    role: 'button',
    tabIndex: 0,
    style: { cursor: 'pointer' },
    className: 'bf-step',
    onClick: (e: MouseEvent<SVGGElement>) => onStepClick?.(id, e.currentTarget),
    onKeyDown: (e: KeyboardEvent<SVGGElement>) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onStepClick?.(id, e.currentTarget); }
    },
  });

  return (
    <svg
      viewBox={compact ? '90 20 1080 745' : '0 0 1300 760'}
      className={className}
      role="img"
      aria-label={ariaLabel ?? 'Circular economy butterfly diagram with law counts per step'}
      style={{ width: '100%', height: 'auto', display: 'block', fontFamily: 'var(--font-sans), Roboto, system-ui, sans-serif' }}
    >
      <defs>
        {(['bio', 'tech', 'out'] as const).map(w => (
          <marker key={w} id={`bf-ar-${w}-${uid}`} viewBox="0 0 10 10" refX={8} refY={5} markerWidth={6} markerHeight={6} orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill={LINE[w]} />
          </marker>
        ))}
        <pattern id={hatch} width={7} height={7} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width={7} height={7} fill="var(--bg-primary)" />
          <line x1={0} y1={0} x2={0} y2={7} stroke="#c3c8cf" strokeWidth={2.5} />
        </pattern>
      </defs>

      {/* Leakage basin and the two flows down into it. */}
      <path d="M 440 740 Q 650 640 860 740" fill="none" stroke="var(--text-muted)" strokeDasharray="2 4" />
      <path d={`M ${CON.x} ${BASE} V 680`} {...lineProps('bio', 2.5)} markerEnd={marker('bio')} />
      <path d={`M ${USR.x} ${BASE} V 680`} {...lineProps('tech', 2.5)} markerEnd={marker('tech')} />

      {/* The loops. */}
      <path d={loop(USR.x, 60, 784, 390, 0)} {...lineProps('tech')} markerEnd={marker('tech')} />
      <path d={loop(USR.x, 150, 784, 305, 0)} {...lineProps('tech')} markerEnd={marker('tech')} />
      <path d={loop(USR.x, 240, 784, 222, 0)} {...lineProps('tech')} markerEnd={marker('tech')} />
      <path d={loop(CON.x, 60, 516, 370, 1)} {...lineProps('bio')} markerEnd={marker('bio')} />
      <path d={loop(CON.x, 176, 516, 215, 1)} {...lineProps('bio')} markerEnd={marker('bio')} />
      <path d={`M ${USR.x + 20} ${BASE} A 95 70 0 1 0 ${USER.x + USER.r + 4} ${USER.y - 14}`} {...lineProps('tech')} markerEnd={marker('tech')} />
      {/* From the user down to collection, one flow per cycle (drawn under the user circle). */}
      <path d={`M ${USR.x} ${USER.y} V ${BASE}`} {...lineProps('tech', 2.5)} />
      <path d={`M ${CON.x} ${USER.y} V ${BASE}`} {...lineProps('bio', 2.5)} />
      {[28, 44, 60].map((rr, i) => (
        <path key={rr} d={`M ${CON.x + 42} ${BASE} A ${rr} ${rr + 6} 0 0 1 ${USER.x - USER.r - 2} ${USER.y + 22 - i * 4}`}
          {...lineProps('bio', 2.2)} markerEnd={marker('bio')} />
      ))}
      <path d={`M 842 370 Q 780 380 ${USER.x + 54} ${USER.y - 38}`} {...lineProps('tech', 2.2)} markerEnd={marker('tech')} />
      {!compact && (
        <path d="M 257.4 490.1 Q 205.4 438.1 163.4 406.1" fill="none" stroke={LINE.out} strokeWidth={2.5} strokeDasharray="5 5" markerEnd={marker('out')} />
      )}

      {/* The centre column: three boxes and the flows between them. */}
      {BOXES.map((b, i) => {
        const n = b.step ? get(b.step) : 0;
        return (
          <g key={b.title} {...(b.step && onStepClick && n > 0 ? stepHandlers(b.step) : {})}>
            <rect x={BOX.x} y={b.y} width={BOX.w} height={BOX.h} rx={27} fill="var(--bg-primary)" stroke="var(--border-default)" />
            {b.step && <title>{`${b.title}: ${fmt(n)} ${unit}${b.caption}`}</title>}
            {compact ? (
              <>
                <Icon name={b.icon} cx={b.step ? BOX.x + 44 : 650} cy={b.y + BOX.h / 2} size={34} color="var(--text-secondary)" />
                {b.step && (
                  <text x={668} y={b.y + 41} textAnchor="middle" style={{ fontFamily: serif, fontWeight: 700, fontSize: 38, fill: 'var(--text-primary)' }}>
                    {fmt(n)}
                  </text>
                )}
              </>
            ) : (
              <>
                <Icon name={b.icon} cx={BOX.x + 21} cy={b.y + BOX.h / 2} size={18} color="var(--text-secondary)" />
                <text x={650} y={b.y + 23} textAnchor="middle"
                  style={{ fontSize: 13, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', fill: 'var(--text-primary)' }}>
                  {b.title}
                </text>
                <text x={650} y={b.y + 41} textAnchor="middle" style={{ fontSize: 12, fill: 'var(--text-secondary)' }}>
                  {b.step && <tspan style={{ fontWeight: 600, fill: 'var(--text-primary)' }}>{fmt(n)}</tspan>}
                  <tspan>{b.caption}</tspan>
                </text>
              </>
            )}
            {i < BOXES.length - 1 && (
              <>
                <path d={`M 600 ${b.y + BOX.h} V ${BOXES[i + 1].y - 3}`} {...lineProps('bio', 2.5)} markerEnd={marker('bio')} />
                <path d={`M 700 ${b.y + BOX.h} V ${BOXES[i + 1].y - 3}`} {...lineProps('tech', 2.5)} markerEnd={marker('tech')} />
              </>
            )}
          </g>
        );
      })}
      <path d="M 600 280 V 399" {...lineProps('bio', 2.5)} markerEnd={marker('bio')} />
      <path d="M 700 280 V 399" {...lineProps('tech', 2.5)} markerEnd={marker('tech')} />

      {/* The user: one person where both cycles meet, half biological green and half technical blue. */}
      <g>
        <title>User: where the biological and technical cycles meet</title>
        <path d={`M ${USER.x} ${USER.y - USER.r} A ${USER.r} ${USER.r} 0 0 0 ${USER.x} ${USER.y + USER.r} Z`} fill={NODE.bio} />
        <path d={`M ${USER.x} ${USER.y - USER.r} A ${USER.r} ${USER.r} 0 0 1 ${USER.x} ${USER.y + USER.r} Z`} fill={NODE.tech} />
        {compact ? (
          <Icon name="user" cx={USER.x} cy={USER.y} size={64} color="#ffffff" />
        ) : (
          <>
            <Icon name="user" cx={USER.x} cy={USER.y - 13} size={38} color="#ffffff" />
            <text x={USER.x} y={USER.y + 30} textAnchor="middle"
              style={{ fontSize: 13, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', fill: '#ffffff' }}>
              User
            </text>
          </>
        )}
      </g>
      {!compact && (
        <text x={CON.x - 6} y={BASE + 22} textAnchor="end" style={labelStyle}>Collection</text>
      )}

      {/* The steps. */}
      {BUTTERFLY_NODES.filter(nd => !(compact && nd.wing === 'out')).map(nd => {
        const n = get(nd.id);
        const r = compact ? Math.max(nd.r * 1.4, 44) : nd.r;
        const base = NODE[nd.wing];
        const gap = nd.noSource || n === 0;
        const withIcon = r >= 28;
        const fs = compact ? Math.min(40, r * 0.7) : withIcon ? Math.min(20, r * 0.56) : 20;
        const lines = nd.label.split('\n');
        const dx = nd.side === 'right' ? r + 10 : nd.side === 'left' ? -(r + 10) : 0;
        const anchor = nd.side === 'right' ? 'start' : nd.side === 'left' ? 'end' : 'middle';
        const ly = nd.side === 'below' ? nd.y + r + 18
          : nd.side === 'above' ? nd.y - r - 10 - (lines.length - 1) * 15 - (nd.sub ? 15 : 0)
          : nd.y - (lines.length - 1) * 7.5 + 4 - (nd.sub ? 7 : 0);
        const tip = nd.wing === 'out' ? `${nd.name}: out of scope by design`
          : nd.noSource ? `${nd.name}: a gap — no law found` : `${nd.name}: ${fmt(n)} ${unit}`;
        const clickable = !!onStepClick && !nd.noSource && n > 0;
        return (
          <g key={nd.id} {...(clickable ? stepHandlers(nd.id) : {})}>
            <title>{tip}</title>
            {nd.wing === 'out' ? (
              <>
                <circle cx={nd.x} cy={nd.y} r={r} fill="var(--bg-primary)" stroke={NODE.out} strokeWidth={2.5} strokeDasharray="4 4" />
                <Icon name={nd.icon} cx={nd.x} cy={nd.y} size={r * 0.95} color={NODE.out} />
              </>
            ) : gap ? (
              <>
                <circle cx={nd.x} cy={nd.y} r={r} fill={`url(#${hatch})`} stroke={base} strokeWidth={2.5} />
                <Icon name={nd.icon} cx={nd.x} cy={nd.noSource ? nd.y : nd.y - r * 0.3} size={r * (nd.noSource ? 0.95 : 0.55)} color="var(--text-muted)" />
                {!nd.noSource && (
                  <text x={nd.x} y={nd.y + r * 0.55} textAnchor="middle"
                    style={{ fontFamily: serif, fontWeight: 700, fontSize: fs, fill: 'var(--text-muted)' }}>0</text>
                )}
              </>
            ) : (
              <>
                <circle cx={nd.x} cy={nd.y} r={r} fill={nodeFill(base, n, max)} stroke={base} strokeWidth={2.5} />
                {withIcon && (
                  <Icon name={nd.icon} cx={nd.x} cy={nd.y - r * (compact ? 0.36 : 0.34)} size={r * (compact ? 0.62 : 0.5)} color="#ffffff" />
                )}
                <text
                  x={nd.x}
                  y={withIcon ? nd.y + r * (compact ? 0.6 : 0.5) : nd.y + fs * 0.35}
                  textAnchor="middle"
                  style={{ fontFamily: serif, fontWeight: 700, fontSize: fs, fill: '#ffffff', fontVariantNumeric: 'tabular-nums' }}
                >
                  {fmt(n)}
                </text>
              </>
            )}
            {!compact && (
              <>
                {lines.map((ln, i) => (
                  <text key={ln} x={nd.x + dx} y={ly + i * 15} textAnchor={anchor} style={labelStyle}>{ln}</text>
                ))}
                {nd.sub && (
                  <text x={nd.x + dx} y={ly + lines.length * 15} textAnchor={anchor} style={subStyle}>{nd.sub}</text>
                )}
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/** The bills the diagram can't place, as an HTML strip (it wraps on a phone, unlike SVG text). */
export function ButterflyUnplaced({ counts }: { counts: ButterflyCounts | null }) {
  if (!counts) return null;
  const items: Array<[string, number]> = [
    ['Incentives', counts.unplaced.incentives ?? 0],
    ['Waste shipments', counts.unplaced.waste_shipment ?? 0],
    ['Other, budget and preemption', counts.unplaced.other ?? 0],
    ['On no step', counts.unplaced.no_step ?? 0],
  ];
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <span className="text-text-muted uppercase tracking-wide self-center mr-1">Not on a step</span>
      {items.map(([label, n]) => (
        <span key={label} className="rounded border border-dashed border-border-default px-2 py-1 text-text-secondary">
          {label} <span className="font-mono text-text-primary">{fmt(n)}</span>
        </span>
      ))}
    </div>
  );
}
