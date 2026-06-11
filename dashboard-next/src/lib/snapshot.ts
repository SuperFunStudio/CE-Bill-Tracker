'use client';
// CDN snapshot layer. The build bakes the summary endpoints to /data/*.json (see
// scripts/build-snapshot.mjs). At runtime we hydrate those into memory + localStorage,
// expose a synchronous getter for React Query `placeholderData` (instant first paint,
// never "0 bills"), and wrap live calls so a cold/unreachable API falls back to the
// last-known data instead of erroring blank.

// Must match the `name`s written by scripts/build-snapshot.mjs (+ 'meta').
const SNAPSHOTS = [
  'bills',
  'map-summary',
  'deadlines',
  'federal-actions',
  'litigation-cases',
  'companies',
  'meta',
] as const;
export type SnapshotName = (typeof SNAPSHOTS)[number];

export interface SnapshotMeta {
  generated_at: string;
  counts: Record<string, number | null>;
}

const mem = new Map<string, unknown>();

const lsKey = (name: string) => `snap:${name}`;
const hasWindow = () => typeof window !== 'undefined';

/** Synchronous best-effort read (memory → localStorage). Null during SSG / when absent. */
export function getSnapshot<T>(name: SnapshotName): T | null {
  if (mem.has(name)) return mem.get(name) as T;
  if (!hasWindow()) return null;
  try {
    const raw = window.localStorage.getItem(lsKey(name));
    if (raw) {
      const val = JSON.parse(raw) as T;
      mem.set(name, val);
      return val;
    }
  } catch {
    /* corrupt/blocked localStorage — ignore */
  }
  return null;
}

export const getSnapshotMeta = () => getSnapshot<SnapshotMeta>('meta');

function store(name: string, val: unknown): void {
  mem.set(name, val);
  if (!hasWindow()) return;
  try {
    window.localStorage.setItem(lsKey(name), JSON.stringify(val));
  } catch {
    /* quota / private mode — memory cache still serves this session */
  }
}

/** Fetch a CDN-baked snapshot file. Null on any failure (missing file, offline). */
async function fetchSnapshotFile<T>(name: SnapshotName): Promise<T | null> {
  if (!hasWindow()) return null;
  try {
    const res = await fetch(`/data/${name}.json`, { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

let hydrated = false;
/** Load every baked snapshot into memory + localStorage. Call once on app boot. */
export async function hydrateSnapshots(): Promise<void> {
  if (hydrated || !hasWindow()) return;
  hydrated = true;
  await Promise.all(
    SNAPSHOTS.map(async (name) => {
      const val = await fetchSnapshotFile(name);
      if (val !== null) store(name, val); // keep any newer live-cached value if the file is absent
    }),
  );
}

/**
 * Live-first fetch with snapshot fallback. Tries `live()`; on success caches the
 * result for instant subsequent loads. On failure (cold start / offline) returns the
 * last-known snapshot so the UI never goes blank — only rejects if no fallback exists.
 */
export async function resilient<T>(name: SnapshotName, live: () => Promise<T>): Promise<T> {
  try {
    const data = await live();
    store(name, data);
    setReachable(true);
    return data;
  } catch (err) {
    setReachable(false);
    const fallback = getSnapshot<T>(name) ?? (await fetchSnapshotFile<T>(name));
    if (fallback !== null) return fallback;
    throw err;
  }
}

// Whether the live API answered the most recent resilient() call. Drives the
// "showing saved data" hint via useSyncExternalStore.
let apiReachable = true;
const listeners = new Set<() => void>();

function setReachable(v: boolean): void {
  if (v === apiReachable) return;
  apiReachable = v;
  listeners.forEach((l) => l());
}

export const getApiReachable = () => apiReachable;

export function subscribeApiReachable(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}
