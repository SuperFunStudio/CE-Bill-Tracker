// Anonymous personalization identity + persistence.
//
// A signed-out reader who sets a scope is telling us exactly what they came for — the same signal that
// makes the subscriber list legible ("Panasonic: US, solar panels"). Until now that answer never left
// the browser, because personalization was account-gated and ScopeContext.persist() early-returned
// without a user. This module gives anonymous scope a pseudonymous key and a way home.
//
// PRIVACY: the id is minted by the browser (crypto.randomUUID), stored in localStorage, and is NOT
// derived from IP, user agent, or anything else that could re-identify someone. Clearing site data
// genuinely starts over. We send states + materials only — never free text — matching the closed
// vocabularies the backend accepts (app/api/scope.py).

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const ID_KEY = 'atlas_anon_v1';

/**
 * The stable-per-browser anonymous id, minted on first use. Returns null on the server, and in
 * private modes where localStorage throws — personalization still works locally there, it just
 * doesn't reach the backend, which is the correct trade rather than a hard failure.
 */
export function getAnonId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const existing = window.localStorage.getItem(ID_KEY);
    if (existing) return existing;
    // randomUUID needs a secure context; fall back so http://localhost dev still works.
    const id =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 14)}`;
    window.localStorage.setItem(ID_KEY, id);
    return id;
  } catch {
    return null;
  }
}

/** Clear the anonymous id — used when a scope is reset, so "start over" really does. */
export function clearAnonId(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(ID_KEY);
  } catch {
    /* ignore */
  }
}

export interface AnonScopePayload {
  states: string[];
  material_categories: string[];
  configured: boolean;
  scoped: boolean;
}

/**
 * Best-effort push of an anonymous scope. Never throws and never blocks the UI: personalization has
 * already been applied locally by the time this runs, so a failed write costs us a data point, not
 * the reader's experience.
 */
export async function postAnonScope(payload: AnonScopePayload): Promise<void> {
  const client_id = getAnonId();
  if (!client_id) return;
  try {
    await fetch(`${API}/anon-scope`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id, ...payload }),
      keepalive: true, // survives a scope save that's immediately followed by a navigation
    });
  } catch {
    /* offline / blocked — anonymous scope is a nice-to-have signal */
  }
}
