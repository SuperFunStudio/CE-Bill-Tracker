// Share-to-unlock referral client. A signed-in user fetches their code, shares `<origin>/?ref=<code>`,
// and when a NEW account signs up via that link the *referrer* earns 30 days of Pro (granted server-
// side). See app/api/referrals.py. The ?ref capture + signup attribution live in AuthContext.
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

/** localStorage key holding a pending referral code captured from a ?ref= landing, until signup. */
export const PENDING_REF_KEY = 'signalscout_pending_ref';

/** The signed-in user's referral code (generated server-side on first call). */
export async function getMyReferralCode(token: string | null): Promise<string> {
  if (!token) throw new Error('Please sign in first.');
  const res = await fetch(`${API}/referrals/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Could not load your referral link (${res.status}).`);
  const { code } = await res.json();
  return code as string;
}

/** Build the shareable link from the current origin so it works in any environment. */
export function referralLink(code: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  return `${origin}/?ref=${encodeURIComponent(code)}`;
}

/** Credit a captured referral for the just-signed-up account. Best-effort; backend enforces the
 *  guards (not-self, one-per-account). Returns whether a grant was made. */
export async function attributeReferral(
  token: string | null,
  code: string,
): Promise<{ granted: boolean; reason?: string }> {
  if (!token || !code) return { granted: false, reason: 'no_token_or_code' };
  try {
    const res = await fetch(`${API}/referrals/attribute`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    if (!res.ok) return { granted: false, reason: `http_${res.status}` };
    return await res.json();
  } catch {
    return { granted: false, reason: 'network' };
  }
}
