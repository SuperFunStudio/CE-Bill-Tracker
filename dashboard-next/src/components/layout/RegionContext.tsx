'use client';
import { createContext, useContext, useEffect, useState } from 'react';

// Global jurisdiction-family selector. Drives which region's law the whole app shows (server query +
// map + nav + filters). Mirrors the backend `region` seam (US default, EU now; more later).
export type RegionCode = 'US' | 'EU';

export interface RegionDef {
  code: RegionCode;
  label: string;
  /** Masthead subtitle fragment, e.g. "across the USA". */
  blurb: string;
  /** Sub-jurisdiction noun, used in copy ("state" vs "member state"). */
  unit: string;
}

export const REGIONS: RegionDef[] = [
  { code: 'US', label: 'United States', blurb: 'across the USA', unit: 'state' },
  { code: 'EU', label: 'European Union', blurb: 'across the EU', unit: 'member state' },
];

export function regionDef(code: RegionCode): RegionDef {
  return REGIONS.find(r => r.code === code) ?? REGIONS[0];
}

const RegionContext = createContext<{
  region: RegionCode;
  setRegion: (r: RegionCode) => void;
  def: RegionDef;
}>({ region: 'US', setRegion: () => {}, def: REGIONS[0] });

function isRegion(v: string | null): v is RegionCode {
  return v === 'US' || v === 'EU';
}

export function RegionProvider({ children }: { children: React.ReactNode }) {
  const [region, setRegionState] = useState<RegionCode>('US');

  // Resolve initial region: ?region= query param wins (shareable links), else localStorage, else US.
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('region')?.toUpperCase() ?? null;
    const stored = localStorage.getItem('region');
    const resolved = isRegion(fromUrl) ? fromUrl : isRegion(stored) ? stored : 'US';
    setRegionState(resolved);
  }, []);

  const setRegion = (r: RegionCode) => {
    setRegionState(r);
    localStorage.setItem('region', r);
  };

  return (
    <RegionContext.Provider value={{ region, setRegion, def: regionDef(region) }}>
      {children}
    </RegionContext.Provider>
  );
}

export function useRegion() {
  return useContext(RegionContext);
}
