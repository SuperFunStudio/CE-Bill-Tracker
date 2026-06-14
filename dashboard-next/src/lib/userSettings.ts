// Client for the per-account endpoints (app/api/user.py). Settings are free (any authed user);
// the watch list is Pro-gated server-side (403 if not Pro). All calls carry the Firebase ID token.
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

async function authedFetch(path: string, token: string | null, init?: RequestInit): Promise<Response> {
  if (!token) throw new Error('not signed in');
  return fetch(`${API}${path}`, {
    ...init,
    headers: { ...(init?.headers ?? {}), Authorization: `Bearer ${token}` },
  });
}

export type Prefs = Record<string, unknown>;

export async function fetchSettings(token: string | null): Promise<Prefs> {
  try {
    const res = await authedFetch('/me/settings', token);
    if (!res.ok) return {};
    const json = await res.json();
    return (json.prefs as Prefs) ?? {};
  } catch {
    return {};
  }
}

export async function saveSettings(token: string | null, prefs: Prefs): Promise<void> {
  await authedFetch('/me/settings', token, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prefs }),
  });
}

export async function getWatchlist(token: string | null): Promise<number[]> {
  const res = await authedFetch('/me/watchlist', token);
  if (!res.ok) return [];
  const json = await res.json();
  return (json.bill_ids as number[]) ?? [];
}

export async function addWatch(token: string | null, billId: number): Promise<void> {
  await authedFetch('/me/watchlist', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bill_id: billId }),
  });
}

export async function removeWatch(token: string | null, billId: number): Promise<void> {
  await authedFetch(`/me/watchlist/${billId}`, token, { method: 'DELETE' });
}

// Notification prefs for watched bills (which events to email about). Pro-gated server-side.
export type WatchlistAlertEvent = 'status_change' | 'text_update' | 'deadline';

export interface WatchlistPrefs {
  alert_on: WatchlistAlertEvent[];
  active: boolean;
}

const DEFAULT_WATCHLIST_PREFS: WatchlistPrefs = {
  alert_on: ['status_change', 'deadline'],
  active: true,
};

export async function getWatchlistPrefs(token: string | null): Promise<WatchlistPrefs> {
  try {
    const res = await authedFetch('/me/watchlist/prefs', token);
    if (!res.ok) return { ...DEFAULT_WATCHLIST_PREFS };
    return (await res.json()) as WatchlistPrefs;
  } catch {
    return { ...DEFAULT_WATCHLIST_PREFS };
  }
}

export async function saveWatchlistPrefs(
  token: string | null,
  prefs: WatchlistPrefs,
): Promise<void> {
  await authedFetch('/me/watchlist/prefs', token, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(prefs),
  });
}
