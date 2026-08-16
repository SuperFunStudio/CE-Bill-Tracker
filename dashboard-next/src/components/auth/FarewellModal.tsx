'use client';
import { useEffect, useState } from 'react';
import { useAuth } from './AuthContext';
import { fetchBillOutcomes } from '@/lib/api';
import { track } from '@/lib/analytics';
import { outcomeMetricText } from '@/lib/outcomeMetric';
import type { BillOutcome } from '@/lib/types';

/**
 * Parting screen shown after sign-out / account deletion. Offboarding shouldn't dead-end on a blank
 * page — this leaves a positive, shareable association by surfacing one documented real-world win
 * from the Insights "Impact" table (a law that actually did something measurable). Best-effort: if
 * outcomes can't load, it degrades to a plain thank-you.
 */

// Outcome copy is written for the Insights table, where there's room to be thorough. A farewell card
// has none — clip to whole sentences up to a budget so the fact stays scannable on the way out.
function clip(text: string | null | undefined, maxChars: number): string {
  const t = (text || '').trim();
  if (t.length <= maxChars) return t;
  const sentences = t.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [t];
  let out = '';
  for (const s of sentences) {
    if (out && (out + s).trim().length > maxChars) break;
    out += s;
    if (out.trim().length >= maxChars) break;
  }
  out = out.trim();
  if (!out) out = t.slice(0, maxChars).replace(/\s+\S*$/, '');
  return out.length < t.length && !/[.!?]$/.test(out) ? `${out}…` : out;
}

// Prefer a positive, human-reviewed outcome that carries a headline metric — the most shareable kind.
function pickShareable(outcomes: BillOutcome[]): BillOutcome | null {
  if (!outcomes.length) return null;
  const positive = outcomes.filter(o => o.direction === 'positive');
  const withMetric = positive.filter(o => outcomeMetricText(o));
  const pool = withMetric.length ? withMetric : positive.length ? positive : outcomes;
  return pool[Math.floor(Math.random() * pool.length)];
}

export function FarewellModal() {
  const { farewellOpen, closeFarewell } = useAuth();
  const [outcome, setOutcome] = useState<BillOutcome | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!farewellOpen || loaded) return;
    let cancelled = false;
    fetchBillOutcomes({ reviewed_only: true })
      .then(d => { if (!cancelled) setOutcome(pickShareable(d)); })
      .catch(() => { /* degrade to plain thank-you */ })
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, [farewellOpen, loaded]);

  if (!farewellOpen) return null;

  const metric = outcome ? outcomeMetricText(outcome) : null;
  const lawLabel = outcome ? [outcome.state, outcome.bill_number].filter(Boolean).join(' ') : '';
  const shareText = outcome
    ? `${metric ? metric + (outcome.metric_label ? ` ${clip(outcome.metric_label, 70)}` : '') + ' — ' : ''}${clip(outcome.summary, 180)}${lawLabel ? ` (${lawLabel})` : ''} · via Atlas Circular`
    : '';

  async function copyShare() {
    try {
      await navigator.clipboard.writeText(shareText);
      setCopied(true);
      track('farewell_fact_share', { slug: outcome?.slug });
      setTimeout(() => setCopied(false), 2500);
    } catch { /* clipboard blocked — the source link is still there */ }
  }

  function dismiss() {
    setCopied(false);
    closeFarewell();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      onClick={dismiss}
    >
      <div
        className="w-full max-w-md rounded-xl bg-bg-secondary border border-border-default shadow-2xl p-6 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <div>
          <h2 className="font-serif text-xl text-text-primary">You&apos;re signed out 👋</h2>
          <p className="text-text-muted text-sm mt-1">Good to have you here. Come back when the laws move.</p>
        </div>

        {outcome ? (
          <div className="rounded-lg border border-green-accent/40 bg-green-dark/20 p-4 space-y-2">
            <p className="text-meta uppercase tracking-wider text-green-accent">
              Before you go — a win worth sharing
            </p>
            {metric && (
              <p className="font-serif text-2xl font-bold text-text-primary leading-tight">
                {metric}
              </p>
            )}
            {outcome.metric_label && (
              <p className="text-text-secondary text-sm leading-snug">
                {clip(outcome.metric_label, 70)}
              </p>
            )}
            <p className="text-text-secondary text-body leading-relaxed">
              {clip(outcome.summary, 180)}
            </p>
            <p className="text-text-muted text-xs">
              {lawLabel && <span className="font-medium text-text-secondary">{lawLabel}</span>}
              {outcome.source_url && (
                <>
                  {lawLabel ? ' · ' : ''}
                  <a
                    href={outcome.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-green-accent hover:underline"
                  >
                    Source{outcome.source_name ? `: ${outcome.source_name}` : ''} ↗
                  </a>
                </>
              )}
            </p>
          </div>
        ) : loaded ? (
          <p className="text-text-secondary text-body">
            Real laws are changing what gets made and what gets thrown away every month — come back
            any time to see what&apos;s next.
          </p>
        ) : (
          <div className="h-24 animate-pulse rounded-lg bg-bg-tertiary" />
        )}

        <div className="flex items-center gap-2">
          {outcome && (
            <button
              onClick={copyShare}
              className="flex-1 rounded-lg border border-green-accent bg-green-dark px-4 py-2 text-sm font-medium text-green-accent hover:opacity-90 transition-opacity"
            >
              {copied ? 'Copied to share ✓' : 'Copy to share'}
            </button>
          )}
          <button
            onClick={dismiss}
            className="flex-1 rounded-lg bg-green-accent text-bg-primary font-semibold px-4 py-2 text-sm hover:opacity-90 transition-opacity"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
