'use client';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import {
  onIdTokenChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  getAdditionalUserInfo,
  sendEmailVerification,
  signOut as fbSignOut,
  type User,
} from 'firebase/auth';
import { auth, googleProvider } from '@/lib/firebase';
import { track } from '@/lib/analytics';
import { startProCheckout, startSignupTrial } from '@/lib/billing';
import { attributeReferral, PENDING_REF_KEY } from '@/lib/referrals';

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export interface Entitlement {
  plan: string; // live tier: "free" | "pro"
  status: string | null;
  is_pro: boolean; // the single paid gate — timeline, watchlists, full Design Guide, CSV
  is_trial?: boolean; // mid-trial (founding 90-day Stripe trial or a comp grant); shows a trial badge
  is_founding?: boolean; // founding member (founding coupon applied at checkout); shows a badge
  current_period_end: string | null;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  entitlement: Entitlement | null;
  isPro: boolean;
  isAdmin: boolean;
  authModalOpen: boolean;
  openAuth: () => void;
  closeAuth: () => void;
  signInEmail: (email: string, password: string) => Promise<void>;
  signUpEmail: (email: string, password: string) => Promise<void>;
  signInGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
  refreshEntitlement: () => Promise<void>;
  /** True once Firebase considers the email verified (Google sign-ins are always verified). The
   *  no-card trial + referral credit only land after this flips true — see H-2. */
  emailVerified: boolean;
  /** Re-send the verification email to a signed-in but unverified account. */
  resendVerification: () => Promise<void>;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [entitlement, setEntitlement] = useState<Entitlement | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);

  const fetchEntitlement = useCallback(async (u: User | null) => {
    if (!u) {
      setEntitlement(null);
      setIsAdmin(false);
      return;
    }
    try {
      const token = await u.getIdToken();
      const [entRes, adminRes] = await Promise.all([
        fetch(`${API}/billing/me`, { headers: { Authorization: `Bearer ${token}` } }),
        // 200 only for an allowlisted admin; 403 for everyone else. Used to reveal the hidden console.
        fetch(`${API}/admin/me`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      setEntitlement(entRes.ok ? await entRes.json() : null);
      setIsAdmin(adminRes.ok);
    } catch {
      setEntitlement(null);
      setIsAdmin(false);
    }
  }, []);

  const getToken = useCallback(async () => {
    return auth.currentUser ? auth.currentUser.getIdToken() : null;
  }, []);

  // Credit any pending share-to-unlock referral. The backend now requires the *referred* account to be
  // email-verified (H-2), so on an unverified account the grant is deferred — we keep the pending code
  // and let the post-verification provision retry it. Cleared only on a terminal outcome.
  const attributePendingReferral = useCallback(async () => {
    if (typeof window === 'undefined') return;
    let code: string | null = null;
    try {
      code = localStorage.getItem(PENDING_REF_KEY);
    } catch {
      return;
    }
    if (!code) return;
    const token = auth.currentUser ? await auth.currentUser.getIdToken() : null;
    const res = await attributeReferral(token, code);
    const terminal =
      res.granted || ['invalid_code', 'self', 'already_referred', 'no_code'].includes(res.reason ?? '');
    if (terminal) {
      try { localStorage.removeItem(PENDING_REF_KEY); } catch { /* ignore */ }
    }
  }, []);

  // Everything a verified free account gets: credit any pending referral (rewards the referrer), claim
  // its own one-time 7-day signup trial, then refresh entitlement so Pro reflects immediately. Gated on
  // a verified email server-side, so this no-ops cleanly for an unverified account.
  const provisionNewAccount = useCallback(async () => {
    await attributePendingReferral();
    await startSignupTrial(getToken);
    await fetchEntitlement(auth.currentUser);
  }, [attributePendingReferral, getToken, fetchEntitlement]);

  // Provision a given uid at most once per session (the verified-poll below can fire repeatedly).
  const provisionedUids = useRef<Set<string>>(new Set());
  const provisionOnce = useCallback(async (uid: string) => {
    if (provisionedUids.current.has(uid)) return;
    provisionedUids.current.add(uid);
    await provisionNewAccount();
  }, [provisionNewAccount]);

  // onIdTokenChanged covers sign-in, sign-out, and silent token refreshes (incl. the forced refresh the
  // verified-poll triggers). Comp grants only land once the email is verified — see H-2.
  useEffect(() => {
    const unsub = onIdTokenChanged(auth, async u => {
      setUser(u);
      setLoading(false);
      await fetchEntitlement(u);
      if (u && u.emailVerified) await provisionOnce(u.uid);
    });
    return unsub;
  }, [fetchEntitlement, provisionOnce]);

  // Capture a ?ref= code on first landing and stash it until signup, when it's attributed.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const ref = new URLSearchParams(window.location.search).get('ref');
    if (ref) {
      try {
        localStorage.setItem(PENDING_REF_KEY, ref.trim());
      } catch {
        /* private mode / storage disabled — referral just won't attribute */
      }
    }
  }, []);

  // While signed in but unverified, watch for the user clicking the verification link (often in another
  // tab): reload on focus + a bounded interval, and force a token refresh the moment it flips so
  // onIdTokenChanged provisions the trial/referral. Stops after 10 min to avoid an endless poll.
  useEffect(() => {
    if (!user || user.emailVerified) return;
    let cancelled = false;
    const check = async () => {
      try {
        await user.reload();
        if (!cancelled && auth.currentUser?.emailVerified) {
          await auth.currentUser.getIdToken(true); // fire onIdTokenChanged → provision
        }
      } catch {
        /* transient — try again on the next tick/focus */
      }
    };
    const onFocus = () => { void check(); };
    window.addEventListener('focus', onFocus);
    const interval = setInterval(() => { void check(); }, 15000);
    const stop = setTimeout(() => clearInterval(interval), 10 * 60 * 1000);
    return () => {
      cancelled = true;
      window.removeEventListener('focus', onFocus);
      clearInterval(interval);
      clearTimeout(stop);
    };
  }, [user]);

  const resendVerification = useCallback(async () => {
    if (auth.currentUser && !auth.currentUser.emailVerified) {
      await sendEmailVerification(auth.currentUser);
    }
  }, []);

  const signInEmail = useCallback(async (email: string, password: string) => {
    await signInWithEmailAndPassword(auth, email, password);
    track('login', { method: 'email' });
  }, []);

  const signUpEmail = useCallback(async (email: string, password: string) => {
    const cred = await createUserWithEmailAndPassword(auth, email, password);
    track('sign_up', { method: 'email' });
    // Start email verification; the trial + referral provision once they verify (H-2). Google sign-ins
    // skip this — their email is already verified, so onIdTokenChanged provisions them immediately.
    try { await sendEmailVerification(cred.user); } catch { /* best-effort */ }
  }, []);

  const signInGoogle = useCallback(async () => {
    const result = await signInWithPopup(auth, googleProvider);
    const isNew = getAdditionalUserInfo(result)?.isNewUser;
    track(isNew ? 'sign_up' : 'login', { method: 'google' });
    // Provisioning runs via onIdTokenChanged (Google emails are verified).
  }, []);

  const signOut = useCallback(async () => {
    await fbSignOut(auth);
  }, []);

  const value: AuthState = {
    user,
    loading,
    entitlement,
    isPro: !!entitlement?.is_pro,
    isAdmin,
    authModalOpen,
    openAuth: () => setAuthModalOpen(true),
    closeAuth: () => setAuthModalOpen(false),
    signInEmail,
    signUpEmail,
    signInGoogle,
    signOut,
    getToken,
    refreshEntitlement: () => fetchEntitlement(auth.currentUser),
    emailVerified: !!user?.emailVerified,
    resendVerification,
  };

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

/**
 * Routes a Pro-only action through the right conversion step: an anonymous visitor is sent to
 * sign-in (a free account is the first gate), a signed-in Free user to Stripe Checkout, and a Pro
 * subscriber runs the action. Returns true only when the action actually ran.
 */
export function useProGate(): (action: () => void, feature?: string) => boolean {
  const { user, isPro, openAuth, getToken } = useAuth();
  return useCallback(
    (action: () => void, feature?: string) => {
      // gate_hit captures the conversion decision at every gated feature: did it wall the visitor at
      // sign-in, send a Free user to checkout, or pass a subscriber through? `feature` says which CTA.
      if (!user) {
        track('gate_hit', { gate: 'pro', outcome: 'sign_in', feature });
        openAuth();
        return false;
      }
      if (!isPro) {
        track('gate_hit', { gate: 'pro', outcome: 'checkout', feature });
        startProCheckout(getToken);
        return false;
      }
      track('gate_hit', { gate: 'pro', outcome: 'allowed', feature });
      action();
      return true;
    },
    [user, isPro, openAuth, getToken],
  );
}
