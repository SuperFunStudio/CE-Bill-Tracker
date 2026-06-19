import type { ReactNode } from 'react';

interface EmptyStateProps {
  /** Optional leading icon/illustration. */
  icon?: ReactNode;
  /** Short headline, e.g. "No bills yet" or "Select a company". */
  title: string;
  /** One or two sentences explaining the state or the next step. */
  body?: ReactNode;
  /** Optional primary action (button or link). */
  action?: ReactNode;
  className?: string;
}

/**
 * One designed empty/prompt state for every "nothing here yet" and "pick
 * something" case. Replaces the three divergent treatments that existed before
 * (bare muted sentence vs. bordered card vs. tinted gate) so a first-time user
 * never sees an unstyled line that reads as a broken page.
 */
export function EmptyState({ icon, title, body, action, className = '' }: EmptyStateProps) {
  return (
    <div
      className={`surface-inset flex flex-col items-center justify-center gap-2 px-6 py-10 text-center ${className}`}
    >
      {icon && <div className="text-text-muted">{icon}</div>}
      <p className="text-body font-medium text-text-primary">{title}</p>
      {body && <p className="text-meta text-text-secondary max-w-prose">{body}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
