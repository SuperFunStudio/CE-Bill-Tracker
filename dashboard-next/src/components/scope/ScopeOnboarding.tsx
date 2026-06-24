'use client';
import { useEffect, useMemo, useState } from 'react';
import { STATE_NAMES } from '@/lib/utils';
import { MATERIAL_CATEGORIES } from '@/components/bills/BillFilters';
import { CheckIcon } from '@/components/ui/icons';
import { useScope } from './ScopeContext';
import { EMPTY_SCOPE, type Scope } from '@/lib/scope';

export function formatMaterial(slug: string): string {
  return slug.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

const STATE_ENTRIES = Object.entries(STATE_NAMES).sort((a, b) => a[1].localeCompare(b[1]));

/**
 * First-visit modal that asks the one question the whole front door pivots on: which states and
 * materials matter to you? Saving defaults every surface to that scope (loss aversion bites hardest
 * when the loss is *mine*). It also opens on demand from the ScopeBar's "Edit". Skipping is allowed
 * but framed as opting *into* the firehose, not as the default. It never auto-opens — readers reach
 * it on demand via the ScopeBar's "Personalize your feed" / "Edit" affordances.
 */
export function ScopeOnboarding() {
  const { ready, isConfigured, editorOpen, scope, saveAndClose, skip, closeEditor } = useScope();
  const open = ready && editorOpen;
  const editing = isConfigured; // opened via "Edit" rather than the first-run invitation

  const [states, setStates] = useState<string[]>([]);
  const [materials, setMaterials] = useState<string[]>([]);

  // Seed the draft from the current scope whenever the modal opens.
  useEffect(() => {
    if (open) {
      setStates(scope.states);
      setMaterials(scope.materials);
    }
  }, [open, scope]);

  const draft: Scope = useMemo(() => ({ states, materials }), [states, materials]);

  if (!open) return null;

  const toggle = (list: string[], set: (v: string[]) => void, v: string) =>
    set(list.includes(v) ? list.filter(x => x !== v) : [...list, v]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="scope-onboarding-title"
      onClick={editing ? closeEditor : skip}
    >
      <div
        className="w-full max-w-lg max-h-[90dvh] flex flex-col rounded-t-2xl sm:rounded-xl bg-bg-secondary border border-border-default shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Scrollable body — keeps the footer CTA pinned and visible on short screens. */}
        <div className="overflow-y-auto p-4 sm:p-6 space-y-4 sm:space-y-5">
        <div className="space-y-1">
          <h2 id="scope-onboarding-title" className="font-serif text-xl sm:text-2xl text-text-primary">
            See what&apos;s coming for you.
          </h2>
          <p className="text-text-secondary text-body leading-relaxed">
            Pick your products, materials &amp; states once. We&apos;ll surface the bills and
            deadlines that hit your portfolio — and skip the ones that don&apos;t.
          </p>
        </div>

        {/* Materials */}
        <fieldset>
          <legend className="font-serif text-text-muted text-meta uppercase tracking-wider mb-2">
            Materials &amp; Products
          </legend>
          <div className="flex flex-wrap gap-2">
            {MATERIAL_CATEGORIES.map(m => {
              const on = materials.includes(m);
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => toggle(materials, setMaterials, m)}
                  aria-pressed={on}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors ${
                    on
                      ? 'border-green-accent bg-green-dark text-green-accent'
                      : 'border-border-default text-text-secondary hover:border-green-accent/40 hover:text-text-primary'
                  }`}
                >
                  {on && <CheckIcon className="text-xs" />}
                  {formatMaterial(m)}
                </button>
              );
            })}
          </div>
        </fieldset>

        {/* States */}
        <fieldset>
          <legend className="font-serif text-text-muted text-meta uppercase tracking-wider mb-2">
            States
          </legend>
          <div className="max-h-44 overflow-y-auto rounded-md border border-border-default bg-bg-primary p-2 grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1">
            {STATE_ENTRIES.map(([abbr, name]) => (
              <label
                key={abbr}
                className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer py-0.5"
              >
                <input
                  type="checkbox"
                  checked={states.includes(abbr)}
                  onChange={() => toggle(states, setStates, abbr)}
                  className="accent-green-accent shrink-0"
                />
                <span className="truncate" title={name}>{name}</span>
              </label>
            ))}
          </div>
          <p className="text-text-muted text-xs mt-1">
            {states.length > 0 ? `${states.length} selected` : 'Leave empty to follow every state.'}
          </p>
        </fieldset>
        </div>

        <div className="shrink-0 flex items-center justify-between gap-3 border-t border-border-default p-4 sm:px-6">
          <button
            type="button"
            onClick={editing ? closeEditor : skip}
            className="text-sm text-text-muted hover:text-text-secondary"
          >
            {editing ? 'Cancel' : 'Prefer the full national view? Skip →'}
          </button>
          <div className="flex items-center gap-3">
            {editing && (
              <button
                type="button"
                onClick={() => saveAndClose(EMPTY_SCOPE)}
                className="text-sm text-text-muted hover:text-text-secondary"
              >
                Clear scope
              </button>
            )}
            <button
              type="button"
              onClick={() => saveAndClose(draft)}
              className="inline-flex items-center gap-2 rounded-lg border border-green-accent bg-green-dark px-5 py-2 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
            >
              Show my exposure →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
