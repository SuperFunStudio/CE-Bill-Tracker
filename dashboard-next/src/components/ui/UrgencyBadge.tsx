import { urgencyBgClass } from '@/lib/utils';

interface UrgencyBadgeProps {
  urgency: string | null | undefined;
}

export function UrgencyBadge({ urgency }: UrgencyBadgeProps) {
  const label = urgency ? urgency.charAt(0).toUpperCase() + urgency.slice(1).toLowerCase() : 'Low';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${urgencyBgClass(urgency)}`}>
      {label === 'High' ? '🔴' : label === 'Medium' ? '🟡' : '⚪'} {label}
    </span>
  );
}
