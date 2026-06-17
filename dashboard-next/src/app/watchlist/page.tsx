'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { BillTable } from '@/components/bills/BillTable';
import { StarIcon, LockIcon } from '@/components/ui/icons';
import { useAuth } from '@/components/auth/AuthContext';
import { useWatchlist } from '@/components/watchlist/WatchlistContext';
import { startProCheckout } from '@/lib/billing';
import { PRO, upgradeLabel } from '@/lib/tiers';
import { useBills } from '@/hooks/useBills';
import {
  getWatchlistPrefs,
  saveWatchlistPrefs,
  type WatchlistAlertEvent,
  type WatchlistPrefs,
} from '@/lib/userSettings';

export default function WatchlistPage() {
  const { user, isPro, loading, openAuth, getToken } = useAuth();
  const { watched, ready } = useWatchlist();
  const { data: bills = [] } = useBills({ epr_relevant: true, limit: 5000 });

  const watchedBills = useMemo(
    () => bills.filter(b => watched.has(b.id)),
    [bills, watched],
  );

  return (
    <div className="p-6 space-y-8 max-w-6xl mx-auto">
      <GazetteHeader title="My Watchlist" subtitle="Bills you're following — starred from anywhere in the explorer." />

      {loading ? (
        <p className="text-text-muted text-sm">Loading…</p>
      ) : !user ? (
        <Gate
          icon={<StarIcon className="text-2xl text-green-accent" />}
          title="Sign in to use watch lists"
          body="Star any bill to follow it, and it'll show up here across all your devices."
          cta="Sign in"
          onClick={openAuth}
        />
      ) : !isPro ? (
        <Gate
          icon={<LockIcon className="text-2xl text-green-accent" />}
          title="Watch lists are a Pro feature"
          body={`Follow bills, get alerts when they move, and track the deadlines that matter to you. ${PRO.foundingNote}`}
          cta={upgradeLabel()}
          onClick={() => startProCheckout(getToken)}
        />
      ) : !ready ? (
        <p className="text-text-muted text-sm">Loading your watchlist…</p>
      ) : watched.size === 0 ? (
        <div className="rounded-xl border border-border-default bg-bg-secondary p-8 text-center space-y-2">
          <StarIcon className="text-2xl text-text-muted mx-auto" />
          <p className="text-text-primary font-medium">No bills yet</p>
          <p className="text-text-muted text-sm">
            Open the <Link href="/" className="text-green-accent hover:underline">Bill Explorer</Link> and tap the ☆ on any
            bill to start following it.
          </p>
        </div>
      ) : (
        <>
          <NotifyPrefs />
          <BillTable bills={watchedBills} />
        </>
      )}
    </div>
  );
}

const ALERT_OPTIONS: { event: WatchlistAlertEvent; label: string; hint: string }[] = [
  { event: 'status_change', label: 'Status changes', hint: 'introduced, passed, signed, vetoed…' },
  { event: 'deadline', label: 'Compliance deadlines', hint: 'when a deadline is approaching' },
];

/** Pro per-account control for which events email the user about their watched bills. */
function NotifyPrefs() {
  const { getToken } = useAuth();
  const [prefs, setPrefs] = useState<WatchlistPrefs | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      const p = await getWatchlistPrefs(await getToken());
      if (active) setPrefs(p);
    })();
    return () => {
      active = false;
    };
  }, [getToken]);

  const persist = useCallback(
    async (next: WatchlistPrefs) => {
      const prev = prefs;
      setPrefs(next); // optimistic
      try {
        await saveWatchlistPrefs(await getToken(), next);
      } catch {
        setPrefs(prev); // reconcile on failure
      }
    },
    [prefs, getToken],
  );

  if (!prefs) return null;

  const toggle = (event: WatchlistAlertEvent) => {
    const on = prefs.alert_on.includes(event);
    const alert_on = on
      ? prefs.alert_on.filter(e => e !== event)
      : [...prefs.alert_on, event];
    persist({ ...prefs, alert_on });
  };

  return (
    <div className="rounded-xl border border-border-default bg-bg-secondary p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-text-primary text-sm font-medium">Email me about these bills</p>
        <p className="text-text-muted text-xs">We&apos;ll send a note when a bill you follow moves.</p>
      </div>
      <div className="flex flex-wrap gap-4">
        {ALERT_OPTIONS.map(({ event, label, hint }) => (
          <label key={event} className="flex items-center gap-2 cursor-pointer" title={hint}>
            <input
              type="checkbox"
              checked={prefs.alert_on.includes(event)}
              onChange={() => toggle(event)}
              className="accent-green-accent h-4 w-4"
            />
            <span className="text-text-secondary text-sm">{label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function Gate({ icon, title, body, cta, onClick }: {
  icon: React.ReactNode; title: string; body: string; cta: string; onClick: () => void;
}) {
  return (
    <div className="rounded-xl border border-green-accent bg-green-dark/20 p-8 text-center space-y-3 max-w-xl mx-auto">
      <div>{icon}</div>
      <h2 className="font-serif text-xl text-text-primary">{title}</h2>
      <p className="text-text-secondary text-sm leading-relaxed">{body}</p>
      <button
        onClick={onClick}
        className="inline-flex items-center gap-2 rounded-lg bg-green-accent text-bg-primary px-5 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity"
      >
        {cta}
      </button>
    </div>
  );
}
