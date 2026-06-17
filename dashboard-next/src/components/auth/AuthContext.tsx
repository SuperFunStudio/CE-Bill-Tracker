'use client';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  onIdTokenChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  getAdditionalUserInfo,
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

  // onIdTokenChanged covers sign-in, sign-out, and silent token refreshes.
  useEffect(() => {
    const unsub = onIdTokenChanged(auth, async u => {
      setUser(u);
      setLoading(false);
      await fetchEntitlement(u);
    });
    return unsub;
  }, [fetchEntitlement]);

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

  const getToken = useCallback(async () => {
    return auth.currentUser ? auth.currentUser.getIdToken() : null;
  }, []);

  // After a NEW account is created, credit any pending share-to-unlock referral (one-shot, best-effort
  // — the backend enforces the not-self / one-per-account guards and grants the referrer).
  const attributePendingReferral = useCallback(async () => {
    if (typeof window === 'undefined') return;
    let code: string | null = null;
    try {
      code = localStorage.getItem(PENDING_REF_KEY);
      if (code) localStorage.removeItem(PENDING_REF_KEY);
    } catch {
      return;
    }
    if (!code) return;
    const token = auth.currentUser ? await auth.currentUser.getIdToken() : null;
    await attributeReferral(token, code);
  }, []);

  // Everything a brand-new free account gets: credit any pending referral (rewards the referrer), claim
  // its own one-time 7-day signup trial, then refresh entitlement so Pro reflects immediately.
  const provisionNewAccount = useCallback(async () => {
    await attributePendingReferral();
    await startSignupTrial(getToken);
    await fetchEntitlement(auth.currentUser);
  }, [attributePendingReferral, getToken, fetchEntitlement]);

  const signInEmail = useCallback(async (email: string, password: string) => {
    await signInWithEmailAndPassword(auth, email, password);
    track('login', { method: 'email' });
  }, []);

  const signUpEmail = useCallback(
    async (email: string, password: string) => {
      await createUserWithEmailAndPassword(auth, email, password);
      track('sign_up', { method: 'email' });
      await provisionNewAccount();
    },
    [provisionNewAccount],
  );

  const signInGoogle = useCallback(async () => {
    const result = await signInWithPopup(auth, googleProvider);
    const isNew = getAdditionalUserInfo(result)?.isNewUser;
    track(isNew ? 'sign_up' : 'login', { method: 'google' });
    if (isNew) await provisionNewAccount();
  }, [provisionNewAccount]);

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
