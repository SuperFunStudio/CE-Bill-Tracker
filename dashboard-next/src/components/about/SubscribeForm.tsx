'use client';
import { useEffect, useState } from 'react';
import { subscribe } from '@/lib/api';
import { track } from '@/lib/analytics';
import { formatInstrumentType } from '@/lib/utils';
import { CheckIcon } from '@/components/ui/icons';
import { useScope } from '@/components/scope/ScopeContext';
import { MATERIAL_CATEGORIES, MultiSelect } from '@/components/bills/BillFilters';
import { jurisdictionsFor } from '@/lib/jurisdictions';
import { REGION_CODES, regionLabel } from '@/components/insights/RegionFilter';

// Policy "topics" a reader can follow — the tracked circular-economy instruments
// (see app/classification instrument_type enum). Order mirrors the About copy.
const TOPICS = ['epr', 'right_to_repair', 'deposit_return', 'recycled_content', 'labeling'] as const;

// Same slug→label transform used across the bills filters / scope onboarding.
const formatMaterial = (slug: string) =>
  slug.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

// The two anchor regions lead the jurisdiction list: US (which drills down to states) and the EU
// bloc (whole-region EU-wide directives — its member states are followable as their own regions in
// the same list). Everything else is national law we ingest as a single followable region.
const ANCHOR_REGIONS = ['US', 'EU'];
// Every other tracked jurisdiction, followed whole-region. Derived from REGION_CODES (the single
// source of truth for "which jurisdictions exist"), so new adapters appear here automatically.
const OTHER_REGIONS = REGION_CODES.filter(c => c !== 'US' && c !== 'EU');
// The full universe this form can build a subscription scope for.
const ALL_REGION_CODES = ['US', 'EU', ...OTHER_REGIONS];

type RegionSel = { included: boolean; all: boolean; codes: string[] };

// Sub-jurisdiction entries (code, name) for a region, excluding the whole-region sentinel (US/EU).
function subJurisdictions(region: string): [string, string][] {
  return Object.entries(jurisdictionsFor(region))
    .filter(([code]) => code !== region)
    .sort((a, b) => a[1].localeCompare(b[1]));
}

export interface SubscribeFormPrefill {
  /** US state codes to preselect (e.g. the Packaging Studio's chosen markets). */
  usStates?: string[];
  /** material_category slugs to preselect (e.g. the materials in a studio spec). */
  materials?: string[];
}

