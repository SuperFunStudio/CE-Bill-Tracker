'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { CheckIcon } from '@/components/ui/icons';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { useAuth } from '@/components/auth/AuthContext';
import { startCheckout } from '@/lib/billing';
import {
  PRO, RESEARCH, STUDENT, ENTERPRISE, PRICING_HEADER, LEDGER, SCALE, FOUNDING, FAIR_QUESTIONS,
  REGION_COUNT_FALLBACK, type BillingPeriod,
} from '@/lib/tiers';
import { useLawsInForce, useBillTimeline } from '@/hooks/useBills';
import { track } from '@/lib/analytics';
import type { PlanInterest } from '@/lib/api';

// Pricing, argued rather than listed. The order is deliberate: what's in the corpus (ledger) → what
// this category normally costs (reference scale) → the tiers → the objections (fair questions). A
// reader should be able to price the thing before a price is named, and every number they pass on the
// way is read from live corpus data rather than typed in here.
//
// Three self-serve tiers sit in the grid (Student, Researcher, Professional); Enterprise is a
// full-width band underneath, because it is an inquiry rather than a checkout and reads as the runt of
// the row when it sits in it. Feature lists mirror the capability matrix in app/api/auth.py PLAN_CAPS.
export default function PricingPage() {
  const { isPro, user, openAuth, getToken, entitlement } = useAuth();
  const plan = entitlement?.plan ?? 'free';
  const [period, setPeriod] = useState<BillingPeriod>('annual');
  const [modal, setModal] = useState<{ plan: PlanInterest; label: string; heading?: string; source?: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // which tier's CTA is mid-flight
  const [error, setError] = useState<string | null>(null);

  // How many regions we actually cover, from the same enacted-laws source the globe and the homepage
  // ticker shade from — so the headline claim can't drift from what the map shows.
  const { data: lawsInForce = [] } = useLawsInForce();
  const regionCount = useMemo(
    () => new Set(lawsInForce.map(r => r.region)).size || REGION_COUNT_FALLBACK,
    [lawsInForce],
  );

  // Coverage ledger. /bills/timeline is a grouped count (year × status × region) over every CE-relevant
  // measure carrying a status date, so summing it gives the corpus totals for the price of one cached
  // aggregate. The "latest year" comes out of the data rather than the clock: a client-side
  // new Date() would disagree with the prerendered HTML across a new year, and the newest year the
  // corpus actually contains is the more honest label anyway.
  const { data: timeline = [] } = useBillTimeline();
  const ledger = useMemo(() => {
    let measures = 0;
    let enacted = 0;
    let latestYear = 0;
    for (const p of timeline) {
      measures += p.count;
      if (p.status === 'enacted') enacted += p.count;
      if (p.year > latestYear) latestYear = p.year;
    }
    const movedLatest = timeline.reduce((n, p) => (p.year === latestYear ? n + p.count : n), 0);
    return { measures, enacted, latestYear, movedLatest };
  }, [timeline]);

  // Until the aggregate lands, an em dash — never a zero. A pricing page that flashes "0 measures
  // tracked" argues the opposite of what it is here to argue.
  const num = (n: number) => (n > 0 ? n.toLocaleString('en-US') : '—');

  const seatsRemaining = Math.max(FOUNDING.total - FOUNDING.claimed, 0);

  function openPlan(p: PlanInterest, label: string, heading?: string, source?: string) {
    track('pricing_cta', { plan: p, plan_label: label });
    setModal({ plan: p, label, heading, source });
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
  const chip = 'text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5';
  const eyebrow = 'block font-mono text-meta uppercase tracking-widest text-green-accent';
  const feat = (f: string) => (
    <li key={f} className="flex items-start gap-2 text-sm text-text-secondary">
      <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" /><span>{f}</span>
    </li>
  );

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* ── Masthead — the frame the rest of the page argues from: the price is small next to the thing
             it prevents. Left-aligned and editorial rather than centred marketing. ── */}
      <header className="pt-4 space-y-4">
        <span className={eyebrow}>{PRICING_HEADER.eyebrow}</span>
        <h1 className="font-serif text-3xl sm:text-4xl leading-tight text-text-primary max-w-[19ch]">
          {PRICING_HEADER.title}
        </h1>
        <p className="text-text-secondary leading-relaxed max-w-[58ch]">{PRICING_HEADER.lede(regionCount)}</p>
      </header>

      {/* ── Coverage ledger — what a seat buys, in numbers, before a price is named. Live counts. ── */}
      <section aria-label="Coverage" className="border-y border-border-default grid grid-cols-2 md:grid-cols-4">
        {[
          { n: num(ledger.measures), l: 'measures tracked, each linked to its source' },
          { n: num(ledger.enacted), l: `enacted laws, across ${regionCount} regions` },
          {
            n: num(ledger.movedLatest),
            l: ledger.latestYear ? `measures that moved in ${ledger.latestYear}` : 'measures that moved this year',
          },
          { n: String(regionCount), l: 'regions — national, supranational, and US state law' },
        ].map((cell, i) => (
          <div
            key={cell.l}
            className={[
              'py-5 pr-4',
              // Hairline rules between cells, and none on a row's first cell — which is a different
              // index at each breakpoint (2-up on mobile, 4-up above it).
              i % 2 === 1 ? 'border-l border-border-default pl-4' : 'md:border-l md:border-border-default md:pl-5',
              i === 0 ? 'md:border-l-0 md:pl-0' : '',
              i < 2 ? 'border-b border-border-default md:border-b-0' : '',
            ].join(' ')}
          >
            <span className="block font-mono text-2xl tracking-tight text-text-primary">{cell.n}</span>
            <span className="block text-meta text-text-muted mt-1.5 leading-snug">{cell.l}</span>
          </div>
        ))}
      </section>
      <p className="text-meta text-text-muted leading-relaxed">
        <span className="text-text-secondary">{LEDGER.noteLead}</span> {LEDGER.noteRest}
      </p>

      {/* ── Reference scale — the category anchor, drawn rather than asserted. The bracket is every
             Atlas tier; the tick near the right edge is where this category normally opens. ── */}
      <section aria-label="How Atlas is priced against comparable platforms" className="pt-8 space-y-3">
        <span className={eyebrow}>{SCALE.eyebrow}</span>
        <h2 className="font-serif text-xl text-text-primary">{SCALE.title}</h2>
        <p className="text-text-secondary text-sm leading-relaxed max-w-[62ch]">{SCALE.intro}</p>

        <div className="pt-7">
          <div className="relative h-px bg-border-default">
            <div className="absolute left-0 top-0 h-7 w-[40%] sm:w-[34%] border-l border-r border-b border-green-accent">
              <div className="absolute inset-x-0 top-0 h-[3px] bg-green-accent" />
            </div>
            <div className="absolute left-[92%] top-0 h-7 w-px bg-text-muted" />
          </div>
          <div className="mt-10 flex items-start justify-between gap-6">
            <div className="max-w-[30ch]">
              <span className="block font-mono text-text-primary">{SCALE.lowValue}</span>
              <span className="block text-sm text-text-secondary mt-1 leading-snug">{SCALE.lowLabel}</span>
            </div>
            <div className="max-w-[26ch] text-right">
              <span className="block font-mono text-text-secondary">{SCALE.highValue}</span>
              <span className="block text-sm text-text-muted mt-1 leading-snug">{SCALE.highLabel}</span>
            </div>
          </div>
          <p className="text-meta text-text-muted leading-relaxed border-t border-border-default mt-6 pt-3">
            {SCALE.foot}
          </p>
        </div>
      </section>

      {/* Billing-period toggle applies to Researchers + Pro (annual is the default, cheaper per month). */}
      <div className="flex items-center gap-3 pt-6">
        <div className="inline-flex rounded-lg border border-border-default bg-bg-secondary p-1">
          {(['annual', 'monthly'] as BillingPeriod[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              aria-pressed={period === p}
              className={`rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors ${
                period === p ? 'bg-green-accent text-bg-primary' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <span className="text-meta text-green-accent">
          {period === 'annual' ? PRO.annual.save : 'Switch to annual and save $600/yr'}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-stretch">
        {/* ── Students — verified-edu, free (value to us is distribution, not revenue) ── */}
        <div className={`${card} border-border-default bg-bg-secondary`}>
          <span className={`self-start mb-2 ${chip}`}>{STUDENT.label}</span>
          <div className="mt-1 mb-3">
            <span className="text-2xl font-bold text-text-primary">{STUDENT.headline}</span>
            <p className="text-text-muted text-meta mt-0.5">{STUDENT.sub}</p>
          </div>
          <p className="text-text-muted text-meta mb-4">{STUDENT.who}</p>
          <ul className="space-y-2 mb-5 flex-1">{STUDENT.features.map(feat)}</ul>
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

        {/* ── Researchers — approval-gated (see the note on the CTA below) ── */}
        <div className={`${card} border-border-default bg-bg-secondary`}>
          <span className={`self-start mb-2 ${chip}`}>{RESEARCH.label}</span>
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
          <ul className="space-y-2 mb-5 flex-1">{RESEARCH.features.map(feat)}</ul>
          {plan === 'research' ? (
            <Link href="/account" className={secondaryBtn}>Manage membership</Link>
          ) : (
            // Researcher access is approval-gated: capture a written request (email + org + message)
            // via the modal rather than self-serving Stripe checkout. The team reviews the request in
            // /admin and sends a Stripe invoice / payment link on approval. (The `research` checkout
            // path in billing.py still exists but is intentionally no longer reachable from the UI.)
            <div className="space-y-2">
              <button onClick={() => openPlan('research', 'Researcher')} className={primaryBtn}>
                Request access →
              </button>
              <p className="text-meta text-text-muted text-center">
                Verification is quick for .edu, .ac.uk, and registered non-profits.
              </p>
            </div>
          )}
        </div>

        {/* ── Professionals — self-serve, founding offer. The price shown is the founding rate and `was`
             is the post-window price struck through; the seat line says how much of the window is left
             as a number we can stand behind rather than a countdown clock (see FOUNDING). ── */}
        <div className={`${card} border-green-accent bg-green-dark/20`}>
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className={chip}>{PRO.label}</span>
            <span className="text-meta font-medium text-green-accent">{PRO.badge}</span>
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
          <div className="mb-3 rounded-lg border border-green-accent/40 bg-green-dark/30 px-3 py-2">
            <p className="text-meta leading-relaxed text-text-primary">{FOUNDING.headline}</p>
            <p className="font-mono text-meta text-green-accent mt-1.5">
              {FOUNDING.seatsLine(seatsRemaining, FOUNDING.total)}
            </p>
          </div>
          <p className="text-text-muted text-meta mb-4">{PRO.who}</p>
          <ul className="space-y-2 mb-5 flex-1">{PRO.features.map(feat)}</ul>
          {isPro ? (
            <Link href="/account" className="flex items-center justify-center gap-2 rounded-lg bg-green-accent text-bg-primary px-4 py-2 font-medium text-sm hover:opacity-90">
              <CheckIcon className="text-xs" /> Manage plan
            </Link>
          ) : (
            <div className="space-y-2">
              <button onClick={() => startPlan('pro', 'Professionals')} disabled={busy === 'pro'} className={primaryBtn}>
                {busy === 'pro' ? 'Starting…' : 'Start 90-day trial →'}
              </button>
              {/* The walkthrough sits here rather than in its own band: by this point the reader is
                  either buying or wants to talk to someone first. Enterprise gets its own CTA below. */}
              <p className="text-meta text-text-muted text-center leading-relaxed">
                No card required. Talk to us first?{' '}
                <button
                  onClick={() => openPlan('bespoke', 'a walkthrough', 'Book a walkthrough', 'pricing_walkthrough')}
                  className="text-green-accent hover:underline"
                >
                  Book a 20-minute walkthrough
                </button>
              </p>
            </div>
          )}
        </div>
      </div>

      {error && <p className="text-red-400 text-sm text-center">{error}</p>}

      {/* ── Enterprise — a conversation, not a checkout, so it gets a band rather than a fourth card ── */}
      <section
        aria-label="Enterprise"
        className="rounded-xl border border-green-accent/40 bg-green-hero px-6 py-7 grid grid-cols-1 lg:grid-cols-[1.15fr_1fr_auto] gap-8 items-center"
      >
        <div>
          <span className={`inline-block ${chip}`}>{ENTERPRISE.label}</span>
          <h2 className="font-serif text-2xl text-text-primary mt-3 mb-2">{ENTERPRISE.headline}</h2>
          <p className="text-text-secondary text-sm leading-relaxed max-w-[42ch]">{ENTERPRISE.who}</p>
        </div>
        <ul className="space-y-2">{ENTERPRISE.features.map(feat)}</ul>
        <div className="lg:min-w-[230px]">
          <button
            onClick={() => openPlan('enterprise', 'Enterprise')}
            className="w-full rounded-lg bg-green-accent text-bg-primary font-semibold px-6 py-3 hover:opacity-90 transition-opacity"
          >
            Start a conversation →
          </button>
          <p className="text-meta text-text-muted text-center mt-3 leading-relaxed">{ENTERPRISE.ctaNote}</p>
        </div>
      </section>

      {/* ── Fair questions — the four objections that actually stop a card going in, answered up front
             instead of buried in a FAQ page. ── */}
      <section className="pt-10">
        <span className={eyebrow}>{FAIR_QUESTIONS.eyebrow}</span>
        <h2 className="font-serif text-2xl text-text-primary mt-3 mb-2">{FAIR_QUESTIONS.title}</h2>
        <p className="text-text-secondary text-sm leading-relaxed max-w-[58ch] mb-6">{FAIR_QUESTIONS.lede}</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-px rounded-xl border border-border-default bg-border-default overflow-hidden">
          {FAIR_QUESTIONS.items({ measures: num(ledger.measures), regions: regionCount }).map(item => (
            <div key={item.q} className="bg-bg-primary p-6">
              <h3 className="font-serif text-base leading-snug text-text-primary mb-2">{item.q}</h3>
              <p className="text-text-secondary text-sm leading-relaxed">{item.a}</p>
            </div>
          ))}
        </div>
      </section>

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
          onClick={() => track('cta_click', { plan: 'api', entry_source: 'pricing_developers' })}
          className="shrink-0 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          View API docs →
        </Link>
      </section>

      <p className="border-t border-border-default pt-5 text-meta text-text-muted flex flex-wrap justify-between gap-3">
        <span>Prices in USD. Annual terms billed once; monthly cancels at the end of the month.</span>
        <span>Atlas Circular — a SUPERFUN project</span>
      </p>

      {modal && (
        <RequestAccessModal
          plan={modal.plan}
          planLabel={modal.label}
          heading={modal.heading}
          source={modal.source ?? 'pricing'}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
