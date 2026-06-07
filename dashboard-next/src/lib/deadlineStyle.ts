// Single-hue accent styling for deadlines: one brand accent color, distinguished
// by OPACITY rather than by hue. Sooner deadlines render opaque; far-off ones
// fade out — so a date-sorted list reads as a gradient from urgent to distant.
//
// Each value is a complete Tailwind class string (not interpolated) so the JIT
// compiler can see and generate it.

export function deadlineAccentText(days: number | null): string {
  if (days === null) return 'text-green-accent/45';
  if (days <= 30) return 'text-green-accent';
  if (days <= 90) return 'text-green-accent/85';
  if (days <= 365) return 'text-green-accent/70';
  if (days <= 730) return 'text-green-accent/55';
  return 'text-green-accent/45';
}

export function deadlineAccentDot(days: number | null): string {
  if (days === null) return 'bg-green-accent/45';
  if (days <= 30) return 'bg-green-accent';
  if (days <= 90) return 'bg-green-accent/85';
  if (days <= 365) return 'bg-green-accent/70';
  if (days <= 730) return 'bg-green-accent/55';
  return 'bg-green-accent/45';
}
