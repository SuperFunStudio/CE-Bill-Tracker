import { riskLevel } from '@/lib/utils';

interface RiskScoreProps {
  /** 0–100 composite risk / preemption score. */
  score: number | null | undefined;
  /** Optional caption for what the score measures, e.g. "preemption risk". */
  label?: string;
  className?: string;
}

/**
 * Renders a risk score with its denominator AND a text severity level, so
 * meaning never rides on color alone (WCAG 1.4.1) and a bare "82" never appears
 * without context (Tufte: counts need a scale). Example: "82 / 100 · High".
 */
export function RiskScore({ score, label, className = '' }: RiskScoreProps) {
  const { label: level, textClass } = riskLevel(score);
  if (score == null || Number.isNaN(score)) {
    return <span className={`text-meta text-text-muted ${className}`}>N/A</span>;
  }
  return (
    <span className={`inline-flex items-baseline gap-1 ${className}`}>
      {label && <span className="text-meta text-text-muted">{label}</span>}
      <span className={`font-semibold tabular-nums ${textClass}`}>{Math.round(score)}</span>
      <span className="text-meta text-text-muted">/ 100</span>
      <span className={`text-meta font-medium ${textClass}`}>· {level}</span>
    </span>
  );
}
