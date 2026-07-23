'use client';

import { useEffect, useRef, useState } from 'react';
import { EU_MEMBERS } from '@/lib/jurisdictions';

/**
 * Insights region filter — a multi-select popover styled like the BillFilters materials/topics
 * MultiSelect: pick one or more jurisdictions, or leave empty for "All regions". Drives the
 * `regions` CSV param on the region-generalizable Insights views (timeline / momentum / coverage).
 *
 * Empty selection = All (aggregate every region). One or more = scope to those, aggregated.
 */

// Non-EU-member region labels; EU member states resolve via EU_MEMBERS. Keep roughly in sync with
// the backend ingest adapters (app/jurisdictions.py) — an unknown code degrades to the bare code.
const NON_EU_LABELS: Record<string, string> = {
  US: 'United States',
  EU: 'European Union',
  UK: 'United Kingdom',
  JP: 'Japan',
  CL: 'Chile',
  BR: 'Brazil',
  CH: 'Switzerland',
  NO: 'Norway',
  KR: 'South Korea',
  CN: 'China',
  CA: 'Canada',
  AU: 'Australia',
  IN: 'India',
};

export function regionLabel(code: string): string {
  return NON_EU_LABELS[code] ?? EU_MEMBERS[code] ?? code;
}

// Display order: the two anchors (US, EU-central) first, then the rest alphabetical by label.
const ANCHORS = ['US', 'EU'];
const REST = [
  'UK', 'FR', 'DE', 'JP', 'PL', 'SE', 'NL', 'ES', 'FI', 'IE', 'DK',
  'CL', 'CH', 'SI', 'BR', 'AT', 'LU', 'LV', 'SK', 'LT', 'CZ', 'EE',
  'CN', 'CA', 'AU', 'IN',
].sort((a, b) => regionLabel(a).localeCompare(regionLabel(b)));
const REGION_CODES = [...ANCHORS, ...REST];

export function RegionFilter({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (codes: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const toggle = (code: string) =>
    onChange(selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code]);

  const summary =
    selected.length === 0
      ? 'All regions'
      : selected.length === 1
        ? regionLabel(selected[0])
        : `${selected.length} regions`;

  return (
    <div className="flex flex-row items-center gap-2" ref={ref}>
      <label className="font-serif text-text-muted text-meta uppercase tracking-wider shrink-0">Regions</label>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-haspopup="listbox"
          aria-expanded={open}
          className="w-full min-w-[10rem] flex items-center cursor-pointer rounded-none border-0 border-b border-text-primary/30 bg-transparent pl-0 pr-5 py-1 text-sm text-left focus:border-green-accent"
        >
          <span className={`truncate ${selected.length ? 'text-text-primary' : 'text-text-muted'}`}>
            {summary}
          </span>
        </button>
        <span className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 text-text-muted text-meta">▾</span>
        {open && (
          <div className="absolute left-0 z-30 mt-1 w-max min-w-full max-h-72 overflow-y-auto rounded-md border border-border-default bg-bg-secondary shadow-lg p-1">
            {/* "All regions" reset row — clears the selection (= aggregate everything). */}
            <button
              type="button"
              onClick={() => onChange([])}
              className={`w-full flex items-center gap-2 rounded px-2 py-1.5 text-sm text-left whitespace-nowrap hover:bg-bg-primary ${
                selected.length === 0 ? 'text-green-accent' : 'text-text-secondary'
              }`}
            >
              <span
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px] ${
                  selected.length === 0 ? 'border-green-accent bg-green-dark text-white' : 'border-border-default'
                }`}
              >
                {selected.length === 0 ? '✓' : ''}
              </span>
              All regions
            </button>
            <div className="my-1 border-t border-border-default" />
            {REGION_CODES.map((code) => {
              const on = selected.includes(code);
              return (
                <button
                  key={code}
                  type="button"
                  onClick={() => toggle(code)}
                  className={`w-full flex items-center gap-2 rounded px-2 py-1.5 text-sm text-left whitespace-nowrap hover:bg-bg-primary ${
                    on ? 'text-green-accent' : 'text-text-secondary'
                  }`}
                >
                  <span
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px] ${
                      on ? 'border-green-accent bg-green-dark text-white' : 'border-border-default'
                    }`}
                  >
                    {on ? '✓' : ''}
                  </span>
                  {regionLabel(code)}
                  <span className="ml-1 text-text-muted text-[10px]">{code}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/** Selected region codes -> the `regions` CSV param (undefined = All / no filter). */
export function regionsParam(selected: string[]): string | undefined {
  return selected.length ? selected.join(',') : undefined;
}
