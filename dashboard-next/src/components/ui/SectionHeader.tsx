interface SectionHeaderProps {
  title: string;
  subtitle?: string;
}

export function SectionHeader({ title, subtitle }: SectionHeaderProps) {
  return (
    <div className="mb-4">
      <h2 className="text-lg font-semibold text-text-primary border-l-4 border-green-accent pl-3">
        {title}
      </h2>
      {subtitle && <p className="text-text-muted text-sm mt-1 pl-4">{subtitle}</p>}
    </div>
  );
}
