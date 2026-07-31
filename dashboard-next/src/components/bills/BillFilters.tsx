'use client';
import { useEffect, useRef, useState } from 'react';
import { STATE_NAMES, formatInstrumentType } from '@/lib/utils';
import { CheckIcon, CloseIcon } from '@/components/ui/icons';
import { useRegion } from '@/components/layout/RegionContext';
import { RegionFilter } from '@/components/insights/RegionFilter';

export interface BillFilterState {
  state: string;
  status: string;
  instrumentType: string;
  materialCategories: string[];
  polymers: string[];
  /** Compliance-dimension keys that must be `present` (filtered server-side; see _DIMENSION_KEYS). */
  dimensions: string[];
  urgency: string;
  search: string;
  /** "search by date" (§9). '' = no date filter. 'effective' ranges the extracted compliance date;
   *  'activity' ranges the most-recent-action date (coalesce last_action_date, status_date). */
  dateType: '' | 'effective' | 'activity';
  /** Inclusive ISO (YYYY-MM-DD) bounds; '' = unbounded on that end. */
  dateFrom: string;
  dateTo: string;
  eprOnly: boolean;
  enactedOnly: boolean;
  hasLitigation: boolean;
}

export const DEFAULT_FILTERS: BillFilterState = {
  state: '',
  status: '',
  instrumentType: '',
  materialCategories: [],
  polymers: [],
  dimensions: [],
  urgency: '',
  search: '',
  dateType: '',
  dateFrom: '',
  dateTo: '',
  eprOnly: true,
  enactedOnly: false,
  hasLitigation: false,
};

// The eight extracted compliance dimensions, filterable from the bills list. Keys mirror the envelope
// keys in compliance_details (app/classification/sonnet_extractor.py) + the backend _DIMENSION_KEYS.
export const COMPLIANCE_DIMENSIONS: { value: string; label: string }[] = [
  { value: 'collection_targets', label: 'Collection / recovery targets' },
  { value: 'recycled_content', label: 'Recycled-content minimums' },
  { value: 'eco_modulation', label: 'Eco-modulation' },
  { value: 'fee_amounts', label: 'Producer fees' },
  { value: 'penalties', label: 'Penalties' },
  { value: 'bans_restrictions', label: 'Bans & restrictions' },
  { value: 'pro_structure', label: 'PRO structure' },
  { value: 'labeling', label: 'Labeling' },
];

// Example search terms cycled through the placeholder — one bill number, one material, one topic.
// Search matches bill_number, title, and ai_summary (see applyBillFilters below).
const SEARCH_EXAMPLES = ['SB 707', 'HDPE', 'solar'];

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
  'incentives', 'labeling', 'preemption', 'disposal_ban', 'organics_diversion', 'other'];
// Values must match the material categories in data/seed/epr_keywords.json.
// biobased / agriculture are the biological cycle of the circular economy (bio-based materials,
// regenerative ag & soil health); composting/organics-recycling bills tag "organics". These live
// on the material axis, not as policy instruments.
// Exported so the personalization onboarding (src/components/scope) shares one canonical list.
export const MATERIAL_CATEGORIES = ['plastic_packaging', 'paper_packaging', 'glass', 'metals',
  'electronics', 'batteries', 'paint', 'carpet', 'mattresses', 'tires',
  'pharmaceuticals', 'solar_panels', 'textiles', 'organics', 'biobased', 'agriculture',
  'water', 'biodiversity', 'other'];
