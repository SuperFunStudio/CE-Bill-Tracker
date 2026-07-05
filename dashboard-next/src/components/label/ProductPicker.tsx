'use client';
import { MATERIAL_CATEGORIES } from '@/components/bills/BillFilters';
import { formatMaterial } from '@/components/scope/ScopeOnboarding';
import { STATE_NAMES } from '@/lib/utils';

// The canonical material vocabulary (shared with BillFilters + scope onboarding), minus the
// catch-all bucket — "other" isn't a meaningful product ingredient.
export const LABEL_MATERIALS = MATERIAL_CATEGORIES.filter(m => m !== 'other');

// EPR-active states first (the demo sweet spot), then the regions with data.
export const FEATURED_MARKETS: { code: string; kind: 'state' | 'region' }[] = [
  { code: 'CA', kind: 'state' },
  { code: 'CO', kind: 'state' },
  { code: 'OR', kind: 'state' },
  { code: 'ME', kind: 'state' },
  { code: 'WA', kind: 'state' },
  { code: 'MN', kind: 'state' },
  { code: 'MD', kind: 'state' },
  { code: 'TX', kind: 'state' },
  { code: 'EU', kind: 'region' },
  { code: 'FR', kind: 'region' },
  { code: 'JP', kind: 'region' },
];

export const REGION_CODES = new Set(FEATURED_MARKETS.filter(m => m.kind === 'region').map(m => m.code));

function Chip({
  label,
  on,
  accent,
  onToggle,
}: {
  label: string;
  on: boolean;
  accent?: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={on}
      className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
        on
          ? accent
            ? 'bg-green-accent text-white border-green-accent'
            : 'bg-text-primary text-bg-primary border-text-primary'
          : 'bg-bg-primary text-text-secondary border-border-default hover:border-text-muted'
      }`}
    >
      {label}
    </button>
  );
}

/**
 * Product-mode inputs: material "ingredients" checkbox-chips + market chips (US states and
 * EU/FR/JP region chips) + an add-a-state select for the long tail of states.
 */
export function ProductPicker({
  materials,
  markets,
  onToggleMaterial,
  onToggleMarket,
  onAddState,
}: {
  materials: Set<string>;
  /** Selected market codes; regions are distinguished by REGION_CODES membership. */
  markets: Set<string>;
  onToggleMaterial: (m: string) => void;
  onToggleMarket: (code: string) => void;
  onAddState: (code: string) => void;
}) {
  // Featured chips plus any extra states the user added via the select.
  const extraStates = [...markets].filter(c => !FEATURED_MARKETS.some(f => f.code === c));
  const chips = [
    ...FEATURED_MARKETS,
    ...extraStates.map(code => ({ code, kind: 'state' as const })),
  ];
  const remainingStates = Object.keys(STATE_NAMES).filter(
    s => !chips.some(c => c.code === s),
  );

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs uppercase tracking-wider text-text-muted font-semibold mb-2">
          Materials (&ldquo;ingredients&rdquo;)
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {LABEL_MATERIALS.map(m => (
            <Chip
              key={m}
              label={formatMaterial(m)}
              on={materials.has(m)}
              onToggle={() => onToggleMaterial(m)}
            />
          ))}
        </div>
        <p className="text-xs text-text-muted mt-1.5">
          Leave all unchecked to match every material.
        </p>
      </div>

      <div>
        <h3 className="text-xs uppercase tracking-wider text-text-muted font-semibold mb-2">
          Target markets
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {chips.map(c => (
            <Chip
              key={c.code}
              label={c.code}
              on={markets.has(c.code)}
              accent={c.kind === 'region'}
              onToggle={() => onToggleMarket(c.code)}
            />
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-text-muted mt-2">
          Add another state:
          <select
            value=""
            onChange={e => e.target.value && onAddState(e.target.value)}
            className="px-2 py-1 text-xs bg-bg-primary border border-border-default rounded text-text-primary"
          >
            <option value="">— pick —</option>
            {remainingStates.map(s => (
              <option key={s} value={s}>
                {s} — {STATE_NAMES[s]}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
