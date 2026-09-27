'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/auth/AuthContext';
import { useLitigationCase } from '@/hooks/useFederal';
import { ReferralUnlock } from '@/components/ui/ReferralUnlock';
import { SkeletonList } from '@/components/ui/SkeletonList';
import { formatDate } from '@/lib/utils';
import { track, trackGateShown } from '@/lib/analytics';

const SITE_URL = 'https://www.atlascircular.com';

/** The canonical link to one case — the same URL litigation alert emails use, so a reader who
 *  forwards what they're looking at sends exactly what they saw. */
export function litigationCaseHref(id: number): string {
  return `${SITE_URL}/federal/?case=${id}`;
}

function titleCase(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function ShareCaseButton({ caseId, caseName }: { caseId: number; caseName: string }) {
  const [copied, setCopied] = useState(false);
  const url = litigationCaseHref(caseId);

  const onShare = useCallback(async () => {
    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({ title: caseName, url });
        track('litigation_case_share', { case_id: caseId, method: 'native' });
        return;
      } catch {
        /* sheet dismissed or unsupported — fall through to copy */
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      track('litigation_case_share', { case_id: caseId, method: 'copy' });
      setTimeout(() => setCopied(false), 1800);
    } catch {
      window.prompt('Copy this link to the case:', url);
    }
  }, [caseId, caseName, url]);

  return (
    <button
      type="button"
      onClick={onShare}
      aria-label="Copy a shareable link to this case"
      className={`text-sm transition-colors ${copied ? 'text-green-accent' : 'text-text-muted hover:text-text-primary'}`}
    >
      {copied ? 'Link copied' : 'Share this case'}
    </button>
  );
}

/**
 * One litigation case, standing on its own — what a reader sees when they arrive at
 * /federal/?case=<id> from a litigation alert without a Pro membership.
 *
 * The alert emails go to every active subscription regardless of tier, and they get forwarded. They
 * used to land on the bare Federal Actions lock card: no case, no clue they were even in the right
 * place. A single case is the unit people share, so it's free (see public_litigation_router) — the
 * corpus-wide tracker above it is what Pro buys. The page therefore ends where the email wants it
 * to: the docket the reader came for, then a way to keep it (share for a month, or sign in).
 */
export function LitigationCaseSpotlight({ caseId }: { caseId: number }) {
  const { user, openAuth } = useAuth();
  const { data: c, isLoading, isError } = useLitigationCase(caseId);

  useEffect(() => {
    // The spotlight IS the wall for this reader — record it like one so the litigation alert's
    // downstream conversion is comparable to every other gate.
    trackGateShown('pro', 'litigation_case');
    track('litigation_case_view', { case_id: caseId, entitled: false });
  }, [caseId]);

  if (isLoading) return <SkeletonList rows={3} height="h-20" />;
  if (isError || !c) {
    return (
      <div className="surface-card p-6 text-center space-y-3">
        <h2 className="font-serif text-xl text-text-primary">This case isn&rsquo;t available</h2>
        <p className="text-text-secondary text-sm">
          It may have been removed from the tracker since your alert was sent.
        </p>
        <Link href="/" className="text-green-accent text-sm hover:underline">
          ← Back to the Bill Explorer
        </Link>
      </div>
    );
  }

  const risk = c.preemption_risk;
  const riskColor =
    risk !== null && risk >= 70 ? 'text-urgency-high'
    : risk !== null && risk >= 40 ? 'text-urgency-medium'
    : 'text-green-accent';

  return (
    <div className="space-y-5">
      <div className="surface-card p-5 space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              {c.related_state && (
                <span className="text-green-accent font-mono text-xs">{c.related_state}</span>
              )}
              {c.challenge_type && (
                <span className="bg-bg-primary border border-border-default rounded px-2 py-0.5 text-xs text-text-secondary">
                  {titleCase(c.challenge_type)}
                </span>
              )}
              {c.case_status && <span className="text-text-muted text-xs">{titleCase(c.case_status)}</span>}
            </div>
            <h2 className="font-serif text-xl text-text-primary">{c.case_name}</h2>
            <div className="text-text-muted text-xs mt-1">
              {c.court_name || c.court_id?.toUpperCase()}
              {c.docket_number && ` · No. ${c.docket_number}`}
              {c.date_filed && ` · Filed ${formatDate(c.date_filed)}`}
            </div>
          </div>
          {risk !== null && (
            <div className="text-right shrink-0">
              <div className={`font-bold text-2xl ${riskColor}`}>{risk}</div>
              <div className="text-text-muted text-xs">Preemption risk</div>
            </div>
          )}
        </div>

        {c.key_plaintiffs && c.key_plaintiffs.length > 0 && (
          <div className="text-text-muted text-xs">Plaintiffs: {c.key_plaintiffs.join(', ')}</div>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 border-t border-border-default">
          <ShareCaseButton caseId={c.id} caseName={c.case_name} />
          {/* The law under challenge, when we've matched one — the reason a compliance reader cares. */}
          {c.related_law_id && (
            <Link href={`/?bill=${c.related_law_id}`} className="text-sm text-green-accent hover:underline">
              The law it challenges →
            </Link>
          )}
          {c.cl_url && (
            <a
              href={c.cl_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-green-accent hover:underline"
            >
              Docket on CourtListener ↗
            </a>
          )}
        </div>
      </div>

      {/* Timeline */}
      <div className="surface-card p-5">
        <div className="text-text-muted text-xs uppercase mb-3">Case Events</div>
        {c.events.length === 0 ? (
          <div className="text-text-secondary text-sm">No events recorded yet.</div>
        ) : (
          <div className="space-y-3">
            {c.events.map(ev => (
              <div key={ev.id} className="flex gap-3 text-sm">
                <div className="text-green-accent font-mono text-xs shrink-0 pt-0.5 w-20">
                  {formatDate(ev.date_filed)}
                </div>
                <div className="min-w-0">
                  <div className="text-text-secondary font-medium text-xs">{titleCase(ev.event_type)}</div>
                  {(ev.summary || ev.description) && (
                    <div className="text-text-muted text-xs mt-0.5">{ev.summary || ev.description}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Where the flow ends: keep the rest of the tracker, by sharing or by joining. */}
      <div className="mx-auto w-full max-w-md rounded-panel border border-green-accent bg-bg-secondary p-6 text-center space-y-5">
        <div>
          <h3 className="font-serif text-lg text-text-primary mb-1">Every EPR case, not just this one</h3>
          <p className="text-text-secondary text-sm leading-relaxed">
            The full litigation tracker — every challenge to a state EPR law, scored for preemption
            risk — plus federal agency actions, is included with a Pro membership.
          </p>
        </div>
        <ReferralUnlock
          source="litigation_case"
          gateFeature="litigation_referral_link"
          shareTitle="Atlas Circular — EPR litigation tracker"
          shareText={`Following ${c.case_name} and every other challenge to state EPR law:`}
        />
        <div className="flex items-center gap-3 text-meta uppercase tracking-wider text-text-muted">
          <span className="h-px flex-1 bg-border-default" /> or <span className="h-px flex-1 bg-border-default" />
        </div>
        <div className="flex justify-center gap-2">
          {!user && (
            <button
              type="button"
              onClick={openAuth}
              className="rounded-full border border-border-default px-5 py-2 text-sm text-text-secondary hover:text-text-primary"
            >
              Sign in
            </button>
          )}
          <Link
            href="/pricing"
            className="rounded-full bg-green-accent px-5 py-2 text-sm font-medium text-bg-primary hover:opacity-90"
          >
            See memberships
          </Link>
        </div>
      </div>
    </div>
  );
}
