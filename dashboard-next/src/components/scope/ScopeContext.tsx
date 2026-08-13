'use client';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Scope, EMPTY_SCOPE, isEmptyScope, loadScope, saveScope, clearScope, normalizeScope } from '@/lib/scope';
import { useAuth } from '@/components/auth/AuthContext';
import { fetchSettings, patchSettings } from '@/lib/userSettings';
import { clearAnonId, postAnonScope } from '@/lib/anonScope';

interface ScopeContextValue {
  /** True once we've read localStorage — guards against SSR/first-paint flash. */
  ready: boolean;
  /** The reader's saved scope (EMPTY_SCOPE if they skipped or never set one). */
  scope: Scope;
  /** Whether the reader has been through onboarding at all (incl. an explicit skip). */
  isConfigured: boolean;
  /** Whether surfaces should currently filter to the scope (the "Show everything" toggle). */
  scoped: boolean;
  /** Whether the onboarding/edit modal should render. */
  editorOpen: boolean;
  /** Save a scope and close the modal. A non-empty scope turns scoping on. */
  saveAndClose: (s: Scope) => void;
  /** First-run "skip — show everything": records configuration without a scope. */
  skip: () => void;
  setScoped: (v: boolean) => void;
  openEditor: () => void;
  closeEditor: () => void;
  reset: () => void;
}

const ScopeContext = createContext<ScopeContextValue>({
  ready: false,
  scope: EMPTY_SCOPE,
  isConfigured: false,
  scoped: false,
  editorOpen: false,
  saveAndClose: () => {},
  skip: () => {},
  setScoped: () => {},
  openEditor: () => {},
  closeEditor: () => {},
  reset: () => {},
});

export function ScopeProvider({ children }: { children: React.ReactNode }) {
  const { user, getToken } = useAuth();
  const [ready, setReady] = useState(false);
  const [scope, setScope] = useState<Scope>(EMPTY_SCOPE);
  const [isConfigured, setIsConfigured] = useState(false);
  const [scoped, setScoped] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);

  // localStorage is the immediate / anonymous / offline source — read it first for instant paint.
  useEffect(() => {
    const saved = loadScope();
    if (saved) {
      setScope(saved);
      setIsConfigured(true);
      setScoped(!isEmptyScope(saved));
    }
    setReady(true);
  }, []);

  // Best-effort push of scope state to the backend. Two destinations, same call site:
  //   signed in  → /me/settings, keyed by uid (cross-device truth)
  //   signed out → /anon-scope, keyed by a browser-minted UUID (no account, no PII)
  // The anonymous branch exists because signed-out returning visitors are the largest and most
  // engaged cohort on the site, and gating personalization behind an account meant they told us
  // nothing about what they came for. See lib/anonScope.
  const persist = useCallback(
    async (next: { scope: Scope; isConfigured: boolean; scoped: boolean }) => {
      if (!user) {
        await postAnonScope({
          regions: next.scope.regions,
          states: next.scope.states,
          material_categories: next.scope.materials,
          configured: next.isConfigured,
          scoped: next.scoped,
        });
        return;
      }
      try {
        // PATCH merges server-side — only scope keys are touched, other features' keys survive.
        await patchSettings(await getToken(), {
          scope: next.scope,
          scopeConfigured: next.isConfigured,
          scoped: next.scoped,
        });
      } catch {
        /* personalization is best-effort */
      }
    },
    [user, getToken],
  );

  // On sign-in: adopt the account's saved scope (cross-device truth). If the account has none yet
  // but this device has a local scope, push the local one up so it follows the user.
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    (async () => {
      const prefs = await fetchSettings(await getToken());
      if (cancelled) return;
      const backendScope = prefs.scope as Partial<Scope> | undefined;
      if (
        backendScope &&
        Array.isArray(backendScope.states) &&
        Array.isArray(backendScope.materials)
      ) {
        // `regions` post-dates the stored blob, so an account saved before it is adopted as
        // region-less rather than rejected — normalizeScope then reads a states-only scope as US-only,
        // exactly as the localStorage path does. Signing in must not silently widen someone's scope.
        const adopted = normalizeScope({
          regions: Array.isArray(backendScope.regions) ? backendScope.regions : [],
          states: backendScope.states,
          materials: backendScope.materials,
        });
        setScope(adopted);
        setIsConfigured(Boolean(prefs.scopeConfigured));
        setScoped(prefs.scoped === undefined ? !isEmptyScope(adopted) : Boolean(prefs.scoped));
        saveScope(adopted);
      } else if (isConfigured) {
        persist({ scope, isConfigured, scoped });
      }
    })();
    return () => {
      cancelled = true;
    };
    // Only re-run when the signed-in user changes — we intentionally snapshot local state at sign-in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const saveAndClose = useCallback(
    (raw: Scope) => {
      // Normalize on the way in, so the stored scope and the live one can never disagree about
      // whether a states-only selection implies the US.
      const s = normalizeScope(raw);
      saveScope(s);
      setScope(s);
      setIsConfigured(true);
      setScoped(!isEmptyScope(s));
      setEditorOpen(false);
      persist({ scope: s, isConfigured: true, scoped: !isEmptyScope(s) });
    },
    [persist],
  );

  const skip = useCallback(() => {
    saveScope(EMPTY_SCOPE);
    setScope(EMPTY_SCOPE);
    setIsConfigured(true);
    setScoped(false);
    setEditorOpen(false);
    persist({ scope: EMPTY_SCOPE, isConfigured: true, scoped: false });
  }, [persist]);

  const reset = useCallback(() => {
    clearScope();
    setScope(EMPTY_SCOPE);
    setIsConfigured(false);
    setScoped(true);
    setEditorOpen(false);
    // Push the cleared state BEFORE dropping the anonymous id, so the existing row reads as
    // "reset" rather than being orphaned — then start a genuinely new identity. "Reset" has to
    // mean reset; leaving the id in place would quietly re-link the next scope to the old one.
    persist({ scope: EMPTY_SCOPE, isConfigured: false, scoped: true });
    if (!user) clearAnonId();
  }, [persist, user]);

  const setScopedPersist = useCallback(
    (v: boolean) => {
      setScoped(v);
      persist({ scope, isConfigured, scoped: v });
    },
    [persist, scope, isConfigured],
  );

  // Personalization is open to everyone. It used to prompt sign-in first, on the reasoning that a
  // scope should follow the reader across devices — but that gate was hit 3 times by 1 user in 28
  // days while 62 returning visitors browsed anonymously, so it converted nobody and cost us the one
  // signal those visitors were willing to give. Anonymous scope persists via /anon-scope; signing in
  // is now an upgrade (cross-device sync), not a toll gate.
  const openEditor = useCallback(() => {
    setEditorOpen(true);
  }, []);

  const value = useMemo<ScopeContextValue>(
    () => ({
      ready,
      scope,
      isConfigured,
      scoped,
      editorOpen,
      saveAndClose,
      skip,
      setScoped: setScopedPersist,
      openEditor,
      closeEditor: () => setEditorOpen(false),
      reset,
    }),
    [ready, scope, isConfigured, scoped, editorOpen, saveAndClose, skip, setScopedPersist, openEditor, reset],
  );

  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useScope() {
  return useContext(ScopeContext);
}

/** Convenience: the scope is "active" only when on AND non-empty. */
export function useScopeActive(): boolean {
  const { scoped, scope } = useScope();
  return scoped && !isEmptyScope(scope);
}
