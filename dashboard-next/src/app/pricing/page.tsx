'use client';
import { useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { CheckIcon } from '@/components/ui/icons';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { useAuth } from '@/components/auth/AuthContext';
import { startCheckout } from '@/lib/billing';
import { PRO, RESEARCH, STUDENT, type BillingPeriod } from '@/lib/tiers';
import { track } from '@/lib/analytics';
import type { PlanInterest } from '@/lib/api';

// Four membership tiers, framed as access to the Atlas research tools. Student (verified-edu,
// pay-what-you-wish) and Research (annual) are new below Pro; Enterprise is the invoiced inquiry.
// Feature lists mirror the capability matrix in app/api/auth.py PLAN_CAPS.
export default function PricingPage() {
  const { isPro, user, openAuth, getToken, entitlement } = useAuth();
  const plan = entitlement?.plan ?? 'free';
  const [period, setPeriod] = useState<BillingPeriod>('annual');
  const [modal, setModal] = useState<{ plan: PlanInterest; label: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // which tier's CTA is mid-flight
  const [error, setError] = useState<string | null>(null);
  // Student pay-what-you-wish amount (cents), collected here because Stripe can't take a customer-chosen
  // amount for a subscription. Suggested $15/mo; presets + a custom field. 0 => free comp membership.
  const [studentAmount, setStudentAmount] = useState(1500);

  function openPlan(p: PlanInterest, label: string) {
    track('pricing_cta', { plan: p, plan_label: label });
    setModal({ plan: p, label });
  }

  // Self-serve checkout for pro/research — both bill monthly or annual, so the period toggle applies
  // to each. Needs a signed-in user (Stripe customer keys off the verified email), so prompt sign-in
  // first if needed.
  async function startPlan(p: 'pro' | 'research', label: string) {
    track('pricing_cta', { plan: p, plan_label: label, period });
    setError(null);
    if (!user) { openAuth(); return; }
    setBusy(p);
    try {
      await startCheckout(getToken, { plan: p, period });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start checkout.');
      setBusy(null);
    }
  }

  // Student — pay-what-you-wish. amountCents 0 grants a free comp membership; any value hands off to
  // Stripe's custom-amount screen. A 403 here means the account isn't a verified educational email.
  async function startStudent(amountCents: number | null, label: string) {
    track('pricing_cta', { plan: 'student', plan_label: label });
    setError(null);
    if (!user) { openAuth(); return; }
    setBusy('student');
    try {
      await startCheckout(getToken, { plan: 'student', amountCents });
    } catch (e) {
      const msg = e instanceof Error ? e.message : '';
      setError(
        /educational|edu/i.test(msg)
          ? 'The Student membership needs a verified educational email (.edu, .ac.uk, …). Sign in with your school address and verify it, then try again.'
          : msg || 'Could not start checkout.',
      );
      setBusy(null);
    }
  }

  const card = 'flex flex-col rounded-xl border p-5';
  const primaryBtn = 'w-full rounded-lg bg-green-accent text-bg-primary px-4 py-2 font-medium text-sm transition-opacity hover:opacity-90 disabled:opacity-50';
  const secondaryBtn = 'block w-full text-center rounded-lg border border-green-accent bg-green-dark px-4 py-2 font-serif font-medium text-green-accent transition-opacity hover:opacity-90';

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <GazetteHeader
        title="Membership"
        subtitle="Join the atlas. Every membership includes the Bill Explorer and jurisdiction data; higher tiers unlock Ask the Atlas, deadlines, alerts, and the Packaging Studio."
      />

      {/* Billing-period toggle applies to Pro (annual is the default, cheaper per month). */}
      <div className="flex items-center justify-center gap-3">
        <div className="inline-flex rounded-lg border border-border-default bg-bg-secondary p-1">
          {(['annual', 'monthly'] as BillingPeriod[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors ${
                period === p ? 'bg-green-accent text-bg-primary' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <span className="text-meta text-green-accent">Pro · {PRO.annual.save}</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-stretch">
        {/* ── Student — verified-edu, pay-what-you-wish ── */}
        <div className={`${card} border-border-default bg-bg-secondary`}>
          <span className="self-start mb-2 text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
            Students
          </span>
          <h2 className="font-serif text-xl text-text-primary">{STUDENT.name}</h2>
          <div className="mt-1 mb-3">
            <span className="text-2xl font-bold text-text-primary">{STUDENT.price}</span>
            <p className="text-text-muted text-meta mt-0.5">{STUDENT.suggested}</p>
          </div>
          <p className="text-text-muted text-meta mb-4">{STUDENT.who} {STUDENT.eduNote}.</p>
          <ul className="space-y-2 mb-5 flex-1">
            {['Ask the Atlas', 'Bill Explorer & jurisdiction data', 'Design Guide'].map(f => (
              <li key={f} className="flex items-start gap-2 text-sm text-text-secondary">
                <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" /><span>{f}</span>
              </li>
            ))}
          </ul>
          {plan === 'student' ? (
            <Link href="/account" className={secondaryBtn}>Manage membership</Link>
          ) : (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-1.5">
                {[500, 1500, 3000].map(a => (
                  <button
                    key={a}
                    type="button"
                    onClick={() => setStudentAmount(a)}
                    className={`rounded-full px-3 py-1 text-xs border transition-colors ${
                      studentAmount === a
                        ? 'border-green-accent bg-green-dark text-green-accent'
                        : 'border-border-default text-text-secondary hover:text-text-primary'
                    }`}
                  >
                    ${a / 100}/mo
                  </button>
                ))}
                <input
                  type="number"
                  min={1}
                  aria-label="Custom monthly amount (USD)"
                  placeholder="Custom $"
                  onChange={e => {
                    const v = Math.round(parseFloat(e.target.value || '0') * 100);
                    if (v > 0) setStudentAmount(v);
                  }}
                  className="w-20 rounded-md border border-border-default bg-bg-primary px-2 py-1 text-xs text-text-primary"
                />
              </div>
              <button onClick={() => startStudent(studentAmount, 'Student — pay what you wish')} disabled={busy === 'student'} className={primaryBtn}>
                {busy === 'student' ? 'Starting…' : `Join for $${(studentAmount / 100).toFixed(0)}/mo →`}
              </button>
              <button
                onClick={() => startStudent(0, 'Student — free')}
                disabled={busy === 'student'}
                className="w-full text-center text-meta text-text-muted hover:text-text-primary"
              >
                or join free ($0)
              </button>
            </div>
          )}
        </div>

        {/* ── Founding Supporter / Research — annual ── */}
        <div className={`${card} border-border-default bg-bg-secondary`}>
          <span className="self-start mb-2 text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
            Research
          </span>
          <h2 className="font-serif text-xl text-text-primary">{RESEARCH.name}</h2>
          <div className="mt-1 mb-3">
            {period === 'annual' ? (
              <>
                <span className="text-2xl font-bold text-text-primary">{RESEARCH.annual.price}</span>
                <span className="text-text-muted text-sm"> {RESEARCH.annual.cadence}</span>
                <p className="text-text-muted text-meta mt-0.5">{RESEARCH.annual.perMonth}</p>
              </>
            ) : (
              <>
                <span className="text-2xl font-bold text-text-primary">{RESEARCH.monthly.price}</span>
                <span className="text-text-muted text-sm"> {RESEARCH.monthly.cadence}</span>
                <p className="text-text-muted text-meta mt-0.5">{RESEARCH.annual.save}</p>
              </>
            )}
          </div>
          <p className="text-text-muted text-meta mb-4">{RESEARCH.who}</p>
          <ul className="space-y-2 mb-5 flex-1">
            {['Ask the Atlas', 'Bill Explorer & jurisdiction data', 'Design Guide', 'Insights: impact + bills over time'].map(f => (
              <li key={f} className="flex items-start gap-2 text-sm text-text-secondary">
                <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" /><span>{f}</span>
              </li>
            ))}
          </ul>
          {plan === 'research' ? (
            <Link href="/account" className={secondaryBtn}>Manage membership</Link>
          ) : (
            <button onClick={() => startPlan('research', 'Founding Supporter')} disabled={busy === 'research'} className={primaryBtn}>
              {busy === 'research' ? 'Starting…' : 'Become a supporter →'}
            </button>
          )}
        </div>

        {/* ── Pro — self-serve, founding offer ── */}
        <div className={`${card} border-green-accent bg-green-dark/20`}>
          <span className="self-start mb-2 text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
            Recommended
          </span>
          <h2 className="font-serif text-xl text-text-primary">{PRO.name}</h2>
          <div className="mt-1 mb-3">
            {period === 'annual' ? (
              <>
                <span className="text-2xl font-bold text-text-primary">{PRO.annual.price}</span>
                <span className="text-text-muted text-sm"> {PRO.annual.cadence}</span>
                <p className="text-text-muted text-meta mt-0.5">{PRO.annual.perMonth}</p>
              </>
            ) : (
              <>
                <span className="text-2xl font-bold text-text-primary">{PRO.monthly.price}</span>
                <span className="text-text-muted text-sm"> {PRO.monthly.cadence}</span>
                <p className="text-text-muted text-meta mt-0.5">{PRO.seatsNote}</p>
              </>
            )}
          </div>
          <p className="mb-3 rounded-lg border border-green-accent/40 bg-green-dark/30 px-3 py-2 text-meta leading-relaxed text-green-accent">
            {PRO.foundingNote}
          </p>
          <ul className="space-y-2 mb-5 flex-1">
            {['Everything in Research', 'Upcoming Deadlines — all jurisdictions', 'Alerts & watch lists', 'Packaging Studio', 'Federal Actions (US)', 'CSV export'].map(f => (
              <li key={f} className="flex items-start gap-2 text-sm text-text-secondary">
                <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" /><span>{f}</span>
              </li>
            ))}
          </ul>
          {isPro ? (
            <Link href="/account" className="flex items-center justify-center gap-2 rounded-lg bg-green-accent text-bg-primary px-4 py-2 font-medium text-sm hover:opacity-90">
              <CheckIcon className="text-xs" /> Manage plan
            </Link>
          ) : (
            <div className="space-y-2">
              <button onClick={() => startPlan('pro', 'Pro')} disabled={busy === 'pro'} className={primaryBtn}>
                {busy === 'pro' ? 'Starting…' : 'Claim founding access →'}
              </button>
              <p className="text-meta text-text-muted text-center">90-day free trial · cancel anytime</p>
              <p className="text-meta text-text-muted text-center">
                Prefer a guided setup?{' '}
                <button onClick={() => openPlan('pro', 'Pro — walkthrough')} className="text-green-accent hover:underline">
                  Book a walkthrough →
                </button>
              </p>
            </div>
          )}
        </div>

        {/* ── Enterprise — invoiced inquiry ── */}
        <div className={`${card} border-border-default bg-bg-secondary`}>
          <span className="self-start mb-2 text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
            Teams
          </span>
          <h2 className="font-serif text-xl text-text-primary">Enterprise</h2>
          <div className="mt-1 mb-3">
            <span className="text-2xl font-bold text-text-primary">Custom</span>
            <p className="text-text-muted text-meta mt-0.5">Invoiced · seats + support</p>
          </div>
          <p className="text-text-muted text-meta mb-4">Firms, ESG &amp; legal services teams.</p>
          <ul className="space-y-2 mb-5 flex-1">
            {['Everything in Pro', 'Seats for your whole team', 'Priority support', 'Onboarding & bespoke exposure mapping'].map(f => (
              <li key={f} className="flex items-start gap-2 text-sm text-text-secondary">
                <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" /><span>{f}</span>
              </li>
            ))}
          </ul>
          <button onClick={() => openPlan('enterprise', 'Enterprise')} className={secondaryBtn}>Start a conversation →</button>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm text-center">{error}</p>}

      {/* Developers strip — its own section below the grid (different buyer, usage-based metric) */}
      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="max-w-2xl">
          <h3 className="font-serif text-lg text-text-primary mb-1">Developers — build on the data.</h3>
          <p className="text-text-secondary text-sm leading-relaxed">
            Tap the circular-economy legislation dataset directly: bills, statuses, deadlines, and
            classifications across every tracked jurisdiction, kept current. Free developer tier
            (rate-limited) · paid plans by usage.
          </p>
        </div>
        <Link
          href="/developers"
          onClick={() => track('cta_click', { plan: 'api', source: 'pricing_developers' })}
          className="shrink-0 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          View API docs →
        </Link>
      </section>

      {modal && (
        <RequestAccessModal
          plan={modal.plan}
          planLabel={modal.label}
          source="pricing"
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
