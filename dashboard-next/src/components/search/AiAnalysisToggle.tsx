'use client';

/**
 * "AI Analysis" on/off switch that sits under the search bar. OFF (default) = classic keyword
 * filtering of the bill table; ON unlocks asking grounded, cited questions (Ask the Atlas) and
 * reveals the Ask button. State is owned + persisted by the parent (localStorage) — this is a
 * controlled presentational switch.
 */
export function AiAnalysisToggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      title={on ? 'AI Analysis on — ask questions for a cited answer' : 'AI Analysis off — keyword filtering'}
      className="group inline-flex shrink-0 items-center gap-2 select-none"
    >
      <span className={`text-sm font-medium transition-colors ${on ? 'text-green-accent' : 'text-text-secondary'}`}>
        AI Analysis
      </span>
      <span
        aria-hidden
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
          on ? 'bg-green-accent' : 'bg-bg-tertiary border border-border-default'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
            on ? 'translate-x-4' : 'translate-x-0.5'
          }`}
        />
      </span>
      <span className={`text-meta uppercase tracking-wider ${on ? 'text-green-accent' : 'text-text-muted'}`}>
        {on ? 'On' : 'Off'}
      </span>
    </button>
  );
}