const URGENCY_LEVELS = ['high', 'medium', 'low'];
// Resin code → display name. Mirrors the controlled vocabulary in app/classification/polymers.py;
// codes are written to bills.polymers by scripts/scan_bill_polymers.py. The filter only offers the
// resins actually present in the loaded bills (passed via resinOptions), so this is just for labels.
const RESIN_NAMES: Record<string, string> = {
  PET: 'PET — Polyethylene terephthalate',
  HDPE: 'HDPE — High-density polyethylene',
  PVC: 'PVC — Polyvinyl chloride',
  LDPE: 'LDPE — Low-density polyethylene',
  PP: 'PP — Polypropylene',
  PS: 'PS — Polystyrene',
  PLA: 'PLA — Polylactic acid',
  PC: 'PC — Polycarbonate',
  ABS: 'ABS — Acrylonitrile butadiene styrene',
  EVA: 'EVA — Ethylene-vinyl acetate',
  PUR: 'PUR — Polyurethane',
  PA: 'PA — Polyamide / nylon',
  PE: 'PE — Polyethylene',
};

interface BillFiltersProps {
  filters: BillFilterState;
  onChange: (f: BillFilterState) => void;
  /** Omit the State select — for contexts where the state is already fixed (e.g. a state profile). */
  hideState?: boolean;
  /** Omit the Search input — for the unified Explore surface, which owns a prominent adaptive
   *  search/ask bar above the facets and drives `filters.search` itself. */
  hideSearch?: boolean;
  /** Render the jurisdiction (Regions) selector centered at the top of the filter box. On the home
   *  page this folds the old site-wide GlobalRegionBar into the explorer's own filter set, so the
   *  region control sits with the facets it governs instead of floating under the nav. */
  showRegion?: boolean;
  /** Resin codes present in the current bill set. When non-empty, a "Resin / polymer" filter appears;
      derive with `resinOptionsFromBills(bills)`. Omitted/empty → the filter is hidden (e.g. before the
      polymer scan has populated any data), so no surface shows a dead control. */
  resinOptions?: string[];
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
      <label className="font-serif text-text-muted text-meta uppercase tracking-wider">{label}</label>
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
        <span className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 text-text-muted text-meta">▾</span>
      </div>
    </div>
  );
}

/** Checkbox popover styled to match the underline Selects — for filters that take several values.
 *  Exported so other surfaces (e.g. the subscribe form) get the same tickable-dropdown affordance. */
