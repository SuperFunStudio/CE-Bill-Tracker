import { scoreColor } from '@/lib/utils';

interface ScoreBadgeProps {
  score: number;
  size?: 'sm' | 'md';
}

export function ScoreBadge({ score, size = 'md' }: ScoreBadgeProps) {
  const color = scoreColor(score);
  const pct = Math.round(score);
  return (
    <span className={`font-mono font-bold ${color} ${size === 'sm' ? 'text-sm' : 'text-base'}`}>
      {pct}
    </span>
  );
}
