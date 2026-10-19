import type { ReactNode } from 'react';

/**
 * The "Headlines & Deadlines" card language: a letter-spaced kicker, one oversized serif figure with
 * its unit stacked beside it, a sentence, a hairline, and a footer row. Shared by the outcome card and
 * the deadlines card so the two read as one front-page spread.
 *
 * `tone` colours the kicker and the figure — the brand accent for documented outcomes (data), amber
 * for deadlines (the status palette's "pending" hue) — so the two cards are told apart at a glance.
 */
export function FeatureCard({ children, className = '', ...rest }: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`flex h-full flex-col rounded-2xl border border-border-default bg-bg-secondary p-6 sm:p-7 ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function Kicker({ tone, children }: { tone: string; children: ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-[0.2em] sm:text-[0.8125rem]" style={{ color: tone }}>
      {children}
    </p>
  );
}

/**
 * Split "2.44 million pounds" into the number and the words after it, so the number can be set huge
 * with the unit stacked beside it. Returns null when the figure doesn't split cleanly — a curated
 * display like "157k → 231k tons (+47%)" or "55.3% collected (2023) vs 77% target", where the "unit"
 * carries numbers of its own or runs long — and the caller sets the whole string at one size instead.
 */
export function splitFigure(text: string): { value: string; unit: string } | null {
  // A shorthand suffix (16k, 2.4m, 76%) only counts when it ends the token — otherwise "$16 million"
  // would split as "$16m" + "illion".
  const m = text.trim().match(/^([~≈$€£¥]?\s?\d[\d.,]*(?:[%kKmMbB](?=\s|$))?\+?)\s*(.*)$/);
  if (!m) return null;
  const unit = m[2].trim();
  if (/\d/.test(unit) || unit.length > 24) return null;
  return { value: m[1].replace(/\s+/g, ''), unit };
}

export function BigFigure({ text, tone }: { text: string; tone: string }) {
  const split = splitFigure(text);
  if (!split) {
    return (
      <p className="font-serif text-4xl leading-tight tabular-nums sm:text-5xl" style={{ color: tone }}>
        {text}
      </p>
    );
  }
  return (
    <div className="flex items-center gap-x-4">
      <span className="font-serif text-7xl leading-[0.9] tabular-nums sm:text-8xl" style={{ color: tone }}>
        {split.value}
      </span>
      {split.unit && (
        <span className="max-w-[10ch] font-serif text-2xl leading-[1.05] text-text-primary sm:text-3xl">
          {split.unit}
        </span>
      )}
    </div>
  );
}
