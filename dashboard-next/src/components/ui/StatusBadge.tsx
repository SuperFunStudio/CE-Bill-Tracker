import { statusBadge, formatStatusLabel } from '@/lib/utils';

interface StatusBadgeProps {
  status: string | null;
  /** When the bill weakens the circular economy, flips the badge red. */
  weakening?: boolean;
  /**
   * Show the "weakens circular economy" caption beneath the badge (used in the
   * detail panel). In dense tables leave this off — the caption rides as the
   * badge's title tooltip instead.
   */
  showCaption?: boolean;
  /** Render an em-dash when status is null (tables) vs. nothing (panels). */
  dashWhenEmpty?: boolean;
}

/**
 * Single shared status badge. Previously duplicated in BillTable and
 * BillDetailPanel, both of which rendered the raw status (so `passed_chamber`
 * showed an underscore). Now formats the label via formatStatusLabel().
 */
export function StatusBadge({
  status,
  weakening,
  showCaption = false,
  dashWhenEmpty = true,
}: StatusBadgeProps) {
  if (!status) {
    return dashWhenEmpty ? <span className="text-text-muted text-meta">—</span> : null;
  }
  const { cls, label } = statusBadge(status, weakening);
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-meta font-medium border ${cls}`}
        title={label || undefined}
      >
        {formatStatusLabel(status)}
      </span>
      {showCaption && label && (
        <span className="text-[11px] font-medium uppercase tracking-wide text-status-weakens">
          {label}
        </span>
      )}
    </span>
  );
}
