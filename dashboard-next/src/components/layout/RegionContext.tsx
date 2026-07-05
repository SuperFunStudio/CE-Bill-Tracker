'use client';
import { createContext, useContext, useEffect, useState } from 'react';
import { EU_MEMBERS } from '@/lib/jurisdictions';

// Global jurisdiction filter. Multi-select now (US, EU, and any ingested country) — drives the bill
// list + insights for all pages. The map and compliance still operate on a single US/EU "primary",
// derived from the selection, since those views are inherently US-states / EU-members shaped.
export type RegionCode = 'US' | 'EU';

export interface RegionDef {
  code: RegionCode;
  label: string;
  /** Sub-jurisdiction noun, used in copy ("state" vs "member state"). */
  unit: string;
}

export const REGIONS: RegionDef[] = [
  { code: 'US', label: 'United States', unit: 'state' },
  { code: 'EU', label: 'European Union', unit: 'member state' },
];

export function regionDef(code: RegionCode): RegionDef {
  return REGIONS.find(r => r.code === code) ?? REGIONS[0];
}

// Derive the US/EU primary (for the map + compliance) from the multi-select: US wins; otherwise any
// EU-or-member selection maps to EU; anything else (or "all") defaults to US.
function primaryOf(regions: string[]): RegionCode {
  if (!regions.length || regions.includes('US')) return 'US';
  if (regions.includes('EU') || regions.some(r => r in EU_MEMBERS)) return 'EU';
  return 'US';
}

interface RegionCtx {
  regions: string[];                // selected codes; [] = all regions
  setRegions: (r: string[]) => void;
  regionsParam: string | undefined; // CSV for the API; undefined = all
  region: RegionCode;               // derived primary (US/EU) for single-region views
  /** Whether US-shaped UI should show (US-only nav items, the State filter, the states leaderboard).
   *  True on "All regions" (US is the flagship) and whenever US is in the selection — but NOT for a
   *  pure foreign selection (e.g. Japan alone), which previously fell through to the US primary and
   *  wrongly rendered the US nav + State dropdown + states ticker. */
  isUsView: boolean;
  def: RegionDef;
}

const RegionContext = createContext<RegionCtx>({
  regions: [],
  setRegions: () => {},
  regionsParam: undefined,
  region: 'US',
  isUsView: true,
  def: REGIONS[0],
});

export function RegionProvider({ children }: { children: React.ReactNode }) {
  const [regions, setRegionsState] = useState<string[]>([]);

  // Resolve initial selection: ?regions=US,EU query param wins (shareable links), else localStorage,
  // else [] (all). Back-compat: an old ?region=US / stored 'region' seeds a single-region selection.
  useEffect(() => {
    const url = new URLSearchParams(window.location.search);
    const raw =
      url.get('regions') ??
      url.get('region') ??
      localStorage.getItem('regions') ??
      localStorage.getItem('region') ??
      '';
    const parsed = raw.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
    if (parsed.length) setRegionsState(parsed);
  }, []);

  const setRegions = (r: string[]) => {
    setRegionsState(r);
    localStorage.setItem('regions', r.join(','));
  };

  const regionsParam = regions.length ? regions.join(',') : undefined;
  const region = primaryOf(regions);
  const isUsView = regions.length === 0 || regions.includes('US');

  return (
    <RegionContext.Provider value={{ regions, setRegions, regionsParam, region, isUsView, def: regionDef(region) }}>
      {children}
    </RegionContext.Provider>
  );
}

export function useRegion() {
  return useContext(RegionContext);
}
