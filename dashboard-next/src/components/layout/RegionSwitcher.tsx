'use client';
import { useEffect, useRef, useState } from 'react';
import { useRegion, REGIONS, type RegionCode } from './RegionContext';

/** Global region selector for the top nav. Dropdown (scales to more regions than a toggle); switching
 *  reshapes the whole app — server query, map, nav, filters — via RegionContext. */
export function RegionSwitcher() {
  const { region, setRegion, def } = useRegion();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const pick = (code: RegionCode) => { setRegion(code); setOpen(false); };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-full border border-border-default px-3 py-1 font-serif text-sm text-text-secondary hover:border-text-primary/40 hover:text-text-primary transition-colors"
      >
        <span className="text-text-muted text-meta uppercase tracking-wider">Region</span>
        <span className="text-text-primary">{def.label}</span>
        <span className="text-text-muted text-meta">▾</span>
      </button>
      {open && (
        <div
          role="listbox"
          className="absolute left-0 z-50 mt-1 w-max min-w-full rounded-md border border-border-default bg-bg-secondary shadow-lg p-1"
        >
          {REGIONS.map(r => (
            <button
              key={r.code}
              type="button"
              role="option"
              aria-selected={r.code === region}
              onClick={() => pick(r.code)}
              className={`w-full flex items-center gap-2 rounded px-3 py-1.5 text-sm text-left whitespace-nowrap hover:bg-bg-primary ${
                r.code === region ? 'text-green-accent' : 'text-text-secondary'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
