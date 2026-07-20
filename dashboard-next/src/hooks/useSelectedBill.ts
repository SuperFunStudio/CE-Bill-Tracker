'use client';
import { useCallback, useEffect, useRef, useState } from 'react';

// Single source of truth for "which bill's detail modal is open", encoded in the ?bill= URL param.
// Both paths that open a bill — a table row click and an inbound deep link (emails, shared links,
// research citations) — flow through here, so the address bar always reflects the open bill: it's
// copyable/shareable, the Back button closes it, and a refresh restores it. Before this, a row click
// only set local React state (URL never changed) while the inbound ?bill= link was a separate,
// read-once code path with its own modal instance.

function readBillParam(): number | null {
  if (typeof window === 'undefined') return null;
  const raw = new URLSearchParams(window.location.search).get('bill');
  const id = raw ? parseInt(raw, 10) : NaN;
  return Number.isFinite(id) ? id : null;
}

function urlWithBill(id: number | null): string {
  const url = new URL(window.location.href);
  if (id === null) url.searchParams.delete('bill');
  else url.searchParams.set('bill', String(id));
  return url.pathname + url.search + url.hash;
}

export function useSelectedBill() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // Mirror of selectedId for synchronous reads inside openBill (avoids a stale closure and keeps the
  // history side effects out of the state updater, which would double-fire under StrictMode).
  const idRef = useRef<number | null>(null);

  // Hydrate from the URL on mount (inbound deep link / refresh) and follow Back/Forward via popstate.
  useEffect(() => {
    const sync = () => {
      const next = readBillParam();
      idRef.current = next;
      setSelectedId(next);
    };
    sync();
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);

  const openBill = useCallback((id: number) => {
    // A fresh open pushes a history entry so Back closes the modal; switching from one open bill to
    // another replaces it, so Back doesn't have to step through every bill you clicked.
    if (idRef.current === null) window.history.pushState({ billModal: id }, '', urlWithBill(id));
    else window.history.replaceState({ billModal: id }, '', urlWithBill(id));
    idRef.current = id;
    setSelectedId(id);
  }, []);

  const closeBill = useCallback(() => {
    if (window.history.state?.billModal != null) {
      // Our own pushed entry is on top — pop it so the close and the Back button stay consistent
      // (the popstate handler clears the state and URL).
      window.history.back();
    } else {
      // Inbound link with no entry of ours to pop: strip the param in place so a refresh won't reopen.
      window.history.replaceState(null, '', urlWithBill(null));
      idRef.current = null;
      setSelectedId(null);
    }
  }, []);

  return { selectedId, openBill, closeBill };
}
