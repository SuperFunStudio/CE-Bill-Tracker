'use client';
import { STATE_NAMES, formatInstrumentType } from '@/lib/utils';

export interface BillFilterState {
  state: string;
  status: string;
  instrumentType: string;
  materialCategory: string;
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
  materialCategory: '',
  urgency: '',
  search: '',
  eprOnly: true,
  enactedOnly: false,
  hasLitigation: false,
};

const STATUSES = ['Introduced', 'In Committee', 'Passed Chamber', 'Enacted', 'Failed', 'Tabled'];
const INSTRUMENT_TYPES = ['epr', 'bottle_bill', 'recycled_content', 'right_to_repair', 'other'];
const MATERIAL_CATEGORIES = [
  'packaging', 'electronics', 'batteries', 'paint', 'mattresses',
  'carpet', 'pharmaceuticals', 'motor_oil', 'tires', 'sharps',
];
const URGENCY_LEVELS = ['high', 'medium', 'low'];

interface BillFiltersProps {
  filters: BillFilterState;
  onChange: (f: BillFilterState) => void;
  showEprToggle?: boolean;
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
      <label className="text-text-muted text-xs uppercase">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="bg-bg-secondary border border-border-default rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-green-accent"
      >
        <option value="">{placeholder}</option>
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

export function BillFilters({ filters, onChange, showEprToggle = false }: BillFiltersProps) {
  const set = (partial: Partial<BillFilterState>) => onChange({ ...filters, ...partial });

  const stateOptions = Object.entries(STATE_NAMES).map(([abbr, name]) => ({
    value: abbr,
    label: `${abbr} — ${name}`,
  }));

  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg p-4 space-y-4">
      {/* Search */}
      <div className="flex flex-col gap-1">
        <label className="text-text-muted text-xs uppercase">Search</label>
        <div className="relative">
          <input
            type="text"
            value={filters.search}
            onChange={e => set({ search: e.target.value })}
            placeholder="Search title, summary..."
            className="w-full bg-bg-primary border border-border-default rounded px-3 py-1.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent pr-8"
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Select
          label="State"
          value={filters.state}
          onChange={v => set({ state: v })}
          options={stateOptions}
          placeholder="All States"
        />
        <Select
          label="Status"
          value={filters.status}
          onChange={v => set({ status: v })}
          options={STATUSES.map(s => ({ value: s, label: s }))}
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
        <Select
          label="Material"
          value={filters.materialCategory}
          onChange={v => set({ materialCategory: v })}
          options={MATERIAL_CATEGORIES.map(m => ({
            value: m,
            label: m.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
          }))}
          placeholder="All Materials"
        />
      </div>

      {/* Toggles */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={filters.enactedOnly}
            onChange={e => set({ enactedOnly: e.target.checked })}
            className="accent-green-accent"
          />
          Enacted only
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={filters.hasLitigation}
            onChange={e => set({ hasLitigation: e.target.checked })}
            className="accent-green-accent"
          />
          Active litigation only
        </label>
        {showEprToggle && (
          <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary">
            <input
              type="checkbox"
              checked={filters.eprOnly}
              onChange={e => set({ eprOnly: e.target.checked })}
              className="accent-green-accent"
            />
            EPR-relevant only
          </label>
        )}
        <button
          onClick={() => onChange(DEFAULT_FILTERS)}
          className="text-green-accent text-xs hover:underline sm:ml-auto"
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
    if (f.materialCategory && !(b.material_categories ?? []).includes(f.materialCategory)) return false;
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
