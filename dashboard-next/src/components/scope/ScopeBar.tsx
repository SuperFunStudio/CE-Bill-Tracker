'use client';
import { usePathname } from 'next/navigation';
import { STATE_NAMES } from '@/lib/utils';
import { isEmptyScope } from '@/lib/scope';
import { useScope } from './ScopeContext';
import { formatMaterial } from './ScopeOnboarding';

function summarize(values: string[], label: (v: string) => string, all: string): string {
  if (values.length === 0) return all;
  if (values.length <= 3) return values.map(label).join(', ');
  return `${values.slice(0, 2).map(label).join(', ')} +${values.length - 2}`;
}

/**
 * Persistent strip under the masthead announcing the active personalization scope, with one-tap
 * controls to edit it or fall back to the full feed. The "Show everything" affordance is the
 * deliberate opt-out — relevance is the default, the firehose is the choice.
 */
export function ScopeBar() {
  const { ready, scope, scoped, setScoped, openEditor } = useScope();
  const pathname = usePathname();
  if (!ready) return null;

  // No active scope (never personalized, or skipped): a quiet, persistent invitation, and the entry
  // point on every page where the modal no longer auto-opens. The home page is the exception — its
  // ScopedDeadlineBanner carries the single "personalize" CTA (with deadline urgency baked in), so we
  // suppress this redundant strip there rather than show two buttons opening the same modal.
  if (isEmptyScope(scope)) {
    if (pathname === '/') return null;
    return (
      <div className="border-b border-border-default bg-bg-secondary/60">
        <div className="max-w-6xl mx-auto px-4 py-1.5 text-center text-xs text-text-muted">
          Showing every state, material &amp; product.{' '}
          <button onClick={openEditor} className="text-green-accent hover:underline">
            Personalize your feed →
          </button>
        </div>
      </div>
    );
  }

  const states = summarize(scope.states, a => STATE_NAMES[a] ?? a, 'all states');
  const materials = summarize(scope.materials, formatMaterial, 'all materials & products');

  return (
    <div className="border-b border-border-default bg-bg-secondary/60">
      <div className="max-w-6xl mx-auto px-4 py-1.5 flex items-center justify-center gap-x-3 gap-y-1 flex-wrap text-xs">
        <span className="text-text-muted">
          {scoped ? 'Showing your scope:' : 'Your scope:'}{' '}
          <span className="text-text-primary font-medium">{materials}</span>
          <span className="text-text-muted"> · </span>
          <span className="text-text-primary font-medium">{states}</span>
        </span>
        <span className="flex items-center gap-2">
          <button onClick={openEditor} className="text-green-accent hover:underline">
            Edit
          </button>
          <span className="text-border-default">|</span>
          <button
            onClick={() => setScoped(!scoped)}
            className="text-text-muted hover:text-text-secondary"
          >
            {scoped ? 'Show everything' : 'Show my scope'}
          </button>
        </span>
      </div>
    </div>
  );
}
