'use client';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Scope, EMPTY_SCOPE, isEmptyScope, loadScope, saveScope, clearScope } from '@/lib/scope';
import { useAuth } from '@/components/auth/AuthContext';
import { fetchSettings, patchSettings } from '@/lib/userSettings';

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
  const { user, getToken, openAuth } = useAuth();
  const [ready, setReady] = useState(false);
  const [scope, setScope] = useState<Scope>(EMPTY_SCOPE);
  const [isConfigured, setIsConfigured] = useState(false);
  const [scoped, setScoped] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);
  // Set when a signed-out reader taps "Personalize"; we prompt sign-in and open the editor once they're in.
  const [pendingEditor, setPendingEditor] = useState(false);

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

  // Best-effort push of scope state to the backend (cross-device persistence) when signed in.
  const persist = useCallback(
    async (next: { scope: Scope; isConfigured: boolean; scoped: boolean }) => {
      if (!user) return;
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
      const backendScope = prefs.scope as Scope | undefined;
      if (
        backendScope &&
        Array.isArray(backendScope.states) &&
        Array.isArray(backendScope.materials)
      ) {
        setScope(backendScope);
        setIsConfigured(Boolean(prefs.scopeConfigured));
        setScoped(
          prefs.scoped === undefined ? !isEmptyScope(backendScope) : Boolean(prefs.scoped),
        );
        saveScope(backendScope);
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
    (s: Scope) => {
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
    persist({ scope: EMPTY_SCOPE, isConfigured: false, scoped: true });
  }, [persist]);

  const setScopedPersist = useCallback(
    (v: boolean) => {
      setScoped(v);
      persist({ scope, isConfigured, scoped: v });
    },
    [persist, scope, isConfigured],
  );

  // Personalization requires a (free) account — the scope follows the reader across devices, so it
  // can't live for anonymous visitors. A signed-out tap prompts sign-in and defers opening the editor.
  const openEditor = useCallback(() => {
    if (!user) {
      setPendingEditor(true);
      openAuth();
      return;
    }
    setEditorOpen(true);
  }, [user, openAuth]);

  // Once the deferred sign-in lands, open the editor we held back.
  useEffect(() => {
    if (user && pendingEditor) {
      setPendingEditor(false);
      setEditorOpen(true);
    }
  }, [user, pendingEditor]);

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
