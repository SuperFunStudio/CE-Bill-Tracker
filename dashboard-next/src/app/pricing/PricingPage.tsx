'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { CheckIcon } from '@/components/ui/icons';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { useAuth } from '@/components/auth/AuthContext';
import { startCheckout } from '@/lib/billing';
import {
  PRO, RESEARCH, STUDENT, ENTERPRISE, DATA, PRICING_HEADER, LEDGER, SCALE, FOUNDING,
  REGION_COUNT_FALLBACK, featureText, featureEmphasis, type BillingPeriod, type Feature,
} from '@/lib/tiers';
import { useLawsInForce, useBillTimeline } from '@/hooks/useBills';
import { useFoundingSeats } from '@/hooks/useFoundingSeats';
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

  // Live from /billing/founding-seats, so the counter moves as seats sell rather than when someone
  // remembers to edit a constant.
  const { total: seatsTotal, remaining: seatsRemaining } = useFoundingSeats();

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
  // One bullet per list may be marked emphasis (see Feature in lib/tiers): it drops the muted secondary
  // colour and takes medium weight, so the reason-to-buy is the line the eye lands on first.
  const feat = (f: Feature) => {
    const text = featureText(f);
    return (
      <li
        key={text}
        className={`flex items-start gap-2 text-sm ${
          featureEmphasis(f) ? 'text-text-primary font-medium' : 'text-text-secondary'
        }`}
      >
        <CheckIcon className="text-green-accent text-xs mt-1 shrink-0" /><span>{text}</span>
      </li>
    );
  };

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* ── Masthead — the shared GazetteHeader, same as every other page: the pitch rides as the
             italic tagline rather than getting a pricing-only headline treatment. ── */}
      <GazetteHeader title={PRICING_HEADER.title} subtitle={PRICING_HEADER.tagline} />
      <p className="text-text-secondary leading-relaxed max-w-[62ch] mx-auto text-center">
        {PRICING_HEADER.lede(regionCount)}
      </p>

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

      {/* ── Category anchor — stated in prose. An earlier version drew this as a scale bar (Atlas's
             range bracketed against a tick at the category's entry price); it didn't read at a glance,
             so the comparison is a sentence now. ── */}
      <section aria-label="How Atlas is priced against comparable platforms" className="pt-6 space-y-3">
        <span className={eyebrow}>{SCALE.eyebrow}</span>
        <h2 className="font-serif text-xl leading-snug text-text-primary max-w-[46ch]">{SCALE.title}</h2>
        <p className="text-text-secondary text-sm leading-relaxed max-w-[62ch]">{SCALE.intro}</p>
        <p className="text-meta text-text-muted leading-relaxed border-t border-border-default pt-3">
          {SCALE.foot}
        </p>
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
                {busy === 'student' ? 'Starting…' : 'Start free →'}
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

        {/* ── Researchers — self-serve, same Stripe checkout as Pro ── */}
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
            // Self-serve again: this goes straight to the `research` Stripe checkout in billing.py
            // rather than the written-request modal. Eligibility (edu / non-profit) is checked at
            // signup instead of gating the purchase behind a human approval step.
            <div className="space-y-2">
              <button onClick={() => startPlan('research', 'Researcher')} disabled={busy === 'research'} className={primaryBtn}>
                {busy === 'research' ? 'Starting…' : 'Start now →'}
              </button>
              <p className="text-meta text-text-muted text-center leading-relaxed">
                Verification happens at signup — instant for .edu, .ac.uk, and registered non-profits.
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
          {/* Benefit before arithmetic — the price is only legible once you know what it buys. */}
          <p className="font-serif text-lg leading-snug text-text-primary mt-1">{PRO.promise}</p>
          <div className="mt-2 mb-3">
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
            <p className="text-meta leading-relaxed text-text-primary">{FOUNDING.headline(seatsTotal)}</p>
            {/* The counter carries the urgency, so it gets the size the sentence above it doesn't. */}
            <p className="font-mono text-base font-medium tracking-tight text-green-accent mt-1">
              {FOUNDING.remainingLine(seatsRemaining, seatsTotal)}
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
                {busy === 'pro' ? 'Starting…' : 'Start your 90-day trial →'}
              </button>
              {/* The trial length is argued rather than offered — see PRO.trialNote. Stacked next to a
                  half-price founding rate, "90 days free" alone reads as a discount on a discount. */}
              <p className="text-meta text-text-muted text-center leading-relaxed">{PRO.trialNote}</p>
              {/* The walkthrough sits here rather than in its own band: by this point the reader is
                  either buying or wants to talk to someone first. Enterprise gets its own CTA below. */}
              <p className="text-meta text-text-muted text-center leading-relaxed">
                Prefer to talk first?{' '}
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

      {/* The "fair questions" objection grid that used to sit here now lives on /methodology as its FAQ
          section — same FAIR_QUESTIONS source, one copy of the answers. */}

      {/* Data strip — its own section below the grid: a different buyer (a platform, not a
          practitioner) buying the corpus rather than the interface, so it ends in a licensing
          conversation instead of the self-serve API docs. */}
      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="max-w-2xl">
          <h3 className="font-serif text-lg text-text-primary mb-1">{DATA.title}</h3>
          <p className="text-text-secondary text-sm leading-relaxed">{DATA.blurb}</p>
        </div>
        <button
          onClick={() => openPlan('api', 'Data licensing', 'Licence the Atlas corpus', 'pricing_data')}
          className="shrink-0 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          {DATA.cta}
        </button>
      </section>

      <p className="border-t border-border-default pt-5 text-meta text-text-muted">
        Prices in USD. Annual terms billed once; monthly cancels at the end of the month.
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
