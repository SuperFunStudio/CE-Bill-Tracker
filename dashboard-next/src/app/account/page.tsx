'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { LockIcon, StarIcon } from '@/components/ui/icons';
import { useAuth } from '@/components/auth/AuthContext';
import { startProCheckout, openBillingPortal, deleteAccount } from '@/lib/billing';
import { track } from '@/lib/analytics';

/** Friendly label for a Firebase provider id (the first linked sign-in method). */
function providerLabel(id: string | undefined): string {
  if (id === 'google.com') return 'Google';
  if (id === 'password') return 'Email & password';
  return id ?? '—';
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

export default function AccountPage() {
  const { user, loading, isPro, entitlement, openAuth, signOut, getToken } = useAuth();

  return (
    <div className="p-6 space-y-8 max-w-3xl mx-auto">
      <GazetteHeader title="Account" subtitle="Your profile, plan, and data — all in one place." />

      {loading ? (
        <p className="text-text-muted text-sm">Loading…</p>
      ) : !user ? (
        <div className="rounded-xl border border-green-accent bg-green-dark/20 p-8 text-center space-y-3 max-w-xl mx-auto">
          <LockIcon className="text-2xl text-green-accent mx-auto" />
          <h2 className="font-serif text-xl text-text-primary">Sign in to manage your account</h2>
          <p className="text-text-secondary text-sm leading-relaxed">
            Sign in to view your profile, change your plan, or delete your account.
          </p>
          <button
            onClick={openAuth}
            className="inline-flex items-center gap-2 rounded-lg bg-green-accent text-bg-primary px-5 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity"
          >
            Sign in
          </button>
        </div>
      ) : (
        <>
          <ProfileCard
            email={user.email ?? '—'}
            created={formatDate(user.metadata?.creationTime)}
            provider={providerLabel(user.providerData?.[0]?.providerId)}
          />
          <PlanCard
            isPro={isPro}
            status={entitlement?.status ?? null}
            periodEnd={entitlement?.current_period_end ?? null}
            getToken={getToken}
          />
          <DataCard />
          <DangerZone
            email={user.email ?? ''}
            getToken={getToken}
            signOut={signOut}
          />
        </>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border-default bg-bg-secondary p-5 space-y-4">
      <h2 className="font-serif text-lg text-text-primary">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <span className="text-text-muted">{label}</span>
      <span className="text-text-primary text-right">{value}</span>
    </div>
  );
}

function ProfileCard({ email, created, provider }: { email: string; created: string; provider: string }) {
  return (
    <Section title="Profile">
      <Row label="Email" value={email} />
      <Row label="Member since" value={created} />
      <Row label="Sign-in method" value={provider} />
    </Section>
  );
}

function PlanCard({
  isPro,
  status,
  periodEnd,
  getToken,
}: {
  isPro: boolean;
  status: string | null;
  periodEnd: string | null;
  getToken: () => Promise<string | null>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // "canceled" subscriptions stay Pro until the period ends — frame the date accordingly.
  const dateLabel = status === 'canceled' ? 'Access ends' : 'Renews';

  async function manage() {
    setError(null);
    setBusy(true);
    track('account_manage_plan');
    try {
      await openBillingPortal(getToken);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not open the billing portal.');
      setBusy(false);
    }
  }

  async function upgrade() {
    setError(null);
    setBusy(true);
    track('account_upgrade');
    try {
      await startProCheckout(getToken);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start checkout.');
      setBusy(false);
    }
  }

  return (
    <Section title="Plan & billing">
      <Row
        label="Current plan"
        value={
          isPro ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="text-[9px] uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-1.5 py-0.5">
                Pro
              </span>
              <span>$39/mo</span>
            </span>
          ) : (
            'Free'
          )
        }
      />
      {isPro && <Row label="Status" value={status ?? 'active'} />}
      {isPro && periodEnd && <Row label={dateLabel} value={formatDate(periodEnd)} />}

      <div className="pt-1">
        {isPro ? (
          <button
            onClick={manage}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg border border-green-accent bg-green-dark px-4 py-2 text-sm font-medium text-green-accent hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {busy ? 'Opening…' : 'Manage plan'}
          </button>
        ) : (
          <button
            onClick={upgrade}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg bg-green-accent text-bg-primary px-4 py-2 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {busy ? 'Starting…' : 'Upgrade to Pro — $39/mo →'}
          </button>
        )}
        {isPro && (
          <p className="text-text-muted text-xs mt-2">
            Opens the Stripe portal to update payment, view invoices, or cancel.
          </p>
        )}
      </div>
      {error && <p className="text-red-400 text-xs">{error}</p>}
    </Section>
  );
}

function DataCard() {
  return (
    <Section title="Your data">
      <p className="text-text-secondary text-sm leading-relaxed">
        Manage the bills you follow and which updates we email you about from your watchlist.
      </p>
      <Link
        href="/watchlist"
        className="inline-flex items-center gap-2 rounded-lg border border-border-default bg-bg-primary px-4 py-2 text-sm text-text-secondary hover:text-text-primary transition-colors"
      >
        <StarIcon className="text-green-accent" />
        My watchlist & alert preferences
      </Link>
    </Section>
  );
}

function DangerZone({
  email,
  getToken,
  signOut,
}: {
  email: string;
  getToken: () => Promise<string | null>;
  signOut: () => Promise<void>;
}) {
  const router = useRouter();
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Type-to-confirm: the delete button only arms once the typed text matches the account email.
  const armed = confirm.trim().toLowerCase() === email.trim().toLowerCase() && email.length > 0;

  async function remove() {
    if (!armed || busy) return;
    setError(null);
    setBusy(true);
    track('account_delete');
    try {
      await deleteAccount(getToken);
      await signOut();
      router.push('/');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete your account.');
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-red-500/40 bg-red-500/5 p-5 space-y-4">
      <h2 className="font-serif text-lg text-red-400">Delete account</h2>
      <p className="text-text-secondary text-sm leading-relaxed">
        This permanently cancels your subscription, erases your watchlist and preferences, and
        removes your sign-in. <span className="text-text-primary font-medium">This cannot be undone.</span>
      </p>
      <div className="space-y-2">
        <label htmlFor="confirm-email" className="block text-text-muted text-xs">
          Type your email <span className="text-text-primary">{email}</span> to confirm:
        </label>
        <input
          id="confirm-email"
          type="email"
          autoComplete="off"
          value={confirm}
          onChange={e => setConfirm(e.target.value)}
          placeholder={email}
          className="w-full max-w-sm rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-red-500/60 focus:outline-none"
        />
      </div>
      <button
        onClick={remove}
        disabled={!armed || busy}
        className="inline-flex items-center gap-2 rounded-lg bg-red-600 text-white px-4 py-2 text-sm font-medium hover:bg-red-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {busy ? 'Deleting…' : 'Delete account'}
      </button>
      {error && <p className="text-red-400 text-xs">{error}</p>}
    </section>
  );
}
