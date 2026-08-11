'use client';
import { useEffect } from 'react';
import { trackGateShown, trackGateHit, type GateOutcome } from '@/lib/analytics';

/**
 * The shared paywall / sign-in wall card.
 *
 * Every wall renders through this so instrumentation follows the UI instead of depending on each
 * caller remembering to fire the right events. That failure mode isn't hypothetical: the Upcoming
 * Deadlines lock hand-rolled its own card and went untracked while being the highest-volume paywall on
 * the site — 61 users saw it in a 28-day window and the conversion funnel showed a single gate_hit.
 * A wall that isn't instrumented reads as a wall nobody reaches, which is the most expensive possible
 * way to be wrong about a paywall.
 *
 * Emits gate_shown on mount (impression) and gate_hit on the CTA (intent), then runs onClick. Callers
 * that need bespoke layout should still call trackGateShown/trackGateHit directly rather than
 * re-deriving the param shape — see UpcomingDeadlinesLock.
 */
export function GateCard({
  gate,
  feature,
  outcome,
  icon,
  title,
  body,
  cta,
  onClick,
}: {
  /** The capability being protected — 'pro', or a capability key for useCapabilityGate-style gates. */
  gate: string;
  /** Names this specific CTA, so two walls guarding the same capability stay distinguishable. */
  feature: string;
  /** What clicking through will do: sign_in for anonymous visitors, checkout/pricing for upgrades. */
  outcome: GateOutcome;
  icon: React.ReactNode;
  title: string;
  body: string;
  cta: string;
  onClick: () => void;
}) {
  // Impression fires once per mount. gate/feature are literal props at every call site, so this does
  // not re-fire on re-render.
  useEffect(() => {
    trackGateShown(gate, feature);
  }, [gate, feature]);

  return (
    <div className="rounded-xl border border-green-accent bg-green-dark/20 p-8 text-center space-y-3 max-w-xl mx-auto">
      <div>{icon}</div>
      <h2 className="font-serif text-xl text-text-primary">{title}</h2>
      <p className="text-text-secondary text-sm leading-relaxed">{body}</p>
      <button
        onClick={() => {
          trackGateHit(gate, outcome, feature);
          onClick();
        }}
        className="inline-flex items-center gap-2 rounded-lg bg-green-accent text-bg-primary px-5 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity"
      >
        {cta}
      </button>
    </div>
  );
}
