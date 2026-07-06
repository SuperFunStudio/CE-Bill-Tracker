'use client';

/**
 * A small on/off control for the coverage heatmaps' "Enacted bills only" filter. Defaults on in the
 * charts that use it: US regions carry a large introduced-bill pipeline that would otherwise dwarf
 * foreign/EU jurisdictions we track only once they're law, so counting enacted-only compares regions
 * on the same footing. Toggle off to fold the full introduced→enacted pipeline back in.
 */
export function EnactedOnlyToggle({
  enactedOnly,
  onChange,
}: {
  enactedOnly: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        role="switch"
        aria-checked={enactedOnly}
        onClick={() => onChange(!enactedOnly)}
        className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
          enactedOnly ? 'bg-[rgb(var(--green-accent))]' : 'bg-bg-tertiary'
        }`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
            enactedOnly ? 'translate-x-4' : 'translate-x-1'
          }`}
        />
      </button>
      <label
        className="cursor-pointer select-none text-xs text-text-secondary"
        onClick={() => onChange(!enactedOnly)}
      >
        Enacted bills only
        <span className="ml-1 text-text-muted">
          {enactedOnly ? '— excludes introduced bills' : '— including introduced'}
        </span>
      </label>
    </div>
  );
}
