'use client';
import { useEffect, useRef, useState } from 'react';
import { STATE_NAMES, formatInstrumentType } from '@/lib/utils';
import { CheckIcon } from '@/components/ui/icons';

export interface BillFilterState {
  state: string;
  status: string;
  instrumentType: string;
  materialCategories: string[];
  urgency: string;
  search: string;
  eprOnly: boolean;
  enactedOnly: boolean;
  hasLitigation: boolean;
}

export const DEFAULT_FILTERS: BillFilterState = {
  state: '',
  status: '',
  instrumentType: '',
  materialCategories: [],
  urgency: '',
  search: '',
  eprOnly: true,
  enactedOnly: false,
  hasLitigation: false,
};

// Values must match the canonical statuses stored on bills (see app/ingestion/coordinator.py).
const STATUSES = [
  { value: 'introduced',     label: 'Introduced' },
  { value: 'in_committee',   label: 'In Committee' },
  { value: 'passed_chamber', label: 'Passed Chamber' },
  { value: 'passed',         label: 'Passed' },
  { value: 'enacted',        label: 'Enacted' },
  { value: 'vetoed',         label: 'Vetoed' },
  { value: 'failed',         label: 'Failed' },
];
// Values must match the classifier instrument_type enum (see app/classification/haiku_classifier.py).
// chemical_restriction and budget are omitted: neither is a tracked circular-economy instrument
// (see TRACKED_INSTRUMENTS); budget is generic appropriations and pulls in tangential bills.
// `incentives` IS surfaced: it's the financial lever (tax credits, grants, funding) for in-scope
// circular-economy outcomes, and supersedes the in-scope use of budget.
const INSTRUMENT_TYPES = ['epr', 'deposit_return', 'right_to_repair', 'recycled_content',
  'incentives', 'labeling', 'preemption', 'other'];
// Values must match the material categories in data/seed/epr_keywords.json.
// biobased / agriculture are the biological cycle of the circular economy (bio-based materials,
// regenerative ag & soil health); composting/organics-recycling bills tag "organics". These live
// on the material axis, not as policy instruments.
// Exported so the personalization onboarding (src/components/scope) shares one canonical list.
export const MATERIAL_CATEGORIES = ['plastic_packaging', 'paper_packaging', 'glass', 'metals',
  'electronics', 'batteries', 'paint', 'carpet', 'mattresses', 'tires',
  'pharmaceuticals', 'solar_panels', 'textiles', 'organics', 'biobased', 'agriculture', 'other'];
const URGENCY_LEVELS = ['high', 'medium', 'low'];

interface BillFiltersProps {
  filters: BillFilterState;
  onChange: (f: BillFilterState) => void;
  /** Omit the State select — for contexts where the state is already fixed (e.g. a state profile). */
  hideState?: boolean;
}

