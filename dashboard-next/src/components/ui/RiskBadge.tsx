import { riskBgClass } from '@/lib/utils';

interface RiskBadgeProps {
  risk: string | null | undefined;
}

export function RiskBadge({ risk }: RiskBadgeProps) {
  const label = risk ?? 'Unknown';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${riskBgClass(risk)}`}>
      {label} Risk
    </span>
  );
}
