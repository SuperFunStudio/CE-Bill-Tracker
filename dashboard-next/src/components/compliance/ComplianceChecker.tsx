'use client';
import { useMemo, useState } from 'react';
import { useRegion } from '@/components/layout/RegionContext';
import { useRegionPathways } from '@/hooks/useCompliancePathways';
import { MATERIAL_CATEGORIES } from '@/components/bills/BillFilters';
import { PathwayCard } from './PathwayCard';
import { SkeletonList } from '@/components/ui/SkeletonList';

const matLabel = (m: string) => m.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

// Actionable next-steps first (register/join/file/report), passive ones (monitor/none) last.
const ACTION_ORDER: Record<string, number> = {
  register_with_state: 0, join_pro: 0, file_individual_plan: 0, pay_into_program: 0,
  arrange_collection: 1, report_to_program: 1, monitor: 2, none: 3,
};

/**
 * Self-serve "which laws apply to me?" view. The producer picks what they make; we show the enacted
 * laws in the current region (top-nav selector) whose covered materials overlap, each with its
 * concrete next step + deadline. Region-generic — works for US and EU off the same pathways data.
 */
export function ComplianceChecker() {
  const { region, def } = useRegion();
  const [materials, setMaterials] = useState<string[]>([]);
  const { data: pathways = [], isLoading } = useRegionPathways(region);

  const toggle = (m: string) =>
    setMaterials(prev => (prev.includes(m) ? prev.filter(x => x !== m) : [...prev, m]));

  const matches = useMemo(() => {
    const filtered = materials.length
      ? pathways.filter(p => (p.material_categories ?? []).some(m => materials.includes(m)))
      : pathways;
    return [...filtered].sort((a, b) => {
      const ord = (ACTION_ORDER[a.action_type ?? 'none'] ?? 3) - (ACTION_ORDER[b.action_type ?? 'none'] ?? 3);
      if (ord !== 0) return ord;
      // soonest real deadline first within an action tier
      const da = a.next_deadline_date ?? '9999';
      const db = b.next_deadline_date ?? '9999';
      return da < db ? -1 : da > db ? 1 : 0;
    });
  }, [pathways, materials]);

  return (
    <section className="rounded-xl border border-border-default bg-bg-tertiary/30 p-5">
      <h2 className="font-serif text-2xl text-text-primary">Does this apply to my products?</h2>
      <p className="text-text-secondary text-sm mt-1">
        Pick what you make to see the enacted <span className="text-text-primary">{def.label}</span> laws
        that cover it and your next step. Switch region in the filter bar above.
      </p>

      {/* Material picker */}
      <div className="mt-4 flex flex-wrap gap-1.5">
        {MATERIAL_CATEGORIES.map(m => {
          const on = materials.includes(m);
          return (
            <button
              key={m}
              type="button"
              onClick={() => toggle(m)}
              className={`rounded-full border px-2.5 py-1 text-meta transition-colors ${
                on
                  ? 'border-green-accent bg-green-dark text-green-accent'
                  : 'border-border-default text-text-secondary hover:border-text-primary/40 hover:text-text-primary'
              }`}
            >
              {matLabel(m)}
            </button>
          );
        })}
        {materials.length > 0 && (
          <button
            type="button"
            onClick={() => setMaterials([])}
            className="rounded-full px-2.5 py-1 text-meta text-text-muted hover:text-text-primary underline"
          >
            clear
          </button>
        )}
      </div>

      {/* Results */}
      <div className="mt-4">
        {isLoading ? (
          <SkeletonList rows={3} />
        ) : matches.length === 0 ? (
          <p className="text-text-muted text-sm py-6 text-center">
            {pathways.length === 0
              ? `No enacted ${def.label} laws with a mapped compliance pathway yet.`
              : 'No laws match those materials — try a broader selection.'}
          </p>
        ) : (
          <>
            <div className="text-text-muted text-meta uppercase tracking-wider mb-2">
              {matches.length} {matches.length === 1 ? 'law applies' : 'laws apply'}
              {materials.length > 0 && ` to ${materials.map(matLabel).join(', ')}`}
            </div>
            <ul className="space-y-2.5">
              {matches.map(p => (
                <PathwayCard key={p.bill_id} p={p} />
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
