// Client helpers for the Stripe billing flow. Checkout sessions are created server-side (the secret
// key never touches the browser); we just POST with the Firebase ID token and redirect to the
// hosted Stripe URL. See app/api/billing.py + gating-and-monetization-plan.
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

async function postWithToken(
  path: string,
  token: string | null,
  body?: unknown,
): Promise<string> {
  if (!token) throw new Error('Please sign in first.');
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Request failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  const { url } = await res.json();
  return url as string;
}

/** Begin the Pro subscription for a billing period (default annual). Opens Checkout — the founding
 *  offer (90-day trial + first-year coupon) is applied server-side — and sends the browser to Stripe. */
export async function startProCheckout(
  getToken: () => Promise<string | null>,
  period: 'monthly' | 'annual' = 'annual',
): Promise<void> {
  const url = await postWithToken('/billing/checkout', await getToken(), { period });
  window.location.href = url;
}

/** Grant the one-time 7-day signup trial (full Pro, no card). Best-effort; the backend is idempotent
 *  (no-op if already used). Call right after a free account is created. Returns `{ granted }` —
 *  granted is true ONLY on the genuine first grant for this account, so the caller can fire a
 *  one-time "you're signed up" confirmation without re-showing it on every later sign-in. */
export async function startSignupTrial(
  getToken: () => Promise<string | null>,
): Promise<{ granted: boolean }> {
  const token = await getToken();
  if (!token) return { granted: false };
  try {
    const res = await fetch(`${API}/billing/signup-trial`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return { granted: false };
    const body = await res.json().catch(() => ({}));
    return { granted: !!body?.granted };
  } catch {
    /* best-effort — they just won't get the auto-trial */
    return { granted: false };
  }
}

/** Open the Stripe customer portal so a subscriber can manage or cancel. */
export async function openBillingPortal(getToken: () => Promise<string | null>): Promise<void> {
  const url = await postWithToken('/billing/portal', await getToken());
  window.location.href = url;
}

/** Permanently delete the signed-in account (cancels Stripe, purges data, removes the auth user).
 * Returns the server's report — `firebase_deleted` flags whether the auth identity was removed. */
export async function deleteAccount(
  getToken: () => Promise<string | null>,
): Promise<{ deleted: boolean; firebase_deleted: boolean }> {
  const token = await getToken();
  if (!token) throw new Error('Please sign in first.');
  const res = await fetch(`${API}/me/account`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Could not delete account (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  return res.json();
}

/** Fetch the Pro-gated full Design Guide HTML and open it in a new tab. */
export async function openFullGuide(getToken: () => Promise<string | null>): Promise<void> {
  const token = await getToken();
  if (!token) throw new Error('Please sign in first.');
  const res = await fetch(`${API}/design-guide/full`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 403) throw new Error('A Pro subscription is required.');
  if (!res.ok) throw new Error(`Could not load the guide (${res.status}).`);
  const html = await res.text();
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
  window.open(url, '_blank', 'noopener');
}
