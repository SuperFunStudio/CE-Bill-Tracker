// Account-security emails (verify address / reset password) sent through OUR backend rather than the
// Firebase client SDK.
//
// Firebase's own mailer sends from `noreply@<project>.firebaseapp.com` — a cold sending identity that
// doesn't match the brand and isn't SPF/DKIM-aligned with atlascircular.com, on the two emails a user
// is most likely to be waiting on. The backend mints the same Firebase action link but delivers it via
// our authenticated sending domain, wrapped in the Atlas Circular masthead. See app/api/auth_email.py.
//
// Both helpers return `false` rather than throwing when the branded send didn't happen (flag off,
// email provider unconfigured, network error). The caller MUST fall back to the Firebase SDK on false —
// losing the pretty email must never mean a user can't verify or recover their account.
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

/** Branded "confirm your email" send for the signed-in account. The address comes from the verified
 *  token server-side, so nothing is passed in but auth. False → fall back to sendEmailVerification. */
export async function sendBrandedVerification(token: string | null): Promise<boolean> {
  if (!token) return false;
  try {
    const res = await fetch(`${API}/auth/send-verification`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return false;
    const { sent } = await res.json();
    return sent === true;
  } catch {
    return false;
  }
}

/** Branded password-reset send. Unauthenticated by necessity (the user can't sign in). The response
 *  is intentionally identical for unknown addresses, so callers must not surface the result as
 *  "no such account" — show the same "check your inbox" copy either way. False → fall back to
 *  sendPasswordResetEmail. */
export async function sendBrandedPasswordReset(email: string): Promise<boolean> {
  try {
    const res = await fetch(`${API}/auth/send-password-reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) return false;
    const { sent } = await res.json();
    return sent === true;
  } catch {
    return false;
  }
}
