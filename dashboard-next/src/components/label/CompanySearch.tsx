'use client';
import { useEffect, useRef, useState } from 'react';
import { searchCompanies } from '@/lib/label';
import type { CompanySummary } from '@/lib/types';

/**
 * Debounced type-ahead against GET /companies?search=&limit=8 (ported from compliance-cliff).
 * Keyboard: arrows to move, Enter to pick the highlighted (or first) hit, Escape to dismiss.
 */
export function CompanySearch({
  onPick,
  disabled,
}: {
  onPick: (company: CompanySummary) => void;
  disabled?: boolean;
}) {
  const [term, setTerm] = useState('');
  const [hits, setHits] = useState<CompanySummary[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const [searching, setSearching] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef(0);

  // Debounced search; a sequence counter drops stale responses that resolve out of order.
  useEffect(() => {
    const q = term.trim();
    if (q.length < 2) {
      setHits([]);
      setOpen(false);
      return;
    }
    const seq = ++seqRef.current;
    const t = setTimeout(async () => {
      setSearching(true);
      try {
        const list = await searchCompanies(q, 8);
        if (seq !== seqRef.current) return;
        setHits(list);
        setActiveIdx(-1);
        setOpen(list.length > 0);
      } catch {
        if (seq === seqRef.current) setOpen(false);
      } finally {
        if (seq === seqRef.current) setSearching(false);
      }
    }, 200);
    return () => clearTimeout(t);
  }, [term]);

  // Dismiss on outside click.
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, []);

  function pick(c: CompanySummary) {
    setTerm(c.name);
    setOpen(false);
    onPick(c);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx(i => Math.min(i + 1, hits.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const hit = hits[activeIdx >= 0 ? activeIdx : 0];
      if (hit) pick(hit);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  }

  return (
    <div ref={wrapRef} className="relative">
      <input
        type="text"
        value={term}
        disabled={disabled}
        onChange={e => setTerm(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => hits.length > 0 && setOpen(true)}
        placeholder="Search a company… e.g. Amazon, PepsiCo"
        autoComplete="off"
        className="w-full px-3 py-2.5 text-sm bg-bg-primary border border-border-default rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-green-accent/40 focus:border-green-accent"
        aria-label="Search companies"
      />
      {searching && (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-text-muted">…</span>
      )}
      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 z-20 bg-bg-secondary border border-border-default rounded-lg shadow-panel overflow-hidden">
          {hits.map((c, i) => (
            <button
              key={c.id}
              type="button"
              onClick={() => pick(c)}
              className={`w-full flex justify-between items-center gap-3 text-left px-3 py-2.5 text-sm border-b border-border-default last:border-b-0 hover:bg-bg-primary/60 ${
                i === activeIdx ? 'bg-bg-primary/60' : ''
              }`}
            >
              <span className="text-text-primary truncate">{c.name}</span>
              <span className="text-text-muted text-xs whitespace-nowrap shrink-0">
                {[c.hq_state, c.operating_states?.length ? `${c.operating_states.length} states` : null]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
