'use client';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Scope, EMPTY_SCOPE, isEmptyScope, loadScope, saveScope, clearScope } from '@/lib/scope';

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
  const [ready, setReady] = useState(false);
  const [scope, setScope] = useState<Scope>(EMPTY_SCOPE);
  const [isConfigured, setIsConfigured] = useState(false);
  const [scoped, setScoped] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);

  useEffect(() => {
    const saved = loadScope();
    if (saved) {
      setScope(saved);
      setIsConfigured(true);
      setScoped(!isEmptyScope(saved));
    }
    setReady(true);
  }, []);

  const saveAndClose = useCallback((s: Scope) => {
    saveScope(s);
    setScope(s);
    setIsConfigured(true);
    setScoped(!isEmptyScope(s));
    setEditorOpen(false);
  }, []);

  const skip = useCallback(() => {
    saveScope(EMPTY_SCOPE);
    setScope(EMPTY_SCOPE);
    setIsConfigured(true);
    setScoped(false);
    setEditorOpen(false);
  }, []);

  const reset = useCallback(() => {
    clearScope();
    setScope(EMPTY_SCOPE);
    setIsConfigured(false);
    setScoped(true);
    setEditorOpen(false);
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
      setScoped,
      openEditor: () => setEditorOpen(true),
      closeEditor: () => setEditorOpen(false),
      reset,
    }),
    [ready, scope, isConfigured, scoped, editorOpen, saveAndClose, skip, reset],
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