export function SubscribeForm({ prefill }: { prefill?: SubscribeFormPrefill } = {}) {
  const [email, setEmail] = useState('');
  const [organization, setOrganization] = useState('');
  const [topics, setTopics] = useState<string[]>([]);
  const [materials, setMaterials] = useState<string[]>([]);
  const [regionSel, setRegionSel] = useState<Record<string, RegionSel>>(() =>
    Object.fromEntries(
      ALL_REGION_CODES.map(code => [code, { included: code === 'US', all: true, codes: [] }]),
    ),
  );
  const [status, setStatus] = useState<'idle' | 'submitting' | 'done' | 'error'>('idle');
  const [error, setError] = useState('');

  // Prefill jurisdictions + materials from the reader's saved personalization scope (US states), so
  // "make this mine" → "alert me about exactly this" is one step. Both remain editable below.
  const { ready, scope } = useScope();
  const [prefilled, setPrefilled] = useState(false);
  useEffect(() => {
    if (prefilled) return;
    // Explicit prefill from the host page (e.g. the Packaging Studio spec) wins over the saved scope.
    if (prefill && ((prefill.usStates?.length ?? 0) > 0 || (prefill.materials?.length ?? 0) > 0)) {
      if (prefill.usStates?.length) {
        setRegionSel(prev => ({ ...prev, US: { included: true, all: false, codes: prefill.usStates! } }));
      }
      if (prefill.materials?.length) setMaterials(prefill.materials);
      setPrefilled(true);
      return;
    }
    if (ready && (scope.states.length > 0 || scope.materials.length > 0)) {
      if (scope.states.length > 0) {
        setRegionSel(prev => ({ ...prev, US: { included: true, all: false, codes: scope.states } }));
      }
      if (scope.materials.length > 0) setMaterials(scope.materials);
      setPrefilled(true);
    }
  }, [ready, prefilled, scope, prefill]);

  const patchRegion = (r: string, patch: Partial<RegionSel>) =>
    setRegionSel(prev => ({ ...prev, [r]: { ...prev[r], ...patch } }));
  const toggleCode = (r: string, code: string) =>
    setRegionSel(prev => {
      const codes = prev[r].codes;
      return {
        ...prev,
        [r]: { ...prev[r], codes: codes.includes(code) ? codes.filter(c => c !== code) : [...codes, code] },
      };
    });

  // Every tracked jurisdiction in ONE dropdown — US and the EU bloc lead, then the national regions —
  // so Topics / Materials / Jurisdictions fit on a single row. The dropdown works off a flat code
  // list; bridge it to the Record state. Picking the US reveals the state drill-down below the row
  // (US states are the only sub-jurisdiction level we ingest).
  const jurisdictionOptions = [
    ...ANCHOR_REGIONS.map(code => ({ value: code, label: regionLabel(code) })),
    ...OTHER_REGIONS.map(code => ({ value: code, label: regionLabel(code) })),
  ];
  const selectedJurisdictions = ALL_REGION_CODES.filter(c => regionSel[c]?.included);
  const setSelectedJurisdictions = (vals: string[]) =>
    setRegionSel(prev => {
      const next = { ...prev };
      for (const c of ALL_REGION_CODES) next[c] = { ...next[c], included: vals.includes(c) };
      return next;
    });
  const usSel = regionSel['US'];

  function buildRegionScope(): Record<string, string[]> {
    const scopeOut: Record<string, string[]> = {};
    for (const code of ALL_REGION_CODES) {
      const s = regionSel[code];
      if (!s?.included) continue;
      scopeOut[code] = s.all || s.codes.length === 0 ? ['*'] : s.codes;
    }
    return scopeOut;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus('submitting');
    setError('');
    try {
      const region_scope = buildRegionScope();
      await subscribe({
        email: email.trim(),
        organization: organization.trim() || undefined,
        // Empty region_scope means "every region" — friendliest default for a free digest.
        region_scope,
        instrument_types: topics.length === 0 ? ['ALL'] : topics,
        material_categories: materials.length === 0 ? ['ALL'] : materials,
      });
      track('subscribe', {
        topics_count: topics.length,
        materials_count: materials.length,
        regions_count: Object.keys(region_scope).length,
        has_organization: organization.trim().length > 0,
      });
      setStatus('done');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
      setStatus('error');
    }
  }

  if (status === 'done') {
    return (
      <div className="border border-green-accent/40 bg-green-dark/30 rounded-lg p-6 text-center space-y-2">
        <CheckIcon className="text-3xl mx-auto text-green-accent" />
        <p className="font-serif text-text-primary text-lg">You&apos;re on the list.</p>
        <p className="text-text-secondary text-body">
          We&apos;ll send updates to <span className="text-text-primary">{email}</span> as matching
          legislation moves. No charge, unsubscribe anytime.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* The three follow-facets share one row on desktop (stacked on mobile) — each is an
          empty-means-everything dropdown, so the whole subscription reads in a glance instead of
          three stacked blocks. */}
      <div className="grid gap-x-6 gap-y-4 sm:grid-cols-3">
        <MultiSelect
          label="Jurisdictions"
          values={selectedJurisdictions}
          onChange={setSelectedJurisdictions}
          options={jurisdictionOptions}
          placeholder="All jurisdictions"
        />
        <MultiSelect
          label="Materials & Products"
          values={materials}
          onChange={setMaterials}
          options={MATERIAL_CATEGORIES.map(m => ({ value: m, label: formatMaterial(m) }))}
          placeholder="All materials"
        />
        <MultiSelect
          label="Topics"
          values={topics}
          onChange={setTopics}
          options={TOPICS.map(t => ({ value: t, label: formatInstrumentType(t) }))}
          placeholder="All topics"
        />
      </div>
      <p className="text-text-muted text-xs">
        Leave a field unselected to follow everything in it.
        {regionSel['EU']?.included && ' The EU entry covers EU-wide measures — follow member states individually from the same list.'}
      </p>

      {/* US state drill-down — the one sub-jurisdiction level we ingest, so it opens under the row
          rather than living inside the dropdown. */}
      {usSel?.included && (
        <div className="rounded-md border border-border-default p-3">
          <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={usSel.all}
              onChange={e => patchRegion('US', { all: e.target.checked })}
              className="accent-green-accent"
            />
            All U.S. states &amp; D.C.
          </label>
          {!usSel.all && (
            <div className="mt-2">
              <div className="max-h-40 overflow-y-auto rounded-md border border-border-default bg-bg-secondary p-2 grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-1">
                {subJurisdictions('US').map(([jc, name]) => (
                  <label key={jc} className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer py-0.5">
                    <input
                      type="checkbox"
                      checked={usSel.codes.includes(jc)}
                      onChange={() => toggleCode('US', jc)}
                      className="accent-green-accent shrink-0"
                    />
                    <span className="truncate" title={name}>{name}</span>
                  </label>
                ))}
              </div>
              <p className="text-text-muted text-xs mt-1">
                {usSel.codes.length > 0 ? `${usSel.codes.length} selected` : 'Select one or more jurisdictions.'}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Email + organization share a row too — two short fields, one line. */}
      <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label
            htmlFor="subscribe-email"
            className="font-serif text-text-muted text-meta uppercase tracking-wider"
          >
            Email
          </label>
          <input
            id="subscribe-email"
            type="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="rounded-none border-0 border-b border-text-primary/30 bg-transparent px-0 py-1 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label
            htmlFor="subscribe-org"
            className="font-serif text-text-muted text-meta uppercase tracking-wider"
          >
            Organization <span className="normal-case tracking-normal text-text-muted/70">(optional)</span>
          </label>
          <input
            id="subscribe-org"
            type="text"
            value={organization}
            onChange={e => setOrganization(e.target.value)}
            placeholder="Company, agency, or association"
            className="rounded-none border-0 border-b border-text-primary/30 bg-transparent px-0 py-1 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
          />
        </div>
      </div>

      {status === 'error' && <p className="text-urgency-high text-body">{error}</p>}

      <button
        type="submit"
        disabled={status === 'submitting'}
        className="inline-flex items-center gap-2 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity disabled:opacity-60"
      >
        {status === 'submitting' ? 'Signing you up…' : 'Get free updates'}
      </button>
    </form>
  );
}
