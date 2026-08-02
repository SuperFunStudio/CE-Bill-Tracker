'use client';
import { useState } from 'react';
import { requestAccess, type PlanInterest } from '@/lib/api';
import { track } from '@/lib/analytics';
import { getAttribution, attributionParams } from '@/lib/attribution';
import { CheckIcon } from '@/components/ui/icons';

/**
 * The willingness-to-pay capture. Every paid-tier CTA and the Company Impact gate opens this; the
 * click + org + tier is the field experiment that sets pricing before any Stripe plumbing exists.
 */
export function RequestAccessModal({
  plan,
  planLabel,
  source,
  heading,
  onClose,
}: {
  plan: PlanInterest;
  planLabel: string;
  source: string;
  /** Override the modal heading. Defaults to "Request {planLabel} access" — a walkthrough CTA passes
   *  "Book a walkthrough" so the form reads as a demo request, not a tier purchase. */
  heading?: string;
  onClose: () => void;
}) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [organization, setOrganization] = useState('');
  const [message, setMessage] = useState('');
  const [status, setStatus] = useState<'idle' | 'submitting' | 'done' | 'error'>('idle');
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus('submitting');
    setError('');
    try {
      // getAttribution() carries UTM + referrer; sent to our own backend so the lead-notification email
      // names the campaign that drove this request (e.g. "Campaign: linkedin / launch-post-3"). Empty
      // object when there's no marketing signal — the backend treats it as optional.
      const attribution = getAttribution();
      await requestAccess({
        email: email.trim(),
        name: name.trim() || undefined,
        organization: organization.trim() || undefined,
        plan_interest: plan,
        message: message.trim() || undefined,
        source,
        attribution: Object.keys(attribution).length ? attribution : undefined,
      });
      // Willingness-to-pay conversion. No PII — plan/source/utm enums only (see lib/analytics PII rule).
      // Mark as a Key Event in GA Admin to track it as a conversion.
      track('request_access', {
        plan,
        source,
        has_organization: organization.trim().length > 0,
        has_message: message.trim().length > 0,
        ...attributionParams(),
      });
      setStatus('done');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
      setStatus('error');
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl bg-bg-secondary border border-border-default shadow-2xl p-6"
        onClick={e => e.stopPropagation()}
      >
        {status === 'done' ? (
          <div className="text-center space-y-3 py-2">
            <CheckIcon className="text-3xl mx-auto text-green-accent" />
            <div className="text-text-primary font-semibold">Request received</div>
            <p className="text-text-muted text-sm">
              Thanks — we&apos;ll reach out at{' '}
              <span className="text-text-secondary">{email}</span> shortly.
            </p>
            <button onClick={onClose} className="text-text-muted text-xs underline hover:text-text-secondary">
              Close
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <h2 className="font-serif text-xl text-text-primary">{heading ?? `Request ${planLabel} access`}</h2>
              <p className="text-text-muted text-sm mt-1">
                Tell us where to reach you. We&apos;re onboarding early users and finalizing pricing —
                no charge today.
              </p>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-text-muted text-xs uppercase">Work email</label>
              <input
                type="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="bg-bg-primary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-text-muted text-xs uppercase">Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="Your name"
                  className="bg-bg-primary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-text-muted text-xs uppercase">Organization</label>
                <input
                  type="text"
                  value={organization}
                  onChange={e => setOrganization(e.target.value)}
                  placeholder="Company / firm"
                  className="bg-bg-primary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
                />
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-text-muted text-xs uppercase">
                Anything we should know? <span className="normal-case">(optional)</span>
              </label>
              <textarea
                value={message}
                onChange={e => setMessage(e.target.value)}
                rows={2}
                placeholder="Team size, use case, must-have features…"
                className="bg-bg-primary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent resize-none"
              />
            </div>
            {status === 'error' && <p className="text-urgency-high text-sm">{error}</p>}
            <div className="flex items-center justify-between gap-3">
              <button type="button" onClick={onClose} className="text-text-muted text-sm hover:text-text-secondary">
                Cancel
              </button>
              <button
                type="submit"
                disabled={status === 'submitting'}
                className="bg-green-accent text-bg-primary font-semibold px-5 py-2 rounded-lg text-sm hover:opacity-90 transition-opacity disabled:opacity-60"
              >
                {status === 'submitting' ? 'Sending…' : 'Request access'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
