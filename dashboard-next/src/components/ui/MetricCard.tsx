interface MetricCardProps {
  label: string;
  value: string | number;
  sublabel?: string;
  accent?: boolean;
  compact?: boolean;
}

export function MetricCard({ label, value, sublabel, accent, compact }: MetricCardProps) {
  return (
    <div className={`bg-bg-secondary border border-border-default rounded-lg ${compact ? 'p-2' : 'p-4'}`}>
      <div className={`text-text-muted uppercase tracking-wider mb-0.5 ${compact ? 'text-[10px]' : 'text-xs'}`}>
        {label}
      </div>
      <div className={`font-bold ${accent ? 'text-green-accent' : 'text-text-primary'} ${compact ? 'text-lg' : 'text-2xl'}`}>
        {value}
      </div>
      {sublabel && !compact && (
        <div className="text-text-muted text-xs mt-1">{sublabel}</div>
      )}
    </div>
  );
}
