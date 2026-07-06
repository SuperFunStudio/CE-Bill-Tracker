'use client';
import { createContext, useContext, useEffect, useState } from 'react';

/**
 * Beta-features opt-in. A per-browser preference (localStorage) gating still-in-testing tools like the
 * Packaging Studio's CI export. New users are opted OUT by default; the toggle lives on /account.
 *
 * Not a security boundary — it only reveals preview UI, so a client-side flag is appropriate. Starts
 * `false` so the first client render matches the (window-less) server render; the stored value is read
 * in an effect after mount, so opting in never causes a hydration mismatch.
 */
const KEY = 'beta_features_enabled';

interface BetaCtx {
  betaEnabled: boolean;
  setBetaEnabled: (v: boolean) => void;
}

const Ctx = createContext<BetaCtx>({ betaEnabled: false, setBetaEnabled: () => {} });

export function BetaProvider({ children }: { children: React.ReactNode }) {
  const [betaEnabled, setEnabled] = useState(false);

  useEffect(() => {
    try {
      setEnabled(localStorage.getItem(KEY) === '1');
    } catch {
      /* private mode / storage blocked — stay opted out */
    }
  }, []);

  const setBetaEnabled = (v: boolean) => {
    setEnabled(v);
    try {
      localStorage.setItem(KEY, v ? '1' : '0');
    } catch {
      /* ignore */
    }
  };

  return <Ctx.Provider value={{ betaEnabled, setBetaEnabled }}>{children}</Ctx.Provider>;
}

export const useBeta = () => useContext(Ctx);
