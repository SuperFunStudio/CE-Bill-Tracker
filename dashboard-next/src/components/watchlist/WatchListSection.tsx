'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { BillTable } from '@/components/bills/BillTable';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { SkeletonList } from '@/components/ui/SkeletonList';
import { StarIcon, LockIcon } from '@/components/ui/icons';
import { GateCard } from '@/components/ui/GateCard';
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

/** The user's watch list — their starred bills + per-account alert preferences. Self-gating:
 *  routes anon→sign-in and non-Pro→upgrade. Lives at the top of /library ("My Library"); the
 *  old standalone /watchlist route now redirects here. */
export function WatchListSection() {
  const { user, isPro, loading, openAuth, getToken } = useAuth();
  const { watched, ready } = useWatchlist();
  const { data: bills = [] } = useBills({ ce_relevant: true, limit: 5000 });

  const watchedBills = useMemo(
    () => bills.filter(b => watched.has(b.id)),
    [bills, watched],
  );

  return (
    <div className="space-y-4">
      <SectionHeader title="Your Watch List" subtitle="Bills you're following — starred from anywhere in the explorer." />

      {loading ? (
        <SkeletonList rows={4} />
      ) : !user ? (
        <GateCard
          gate="pro"
          feature="watchlist"
          outcome="sign_in"
          icon={<StarIcon className="text-2xl text-green-accent" />}
          title="Sign in to use watch lists"
          body="Star any bill to follow it, and it'll show up here across all your devices."
          cta="Sign in"
          onClick={openAuth}
        />
      ) : !isPro ? (
        <GateCard
          gate="pro"
          feature="watchlist"
          outcome="checkout"
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
          <p className="text-text-secondary text-sm">
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

// The last two are opt-in extras: off unless the user checks them, and the backend never defaults
// them on — so unchecked here really means "no extra email".
const ALERT_OPTIONS: { event: WatchlistAlertEvent; label: string; hint: string }[] = [
  { event: 'status_change', label: 'Status changes', hint: 'introduced, passed, signed, vetoed…' },
  {
    event: 'deadline',
    label: 'Deadline reminders',
    hint: 'an extra email when a compliance deadline you follow is approaching',
  },
  {
    event: 'weekly_digest',
    label: 'Weekly digest',
    hint: 'get the roundup weekly instead of monthly',
  },
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
        <p className="text-text-muted text-xs">
          We&apos;ll send a note when a bill you follow moves. Deadline reminders and the weekly
          digest are optional extras — you&apos;ll only get them if you turn them on here.
        </p>
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
