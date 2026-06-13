// Client helpers for the Stripe billing flow. Checkout sessions are created server-side (the secret
// key never touches the browser); we just POST with the Firebase ID token and redirect to the
// hosted Stripe URL. See app/api/billing.py + gating-and-monetization-plan.
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

async function postWithToken(path: string, token: string | null): Promise<string> {
  if (!token) throw new Error('Please sign in first.');
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Request failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  const { url } = await res.json();
  return url as string;
}

/** Begin the Pro subscription: create a Checkout Session and send the browser to Stripe. */
export async function startProCheckout(getToken: () => Promise<string | null>): Promise<void> {
  const url = await postWithToken('/billing/checkout', await getToken());
  window.location.href = url;
}

/** Open the Stripe customer portal so a subscriber can manage or cancel. */
export async function openBillingPortal(getToken: () => Promise<string | null>): Promise<void> {
  const url = await postWithToken('/billing/portal', await getToken());
  window.location.href = url;
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
