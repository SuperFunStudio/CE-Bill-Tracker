'use client';
import { useEffect, useState } from 'react';
import { fetchBill } from '@/lib/api';
import { formatDate } from '@/lib/utils';
import { StatusBadge } from '@/components/ui/StatusBadge';

/**
 * The /bill/[id]/[slug] pages are a static export, so whatever status the bill had at deploy time
 * gets frozen into the HTML. When a bill moves after that (CA AB-864: enacted Sept 30, caught up by
 * ingest Nov 7, page built Nov 3), the page would contradict the app and the alert email until the
 * next deploy. These components render the build-time value first (so crawlers and no-JS readers
 * still see something), then swap in the live value from the API.
 *
 * The badge and the last-action date share one request per bill id via a module-level cache.
 */
interface LiveFields {
  status: string | null;
  lastAction?: string | null;
}

const cache = new Map<number, Promise<LiveFields | null>>();

function loadLive(id: number): Promise<LiveFields | null> {
  const hit = cache.get(id);
  if (hit) return hit;
  const p: Promise<LiveFields | null> = fetchBill(id)
    .then(b => ({ status: b.status, lastAction: b.last_action_date || b.status_date }))
    .catch(() => null); // keep showing the build-time value if the API is unreachable
  cache.set(id, p);
  return p;
}

function useLive(id: number, initial: LiveFields): LiveFields {
  const [fields, setFields] = useState(initial);
  useEffect(() => {
    let alive = true;
    loadLive(id).then(live => {
      if (alive && live) setFields(live);
    });
    return () => {
      alive = false;
    };
  }, [id]);
  return fields;
}

export function LiveStatusBadge({
  billId,
  status,
  lastAction,
}: {
  billId: number;
  status: string | null;
  lastAction?: string | null;
}) {
  const live = useLive(billId, { status, lastAction });
  return <StatusBadge status={live.status} showCaption dashWhenEmpty={false} />;
}

export function LiveLastAction({
  billId,
  status,
  lastAction,
}: {
  billId: number;
  status: string | null;
  lastAction?: string | null;
}) {
  const live = useLive(billId, { status, lastAction });
  return <>{formatDate(live.lastAction)}</>;
}
