'use client';
import { useSyncExternalStore } from 'react';
import { getApiReachable, subscribeApiReachable, getSnapshotMeta } from '@/lib/snapshot';
import { formatDate } from '@/lib/utils';

/**
 * Shows nothing while the live API is reachable. When a call falls back to the
 * cached snapshot (cold start / offline), it surfaces a quiet "showing saved data
 * as of <date>" note so the displayed numbers read as last-known rather than wrong.
 */
export function FreshnessNote({ className = '' }: { className?: string }) {
  const reachable = useSyncExternalStore(subscribeApiReachable, getApiReachable, () => true);
  if (reachable) return null;

  const meta = getSnapshotMeta();
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs text-text-muted ${className}`}>
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-urgency-medium animate-pulse" />
      {meta ? <>Showing saved data from {formatDate(meta.generated_at)} · reconnecting…</> : <>Reconnecting…</>}
    </span>
  );
}
