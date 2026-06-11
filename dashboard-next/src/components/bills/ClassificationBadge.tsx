'use client';
import Link from 'next/link';
import type { BillSummary } from '@/lib/types';

/**
 * Classification transparency marker — converts the hidden relevance judgment into an auditable,
 * defensible one (a prerequisite for enterprise trust). Every bill is auto-classified against fixed
 * circularity criteria; `reviewed` flips once a human has spot-checked it. Links to /methodology.
 */
export function ClassificationBadge({
  bill,
  showLink = false,
  className = '',
}: {
  bill: BillSummary;
  showLink?: boolean;
  className?: string;
}) {
  const confidence =
    bill.confidence_score != null && bill.confidence_score >= 0
      ? `${Math.round(bill.confidence_score * 100)}% confidence`
      : null;
  const tooltip =
    `Screened against fixed circularity criteria, then ` +
    `${bill.reviewed ? 'spot-reviewed by a human' : 'auto-classified'}.` +
    (confidence ? ` ${confidence}.` : '');

  return (
    <span className={`inline-flex flex-wrap items-center gap-1.5 text-xs text-text-muted ${className}`} title={tooltip}>
      <span className="text-text-secondary">Relevance:</span>
      <span>
        auto-classified circularity-relevant
        {bill.reviewed && (
          <>
            {' · '}
            <span className="text-green-accent">reviewed</span>
          </>
        )}
      </span>
      {showLink && (
        <Link href="/methodology" className="text-green-accent hover:underline">
          How we decide what counts →
        </Link>
      )}
    </span>
  );
}