export function MultiSelect({
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
    // Escape closes the popover, matching the native <select> it mimics.
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
      <label className="font-serif text-text-muted text-meta uppercase tracking-wider">{label}</label>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          aria-haspopup="listbox"
          aria-expanded={open}
          className="w-full flex items-center cursor-pointer rounded-none border-0 border-b border-text-primary/30 bg-transparent pl-0 pr-5 py-1 text-sm text-left focus:border-green-accent"
        >
          <span className={`truncate ${values.length ? 'text-text-primary' : 'text-text-muted'}`}>{summary}</span>
        </button>
        <span className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 text-text-muted text-meta">▾</span>
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
                    {on && <CheckIcon className="text-meta" />}
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

/** A single date bound, styled to match the underline Selects. Native date picker for zero deps. */
function DateInput({
  label, value, onChange,
}: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="font-serif text-text-muted text-meta uppercase tracking-wider">{label}</label>
      <input
        type="date"
        value={value}
        onChange={e => onChange(e.target.value)}
        className="appearance-none cursor-pointer rounded-none border-0 border-b border-text-primary/30 bg-transparent px-0 py-1 text-sm text-text-primary focus:outline-none focus:border-green-accent [color-scheme:light] dark:[color-scheme:dark]"
      />
    </div>
  );
}

/** "Search by date" (§9): a date-type select + from/to bounds, revealed once a type is chosen. Occupies
 *  its own row (col-span-full) so it doesn't disturb the surrounding filter grid's column math. */
function DateFilter({
  dateType, dateFrom, dateTo, onChange,
}: {
  dateType: BillFilterState['dateType'];
  dateFrom: string;
  dateTo: string;
  onChange: (patch: Partial<BillFilterState>) => void;
}) {
  return (
    <div className="col-span-full flex flex-wrap items-end gap-x-4 gap-y-2">
      <div className="min-w-[12rem]">
        <Select
          label="Date filter"
          value={dateType}
          onChange={v =>
            // Clearing the type clears the bounds too, so an empty date filter can't linger.
            onChange(v ? { dateType: v as BillFilterState['dateType'] } : { dateType: '', dateFrom: '', dateTo: '' })
          }
          options={[
            { value: 'effective', label: 'Effective / compliance date' },
            { value: 'activity', label: 'Legislative activity date' },
          ]}
          placeholder="No date filter"
        />
      </div>
      {dateType && (
        <>
          <DateInput label="From" value={dateFrom} onChange={v => onChange({ dateFrom: v })} />
          <DateInput label="To" value={dateTo} onChange={v => onChange({ dateTo: v })} />
        </>
      )}
    </div>
  );
}

export function BillFilters({ filters, onChange, hideState, hideSearch, showRegion, resinOptions }: BillFiltersProps) {
  const set = (partial: Partial<BillFilterState>) => onChange({ ...filters, ...partial });

  // EU-central law is EU-wide (no sub-jurisdiction yet), so the State select is hidden in EU mode —
  // it returns with member-state national law (Phase B). Region itself is the global nav selector,
  // but when `showRegion` is set the selector is hosted here (regions/setRegions come from the same
  // RegionContext, so it stays in sync with the rest of the site).
  const { isUsView, regions, setRegions } = useRegion();
  const showState = !hideState && isUsView;

  // Rotate example terms through the placeholder to hint what's searchable (bill #, material, topic).
  const [exampleIdx, setExampleIdx] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setExampleIdx(i => (i + 1) % SEARCH_EXAMPLES.length), 2500);
    return () => clearInterval(id);
  }, []);

  // Home-explorer (showRegion) layout keeps Region + State up front and folds the rest behind a
  // "More filters" toggle. Start expanded only if one of those secondary filters is already active,
  // so a filtered arrival isn't hidden.
  const secondaryActiveCount = [
    filters.status,
    filters.instrumentType,
    filters.materialCategories.length > 0,
    filters.dimensions.length > 0,
    filters.polymers.length > 0,
    filters.dateType,
  ].filter(Boolean).length;
  const [showMore, setShowMore] = useState(secondaryActiveCount > 0);
  // On a fixed-state context, reset preserves the locked state instead of clearing it.
  const reset = () => onChange(hideState ? { ...DEFAULT_FILTERS, state: filters.state } : DEFAULT_FILTERS);

  // The resin filter only appears once the polymer scan has tagged bills (resinOptions non-empty),
  // so no surface shows a control that can only return nothing.
  const showResin = (resinOptions?.length ?? 0) > 0;

  // Count active filters so Reset signals there's something to undo (and disables when clean).
  const activeCount = [
    showState && filters.state,
    filters.status,
    filters.instrumentType,
    filters.materialCategories.length > 0,
    filters.polymers.length > 0,
    filters.dimensions.length > 0,
    filters.dateType,
    filters.search,
  ].filter(Boolean).length;

  const stateOptions = Object.entries(STATE_NAMES).map(([abbr, name]) => ({
    value: abbr,
    label: `${abbr} — ${name}`,
  }));

  // The Status / Instrument / Materials / Compliance / Resin controls — shared between the default
  // grid and the collapsible "More filters" panel of the home-explorer layout.
  const secondaryFields = (
    <>
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
        options={INSTRUMENT_TYPES.map(t => ({ value: t, label: formatInstrumentType(t) }))}
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
      <MultiSelect
        label="Compliance"
        values={filters.dimensions}
        onChange={v => set({ dimensions: v })}
        options={COMPLIANCE_DIMENSIONS}
        placeholder="Any"
      />
      {showResin && (
        <MultiSelect
          label="Resin / Polymer"
          values={filters.polymers}
          onChange={v => set({ polymers: v })}
          options={resinOptions!.map(code => ({ value: code, label: RESIN_NAMES[code] ?? code }))}
          placeholder="Any"
        />
      )}
      <DateFilter
        dateType={filters.dateType}
        dateFrom={filters.dateFrom}
        dateTo={filters.dateTo}
        onChange={patch => set(patch)}
      />
    </>
  );

  // Home-explorer layout: Region + State (US) always visible; the rest fold behind "More filters" so
  // the bar stays calm above the ask box.
  if (showRegion) {
    return (
      <div className="space-y-3 border-y border-text-primary/15 py-4">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <RegionFilter selected={regions} onChange={setRegions} />
          {showState && (
            <div className="min-w-[9rem]">
              <Select
                label="State"
                value={filters.state}
                onChange={v => set({ state: v })}
                options={stateOptions}
                placeholder="All States"
              />
            </div>
          )}
          <button
            type="button"
            onClick={() => setShowMore(v => !v)}
            aria-expanded={showMore}
            className="flex items-center gap-1.5 pb-1 text-left transition-colors group"
          >
            <span className="font-serif text-text-muted group-hover:text-text-primary text-meta uppercase tracking-wider">More filters</span>
            {secondaryActiveCount > 0 && (
              <span className="rounded-full bg-green-dark/40 text-green-accent text-[10px] leading-none px-1.5 py-0.5">{secondaryActiveCount}</span>
            )}
            <span className={`text-text-muted text-meta transition-transform ${showMore ? 'rotate-180' : ''}`}>▾</span>
          </button>
          {(activeCount > 0 || regions.length > 0) && (
            <button
              // Reset clears the facets AND the region selection — the region lives here now, so its
              // reset belongs on this bar too (there's no global region bar on the home page).
              onClick={() => { reset(); if (regions.length) setRegions([]); }}
              className="ml-auto self-end rounded-full border border-border-default px-3 py-1 text-meta text-text-secondary transition-colors hover:border-text-primary/40 hover:text-text-primary"
            >
              Reset ({activeCount + (regions.length > 0 ? 1 : 0)})
            </button>
          )}
        </div>

        {/* Secondary controls — revealed on demand. */}
        {showMore && (
          <div className={`grid grid-cols-2 gap-3 pt-1 ${showResin ? 'md:grid-cols-5' : 'md:grid-cols-4'}`}>
            {secondaryFields}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4 border-y border-text-primary/15 py-4">
      {/* Search — omitted on the unified Explore surface, which hosts the adaptive search/ask bar. */}
      {!hideSearch && (
        <div className="flex flex-col gap-1">
          <label className="font-serif text-text-muted text-meta uppercase tracking-wider">Search</label>
          <div className="relative">
            <input
              type="text"
              value={filters.search}
              onChange={e => set({ search: e.target.value })}
              placeholder={`Search e.g. ${SEARCH_EXAMPLES[exampleIdx]}`}
              className="w-full rounded-none border-0 border-b border-text-primary/30 bg-transparent px-0 py-1 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent pr-8"
            />
            {filters.search && (
              <button
                onClick={() => set({ search: '' })}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary text-sm leading-none"
                aria-label="Clear search"
              >
                <CloseIcon />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Filter row. Column count tracks how many controls render: State (US only) + Status +
          Instrument + Materials, plus Resin when the polymer scan has data. */}
      <div className={`grid grid-cols-2 gap-3 ${
        { 4: 'md:grid-cols-4', 5: 'md:grid-cols-5', 6: 'md:grid-cols-6' }[
          (showState ? 5 : 4) + (showResin ? 1 : 0)
        ]
      }`}>
        {showState && (
          <Select
            label="State"
            value={filters.state}
            onChange={v => set({ state: v })}
            options={stateOptions}
            placeholder="All States"
          />
        )}
        {secondaryFields}
      </div>

      {/* Reset. (eprOnly — circular-economy relevance — is the product's fixed editorial scope, applied
          by applyBillFilters but not surfaced as a control. enactedOnly/hasLitigation/urgency are also
          enforced if set, but have no UI yet: enacted-only is redundant with the Status select, and the
          litigation filter is held back until active-litigation tracking is wired up.) */}
      <div className="flex justify-end">
        <button
          onClick={reset}
          disabled={activeCount === 0}
          className="rounded-full border border-border-default px-3 py-1 text-meta text-text-secondary transition-colors hover:border-text-primary/40 hover:text-text-primary disabled:opacity-40 disabled:hover:border-border-default disabled:hover:text-text-secondary"
        >
          Reset{activeCount ? ` (${activeCount})` : ''}
        </button>
      </div>
    </div>
  );
}

/** Apply BillFilterState to a bill list client-side */
import type { BillSummary } from '@/lib/types';
import { fixEncoding } from '@/lib/utils';

/** Granularity of a bill's activity date. Prefers the server's date_precision; falls back to deriving
 *  it (older/snapshot rows may lack the field): a Jan-1 status_date with no last_action_date is the
 *  year-only foreign placeholder. Exported so a row renderer can qualify such dates as "YYYY (year)". */
export function billDatePrecision(b: BillSummary): 'day' | 'year' {
  if (b.date_precision === 'day' || b.date_precision === 'year') return b.date_precision;
  if (b.last_action_date) return 'day';
  const sd = b.status_date ?? '';
  return sd.slice(5) === '01-01' ? 'year' : 'day';
}

export function applyBillFilters(bills: BillSummary[], f: BillFilterState): BillSummary[] {
  return bills.filter(b => {
    if (f.eprOnly && !b.ce_relevant) return false;
    if (f.enactedOnly && b.status?.toLowerCase() !== 'enacted') return false;
    if (f.state && b.state !== f.state) return false;
    if (f.status && b.status?.toLowerCase() !== f.status.toLowerCase()) return false;
    // Match the instrument anywhere in the law's set (primary + secondary), not just the primary.
    if (f.instrumentType && !(b.instrument_types ?? (b.instrument_type ? [b.instrument_type] : [])).includes(f.instrumentType)) return false;
    if (f.urgency && b.urgency?.toLowerCase() !== f.urgency.toLowerCase()) return false;
    if (f.materialCategories.length &&
        !f.materialCategories.some(m => (b.material_categories ?? []).includes(m))) return false;
    // Resin filter: keep bills naming ANY of the selected resins (OR), mirroring material categories.
    if (f.polymers.length &&
        !f.polymers.some(p => (b.polymers ?? []).includes(p))) return false;
    // Search by date (§9). ISO YYYY-MM-DD strings compare lexicographically, so string < / > is a
    // correct date comparison. Mirrors the server-side §9b semantics for parity.
    if (f.dateType && (f.dateFrom || f.dateTo)) {
      if (f.dateType === 'effective') {
        const d = b.effective_date;                 // day-precise, or null when not extracted
        if (!d) return false;
        if (f.dateFrom && d < f.dateFrom) return false;
        if (f.dateTo && d > f.dateTo) return false;
      } else {
        // Activity date: coalesce(last_action_date, status_date). Year-only rows match on year overlap
        // so a mid-year range still includes a bill dated only to that year.
        const activity = b.last_action_date ?? b.status_date ?? null;
        if (!activity) return false;
        if (billDatePrecision(b) === 'year') {
          const y = (b.status_date ?? '').slice(0, 4);
          if (f.dateFrom && y < f.dateFrom.slice(0, 4)) return false;
          if (f.dateTo && y > f.dateTo.slice(0, 4)) return false;
        } else {
          if (f.dateFrom && activity < f.dateFrom) return false;
          if (f.dateTo && activity > f.dateTo) return false;
        }
      }
    }
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

/** Distinct resin codes present across a bill set, ordered by the canonical RESIN_NAMES list, for
 *  feeding BillFilters' `resinOptions`. Empty when no bill carries polymers (pre-scan) → filter hidden. */
export function resinOptionsFromBills(bills: BillSummary[]): string[] {
  const present = new Set<string>();
  for (const b of bills) for (const code of b.polymers ?? []) present.add(code);
  return Object.keys(RESIN_NAMES).filter(code => present.has(code));
}
