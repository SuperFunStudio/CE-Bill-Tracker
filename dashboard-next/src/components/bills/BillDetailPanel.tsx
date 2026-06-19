'use client';
import Link from 'next/link';
import type { BillSummary } from '@/lib/types';
import { fixEncoding, formatDate, formatInstrumentType, isWeakening } from '@/lib/utils';
import { useBill, useBillLitigationCases } from '@/hooks/useBills';
import { ClassificationBadge } from '@/components/bills/ClassificationBadge';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { RiskScore } from '@/components/ui/RiskScore';
import { CloseIcon } from '@/components/ui/icons';

interface BillDetailPanelProps {
  bill: BillSummary;
  onClose?: () => void;
}

export function BillDetailPanel({ bill, onClose }: BillDetailPanelProps) {
  // compliance_details no longer rides along on the bulk list (it's the paid extraction) — fetch the
  // per-bill detail to populate the compliance layers. Free per-bill detail is intended; the gate is
  // on the *bulk* harvest, not single-bill views.
  const { data: detail, isLoading, isError, refetch } = useBill(bill.id);
  const cd = detail?.compliance_details;
  const { data: litigationCases = [] } = useBillLitigationCases(
    bill.litigation_case_count > 0 ? bill.id : null
  );

  const hasPrimary = (cd?.covered_products?.length ?? 0) > 0
    || (cd?.producer_obligations?.length ?? 0) > 0
    || (cd?.deadlines?.length ?? 0) > 0;

  const hasSecondary = cd?.producer_definition || cd?.fees || cd?.enforcement || cd?.preemption_notes;

  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg p-5 space-y-4">

      {/* ── Layer 1: Identity ── */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="text-green-accent font-mono font-bold text-sm">{bill.state}</span>
            {bill.bill_number && (
              <span className="text-text-muted font-mono text-sm">{bill.bill_number}</span>
            )}
            <StatusBadge status={bill.status} weakening={isWeakening(bill)} showCaption dashWhenEmpty={false} />
          </div>
          <h3 className="text-text-primary text-lg font-bold leading-snug">
            {fixEncoding(bill.title) || 'Untitled'}
          </h3>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-text-muted hover:text-text-primary text-lg shrink-0 mt-0.5"
          >
            <CloseIcon />
          </button>
        )}
      </div>

      {/* Metadata row — type + last action only */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        <span>Type: <span className="text-text-secondary">{formatInstrumentType(bill.instrument_type)}</span></span>
        <span>Last Action: <span className="text-text-secondary">{formatDate(bill.last_action_date)}</span></span>
      </div>

      {/* Classification transparency — auto-classified vs reviewed, linked to methodology */}
      <ClassificationBadge bill={bill} showLink className="border-t border-border-default pt-3" />

      {/* Material category pills */}
      {bill.material_categories && bill.material_categories.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {bill.material_categories.map(cat => (
            <span key={cat} className="bg-bg-primary border border-border-default rounded px-2 py-0.5 text-xs text-green-light">
              {cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
            </span>
          ))}
        </div>
      )}

      {/* AI summary */}
      {bill.ai_summary && (
        <div className="bg-bg-primary rounded p-3 text-sm text-text-secondary leading-relaxed">
          {fixEncoding(bill.ai_summary)}
        </div>
      )}

      {/* Compliance fetch status — the paid layers below render blank until this resolves, so
          signal loading/error rather than letting the panel look complete-but-empty. */}
      {isLoading && !detail && (
        <div className="border-l-2 border-border-default pl-3 space-y-2" aria-live="polite">
          <div className="h-2.5 w-32 animate-pulse rounded bg-bg-tertiary" />
          <div className="h-2.5 w-full animate-pulse rounded bg-bg-tertiary" />
          <div className="h-2.5 w-2/3 animate-pulse rounded bg-bg-tertiary" />
          <span className="sr-only">Loading compliance details…</span>
        </div>
      )}
      {isError && (
        <p className="text-meta text-text-muted">
          Couldn&apos;t load compliance details.{' '}
          <button onClick={() => refetch()} className="text-green-accent hover:underline">
            Retry
          </button>
        </p>
      )}

      {/* ── Layer 2: Primary compliance content ── */}
      {hasPrimary && (
        <div className="space-y-3">
          {cd?.covered_products && cd.covered_products.length > 0 && (
            <div className="border-l-2 border-green-accent/40 pl-3">
              <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide mb-1">
                Covered Products
              </div>
              <ul className="space-y-0.5">
                {cd.covered_products.map((p, i) => (
                  <li key={i} className="text-text-primary text-sm flex gap-2">
                    <span className="text-green-accent/60 shrink-0 select-none">·</span>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {cd?.producer_obligations && cd.producer_obligations.length > 0 && (
            <div className="border-l-2 border-green-accent/40 pl-3">
              <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide mb-1">
                Producer Obligations
              </div>
              <ul className="space-y-0.5">
                {cd.producer_obligations.map((o, i) => (
                  <li key={i} className="text-text-primary text-sm flex gap-2">
                    <span className="text-green-accent/60 shrink-0 select-none">·</span>
                    {o}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {cd?.deadlines && cd.deadlines.length > 0 && (
            <div className="border-l-2 border-green-accent/40 pl-3">
              <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide mb-1">
                Key Deadlines
              </div>
              <div className="space-y-1">
                {cd.deadlines.map((d, i) => (
                  <div key={i} className="flex gap-3">
                    <span className="text-green-accent font-mono text-xs shrink-0 pt-0.5">{formatDate(d.date)}</span>
                    <span className="text-text-primary text-sm">{d.type}: {d.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Layer 3: Secondary detail ── */}
      {hasSecondary && (
        <div className="border-t border-border-default pt-3 space-y-3 text-sm">
          {cd?.producer_definition && (
            <div>
              <div className="text-text-muted text-xs uppercase mb-1">Producer Definition</div>
              <div className="text-text-secondary">{cd.producer_definition}</div>
            </div>
          )}

          {cd?.fees && (
            <div>
              <div className="text-text-muted text-xs uppercase mb-1">Fee Structure</div>
              <div className="text-text-secondary">
                <span className="font-medium">
                  {cd.fees.structure?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}:{' '}
                </span>
                {cd.fees.details}
              </div>
            </div>
          )}

          {cd?.enforcement && (
            <div>
              <div className="text-text-muted text-xs uppercase mb-1">Enforcement</div>
              <div className="text-text-secondary">
                <span className="font-medium">{cd.enforcement.agency}: </span>
                {cd.enforcement.penalties}
              </div>
            </div>
          )}

          {cd?.preemption_notes && (
            <div>
              <div className="text-text-muted text-xs uppercase mb-1">Preemption Notes</div>
              <div className="text-text-secondary">{cd.preemption_notes}</div>
            </div>
          )}
        </div>
      )}

      {/* ── Litigation: risk-accented ── */}
      {litigationCases.length > 0 && (
        <div className="border-l-2 border-amber-600/50 pl-3 space-y-2">
          <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
            Related Litigation
          </div>
          {litigationCases.map(c => (
            <div key={c.id} className="bg-bg-primary rounded p-3 text-sm space-y-1">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="text-text-primary font-medium">{c.case_name}</span>
                  {c.court_name && (
                    <span className="text-text-muted text-xs ml-2">{c.court_name}</span>
                  )}
                </div>
                {c.preemption_risk !== null && (
                  <RiskScore score={c.preemption_risk} label="preemption" className="shrink-0" />
                )}
              </div>
              <div className="flex flex-wrap gap-3 text-xs text-text-muted">
                {c.challenge_type && <span>{c.challenge_type.replace(/_/g, ' ')}</span>}
                {c.case_status && <span>{c.case_status}</span>}
                <span>{c.event_count} docket events</span>
              </div>
              {c.cl_url && (
                <a href={c.cl_url} target="_blank" rel="noopener noreferrer"
                   className="text-green-accent text-xs hover:underline">
                  View on CourtListener ↗
                </a>
              )}
            </div>
          ))}
          <div className="text-xs text-text-muted">
            <Link href="/federal" className="text-green-accent hover:underline">
              View all litigation on the Federal Actions page ↗
            </Link>
          </div>
        </div>
      )}

      {/* Source link */}
      {bill.source_url && (
        <a
          href={bill.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-green-accent text-sm hover:underline"
        >
          View Source ↗
        </a>
      )}
    </div>
  );
}
