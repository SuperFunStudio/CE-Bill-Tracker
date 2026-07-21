'use client';
import { useState } from 'react';
import Link from 'next/link';
import { CheckIcon } from '@/components/ui/icons';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { useAuth } from '@/components/auth/AuthContext';
import { startCheckout } from '@/lib/billing';
import { PRO, RESEARCH, STUDENT, ENTERPRISE, PRICING_HEADER, type BillingPeriod } from '@/lib/tiers';
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

  // Student — verified-edu, free. amountCents 0 grants a free comp membership on the spot (no Stripe).
  // A 403 here means the account isn't a verified educational email.
  async function startStudent(label: string) {
    track('pricing_cta', { plan: 'student', plan_label: label });
    setError(null);
    if (!user) { openAuth(); return; }
    setBusy('student');
    try {
      await startCheckout(getToken, { plan: 'student', amountCents: 0 });
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
      {/* Value-anchoring header — Atlas vs $50k+ legislative-intelligence platforms + cost of a
          missed EPR registration. Replaces the generic "Membership" masthead. */}
      <header className="text-center max-w-3xl mx-auto space-y-3">
        <h1 className="font-serif text-2xl sm:text-3xl text-text-primary">{PRICING_HEADER.title}</h1>
        <p className="text-text-secondary leading-relaxed">{PRICING_HEADER.subtitle}</p>
        <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
          {PRICING_HEADER.chips.map(c => (
            <span key={c} className="rounded-full border border-border-default bg-bg-secondary px-3 py-1 text-meta text-text-muted">
              {c}
            </span>
          ))}
        </div>
      </header>

      {/* Billing-period toggle applies to Researchers + Pro (annual is the default, cheaper per month). */}
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
        <span className="text-meta text-green-accent">{PRO.annual.save}</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-stretch">
        {/* ── Students — verified-edu, free (value to us is distribution, not revenue) ── */}
        <div className={`${card} border-border-default bg-bg-secondary`}>
          <span className="self-start mb-2 text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
            {STUDENT.label}
          </span>
          <div className="mt-1 mb-3">
            <span className="text-2xl font-bold text-text-primary">{STUDENT.headline}</span>
            <p className="text-text-muted text-meta mt-0.5">{STUDENT.sub}</p>
          </div>
          <p className="text-text-muted text-meta mb-4">{STUDENT.who}</p>
          <ul className="space-y-2 mb-5 flex-1">
            {STUDENT.features.map(f => (
              <li key={f} className="flex items-start gap-2 text-sm text-text-secondary">
                <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" /><span>{f}</span>
              </li>
            ))}
          </ul>
          {plan === 'student' ? (
            <Link href="/account" className={secondaryBtn}>Manage membership</Link>
          ) : (
            <div className="space-y-2">
              <button onClick={() => startStudent('Students — free')} disabled={busy === 'student'} className={primaryBtn}>
                {busy === 'student' ? 'Starting…' : 'Verify and start →'}
              </button>
              <p className="text-meta text-text-muted text-center">
                Teaching a course?{' '}
                <button onClick={() => openPlan('enterprise', 'Students — class seats')} className="text-green-accent hover:underline">
                  Get seats for your class
                </button>
              </p>
            </div>
          )}
        </div>

        {/* ── Researchers — monthly / annual ── */}
        <div className={`${card} border-border-default bg-bg-secondary`}>
          <span className="self-start mb-2 text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
            {RESEARCH.label}
          </span>
          <div className="mt-1 mb-3">
            {(() => {
              const r = period === 'annual' ? RESEARCH.annual : RESEARCH.monthly;
              return (
                <>
                  <span className="text-2xl font-bold text-text-primary">{r.price}</span>
                  <span className="text-text-muted text-sm">{r.cadence}</span>
                  <p className="text-text-muted text-meta mt-0.5">{r.sub}</p>
                </>
              );
            })()}
          </div>
          <p className="text-text-muted text-meta mb-4">{RESEARCH.who}</p>
          <ul className="space-y-2 mb-5 flex-1">
            {RESEARCH.features.map(f => (
              <li key={f} className="flex items-start gap-2 text-sm text-text-secondary">
                <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" /><span>{f}</span>
              </li>
            ))}
          </ul>
          {plan === 'research' ? (
            <Link href="/account" className={secondaryBtn}>Manage membership</Link>
          ) : (
            <button onClick={() => startPlan('research', 'Researchers')} disabled={busy === 'research'} className={primaryBtn}>
              {busy === 'research' ? 'Starting…' : 'Get access →'}
            </button>
          )}
        </div>

        {/* ── Professionals — self-serve, founding offer (price shown is the founding rate; `was` is
             the post-window price struck through) ── */}
        <div className={`${card} border-green-accent bg-green-dark/20`}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
              {PRO.label}
            </span>
            <span className="text-meta font-medium text-green-accent bg-green-dark/40 rounded-full px-2 py-0.5">{PRO.badge}</span>
          </div>
          <div className="mt-1 mb-3">
            {(() => {
              const pr = period === 'annual' ? PRO.annual : PRO.monthly;
              return (
                <>
                  <span className="text-2xl font-bold text-text-primary">{pr.price}</span>
                  <span className="text-text-muted text-sm">{pr.cadence}</span>
                  <span className="text-text-muted text-sm line-through ml-2">{pr.was}</span>
                  <p className="text-text-muted text-meta mt-0.5">{pr.sub}</p>
                </>
              );
            })()}
          </div>
          <p className="mb-3 rounded-lg border border-green-accent/40 bg-green-dark/30 px-3 py-2 text-meta leading-relaxed text-green-accent">
            {PRO.foundingNote}
          </p>
          <p className="text-text-muted text-meta mb-4">{PRO.who}</p>
          <ul className="space-y-2 mb-5 flex-1">
            {PRO.features.map(f => (
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
              <button onClick={() => startPlan('pro', 'Professionals')} disabled={busy === 'pro'} className={primaryBtn}>
                {busy === 'pro' ? 'Starting…' : 'Start 90-day trial →'}
              </button>
              <p className="text-meta text-text-muted text-center">
                No card required ·{' '}
                <button onClick={() => openPlan('pro', 'Pro — walkthrough')} className="text-green-accent hover:underline">
                  book a walkthrough
                </button>
              </p>
            </div>
          )}
        </div>

        {/* ── Enterprise — invoiced inquiry (Bespoke) ── */}
        <div className={`${card} border-border-default bg-bg-secondary`}>
          <span className="self-start mb-2 text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
            {ENTERPRISE.label}
          </span>
          <div className="mt-1 mb-3">
            <span className="text-2xl font-bold text-text-primary">{ENTERPRISE.headline}</span>
            <p className="text-text-muted text-meta mt-0.5">{ENTERPRISE.sub}</p>
          </div>
          <p className="text-text-muted text-meta mb-4">{ENTERPRISE.who}</p>
          <ul className="space-y-2 mb-5 flex-1">
            {ENTERPRISE.features.map(f => (
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