function Select({
  label, value, onChange, options, placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="font-serif text-text-muted text-[11px] uppercase tracking-wider">{label}</label>
      <div className="relative">
        <select
          value={value}
          onChange={e => onChange(e.target.value)}
          className="w-full appearance-none cursor-pointer rounded-none border-0 border-b border-text-primary/30 bg-transparent pl-0 pr-5 py-1 text-sm text-text-primary focus:outline-none focus:border-green-accent [&>option]:bg-bg-secondary [&>option]:text-text-primary"
        >
          <option value="">{placeholder}</option>
          {options.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <span className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 text-text-muted text-[10px]">▾</span>
      </div>
    </div>
  );
}

/** Checkbox popover styled to match the underline Selects — for filters that take several values. */
function MultiSelect({
  label, values, onChange, options, placeholder,
}: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  options: { value: string; label: string }[];
  placeholder: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click so the popover behaves like a native dropdown.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const toggle = (v: string) =>
    onChange(values.includes(v) ? values.filter(x => x !== v) : [...values, v]);

  const summary =
    values.length === 0
      ? placeholder
      : values.length === 1
        ? options.find(o => o.value === values[0])?.label ?? '1 selected'
        : `${values.length} selected`;

  return (
    <div className="flex flex-col gap-1" ref={ref}>
      <label className="font-serif text-text-muted text-[11px] uppercase tracking-wider">{label}</label>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="w-full flex items-center cursor-pointer rounded-none border-0 border-b border-text-primary/30 bg-transparent pl-0 pr-5 py-1 text-sm text-left focus:outline-none focus:border-green-accent"
        >
          <span className={`truncate ${values.length ? 'text-text-primary' : 'text-text-muted'}`}>{summary}</span>
        </button>
        <span className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 text-text-muted text-[10px]">▾</span>
        {open && (
          <div className="absolute left-0 z-30 mt-1 w-max min-w-full max-h-60 overflow-y-auto rounded-md border border-border-default bg-bg-secondary shadow-lg p-1">
            {options.map(o => {
              const on = values.includes(o.value);
              return (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => toggle(o.value)}
                  className={`w-full flex items-center gap-2 rounded px-2 py-1.5 text-sm text-left whitespace-nowrap hover:bg-bg-primary ${
                    on ? 'text-green-accent' : 'text-text-secondary'
                  }`}
                >
                  <span
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                      on ? 'border-green-accent bg-green-dark' : 'border-border-default'
                    }`}
                  >
                    {on && <CheckIcon className="text-[10px]" />}
                  </span>
                  {o.label}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export function BillFilters({ filters, onChange, hideState }: BillFiltersProps) {
  const set = (partial: Partial<BillFilterState>) => onChange({ ...filters, ...partial });
  // On a fixed-state context, reset preserves the locked state instead of clearing it.
  const reset = () => onChange(hideState ? { ...DEFAULT_FILTERS, state: filters.state } : DEFAULT_FILTERS);

  const stateOptions = Object.entries(STATE_NAMES).map(([abbr, name]) => ({
    value: abbr,
    label: `${abbr} — ${name}`,
  }));

  return (
    <div className="space-y-4 border-y border-text-primary/15 py-4">
      {/* Search */}
      <div className="flex flex-col gap-1">
        <label className="font-serif text-text-muted text-[11px] uppercase tracking-wider">Search</label>
        <div className="relative">
          <input
            type="text"
            value={filters.search}
            onChange={e => set({ search: e.target.value })}
            placeholder="Search title, summary…"
            className="w-full rounded-none border-0 border-b border-text-primary/30 bg-transparent px-0 py-1 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent pr-8"
          />
          {filters.search && (
            <button
              onClick={() => set({ search: '' })}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary text-sm leading-none"
              aria-label="Clear search"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Filter row */}
      <div className={`grid grid-cols-2 gap-3 ${hideState ? 'md:grid-cols-3' : 'md:grid-cols-4'}`}>
        {!hideState && (
          <Select
            label="State"
            value={filters.state}
            onChange={v => set({ state: v })}
            options={stateOptions}
            placeholder="All States"
          />
        )}
        <Select
          label="Status"
          value={filters.status}
          onChange={v => set({ status: v })}
          options={STATUSES}
          placeholder="All Statuses"
        />
        <Select
          label="Instrument"
          value={filters.instrumentType}
          onChange={v => set({ instrumentType: v })}
          options={INSTRUMENT_TYPES.map(t => ({
            value: t,
            label: formatInstrumentType(t),
          }))}
          placeholder="All Types"
        />
        <MultiSelect
          label="Materials & Products"
          values={filters.materialCategories}
          onChange={v => set({ materialCategories: v })}
          options={MATERIAL_CATEGORIES.map(m => ({
            value: m,
            label: m.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
          }))}
          placeholder="All"
        />
      </div>

      {/* Reset */}
      <div className="flex justify-end">
        <button
          onClick={reset}
          className="text-green-accent text-xs hover:underline"
        >
          Reset filters
        </button>
      </div>
    </div>
  );
}

/** Apply BillFilterState to a bill list client-side */
import type { BillSummary } from '@/lib/types';
import { fixEncoding } from '@/lib/utils';

export function applyBillFilters(bills: BillSummary[], f: BillFilterState): BillSummary[] {
  return bills.filter(b => {
    if (f.eprOnly && !b.epr_relevant) return false;
    if (f.enactedOnly && b.status?.toLowerCase() !== 'enacted') return false;
    if (f.state && b.state !== f.state) return false;
    if (f.status && b.status?.toLowerCase() !== f.status.toLowerCase()) return false;
    if (f.instrumentType && b.instrument_type !== f.instrumentType) return false;
    if (f.urgency && b.urgency?.toLowerCase() !== f.urgency.toLowerCase()) return false;
    if (f.materialCategories.length &&
        !f.materialCategories.some(m => (b.material_categories ?? []).includes(m))) return false;
    if (f.hasLitigation && !(b.litigation_case_count > 0)) return false;
    if (f.search) {
      const q = f.search.toLowerCase();
      const title = fixEncoding(b.title).toLowerCase();
      const summary = fixEncoding(b.ai_summary).toLowerCase();
      if (!title.includes(q) && !summary.includes(q) && !b.bill_number?.toLowerCase().includes(q)) {
        return false;
      }
    }
    return true;
  });
}
