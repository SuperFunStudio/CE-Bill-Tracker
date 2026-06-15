'use client';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  onIdTokenChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  signOut as fbSignOut,
  type User,
} from 'firebase/auth';
import { auth, googleProvider } from '@/lib/firebase';
import { track } from '@/lib/analytics';

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export interface Entitlement {
  plan: string;
  status: string | null;
  is_pro: boolean;
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

  const getToken = useCallback(async () => {
    return auth.currentUser ? auth.currentUser.getIdToken() : null;
  }, []);

  const signInEmail = useCallback(async (email: string, password: string) => {
    await signInWithEmailAndPassword(auth, email, password);
    track('login', { method: 'email' });
  }, []);

  const signUpEmail = useCallback(async (email: string, password: string) => {
    await createUserWithEmailAndPassword(auth, email, password);
    track('sign_up', { method: 'email' });
  }, []);

  const signInGoogle = useCallback(async () => {
    await signInWithPopup(auth, googleProvider);
    track('login', { method: 'google' });
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
  };

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
