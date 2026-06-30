'use client';
import { useEffect, useState } from 'react';
import { subscribe } from '@/lib/api';
import { track } from '@/lib/analytics';
import { formatInstrumentType } from '@/lib/utils';
import { CheckIcon } from '@/components/ui/icons';
import { useScope } from '@/components/scope/ScopeContext';
import { MATERIAL_CATEGORIES } from '@/components/bills/BillFilters';
import { REGION_LABELS, jurisdictionsFor } from '@/lib/jurisdictions';

// Policy "topics" a reader can follow — the tracked circular-economy instruments
// (see app/classification instrument_type enum). Order mirrors the About copy.
const TOPICS = ['epr', 'right_to_repair', 'deposit_return', 'recycled_content', 'labeling'] as const;

// Same slug→label transform used across the bills filters / scope onboarding.
const formatMaterial = (slug: string) =>
  slug.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

// Regions a subscriber can follow. `hasSub` = the region has selectable sub-jurisdictions today
// (US states). EU member-state selection arrives with Phase B national law, so EU is whole-region
// for now; new regions (UK, …) flip hasSub on once their jurisdiction data lands.
const SUB_REGIONS: { code: string; hasSub: boolean }[] = [
  { code: 'US', hasSub: true },
  { code: 'EU', hasSub: false },
];

type RegionSel = { included: boolean; all: boolean; codes: string[] };

// Sub-jurisdiction entries (code, name) for a region, excluding the whole-region sentinel (US/EU).
function subJurisdictions(region: string): [string, string][] {
  return Object.entries(jurisdictionsFor(region))
    .filter(([code]) => code !== region)
    .sort((a, b) => a[1].localeCompare(b[1]));
}

export function SubscribeForm() {
  const [email, setEmail] = useState('');
  const [organization, setOrganization] = useState('');
  const [topics, setTopics] = useState<string[]>([]);
  const [materials, setMaterials] = useState<string[]>([]);
  const [regionSel, setRegionSel] = useState<Record<string, RegionSel>>({
    US: { included: true, all: true, codes: [] },
    EU: { included: false, all: true, codes: [] },
  });
  const [status, setStatus] = useState<'idle' | 'submitting' | 'done' | 'error'>('idle');
  const [error, setError] = useState('');

  // Prefill jurisdictions + materials from the reader's saved personalization scope (US states), so
  // "make this mine" → "alert me about exactly this" is one step. Both remain editable below.
  const { ready, scope } = useScope();
  const [prefilled, setPrefilled] = useState(false);
  useEffect(() => {
    if (ready && !prefilled && (scope.states.length > 0 || scope.materials.length > 0)) {
      if (scope.states.length > 0) {
        setRegionSel(prev => ({ ...prev, US: { included: true, all: false, codes: scope.states } }));
      }
      if (scope.materials.length > 0) setMaterials(scope.materials);
      setPrefilled(true);
    }
  }, [ready, prefilled, scope]);

  const toggleTopic = (t: string) =>
    setTopics(prev => (prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]));
  const toggleMaterial = (m: string) =>
    setMaterials(prev => (prev.includes(m) ? prev.filter(x => x !== m) : [...prev, m]));

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

  function buildRegionScope(): Record<string, string[]> {
    const scopeOut: Record<string, string[]> = {};
    for (const { code } of SUB_REGIONS) {
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
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Topics */}
      <fieldset>
        <legend className="font-serif text-text-muted text-meta uppercase tracking-wider mb-2">
          Topics
        </legend>
        <div className="flex flex-wrap gap-2">
          {TOPICS.map(t => {
            const on = topics.includes(t);
            return (
              <button
                key={t}
                type="button"
                onClick={() => toggleTopic(t)}
                aria-pressed={on}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors ${
                  on
                    ? 'border-green-accent bg-green-dark text-green-accent'
                    : 'border-border-default text-text-secondary hover:border-green-accent/40 hover:text-text-primary'
                }`}
              >
                {on && <CheckIcon className="text-xs" />}
                {formatInstrumentType(t)}
              </button>
            );
          })}
        </div>
        <p className="text-text-muted text-xs mt-2">Leave all unselected to follow every topic.</p>
      </fieldset>

      {/* Materials & Products */}
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
                onClick={() => toggleMaterial(m)}
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
        <p className="text-text-muted text-xs mt-2">Leave all unselected to follow every material.</p>
      </fieldset>

      {/* Regions & jurisdictions */}
      <fieldset>
        <legend className="font-serif text-text-muted text-meta uppercase tracking-wider mb-2">
          Regions &amp; jurisdictions
        </legend>
        <div className="space-y-3">
          {SUB_REGIONS.map(({ code, hasSub }) => {
            const sel = regionSel[code];
            const label = REGION_LABELS[code] ?? code;
            return (
              <div key={code} className="rounded-md border border-border-default p-3">
                <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={sel.included}
                    onChange={e => patchRegion(code, { included: e.target.checked })}
                    className="accent-green-accent"
                  />
                  <span className="font-serif">{label}</span>
                </label>

                {sel.included && hasSub && (
                  <div className="mt-2 pl-6">
                    <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
                      <input
                        type="checkbox"
                        checked={sel.all}
                        onChange={e => patchRegion(code, { all: e.target.checked })}
                        className="accent-green-accent"
                      />
                      All {label} jurisdictions
                    </label>
                    {!sel.all && (
                      <div className="mt-2">
                        <div className="max-h-48 overflow-y-auto rounded-md border border-border-default bg-bg-secondary p-2 grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1">
                          {subJurisdictions(code).map(([jc, name]) => (
                            <label key={jc} className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer py-0.5">
                              <input
                                type="checkbox"
                                checked={sel.codes.includes(jc)}
                                onChange={() => toggleCode(code, jc)}
                                className="accent-green-accent shrink-0"
                              />
                              <span className="truncate" title={name}>{name}</span>
                            </label>
                          ))}
                        </div>
                        <p className="text-text-muted text-xs mt-1">
                          {sel.codes.length > 0 ? `${sel.codes.length} selected` : 'Select one or more jurisdictions.'}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {sel.included && !hasSub && (
                  <p className="mt-1 pl-6 text-text-muted text-xs">
                    EU-wide measures now; member-state coverage is coming.
                  </p>
                )}
              </div>
            );
          })}
        </div>
        <p className="text-text-muted text-xs mt-2">Uncheck all regions to follow everything.</p>
      </fieldset>

      {/* Email */}
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

      {/* Organization (optional) */}
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
