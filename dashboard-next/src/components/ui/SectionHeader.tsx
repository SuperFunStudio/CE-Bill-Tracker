interface SectionHeaderProps {
  title: string;
  subtitle?: string;
}

export function SectionHeader({ title, subtitle }: SectionHeaderProps) {
  return (
    <div className="mb-4">
      <h2 className="font-serif uppercase tracking-[0.06em] text-text-primary text-base sm:text-lg border-b border-text-primary/20 pb-1.5">
        {title}
      </h2>
      {subtitle && <p className="font-serif italic text-text-muted text-sm mt-1.5">{subtitle}</p>}
    </div>
  );
}
