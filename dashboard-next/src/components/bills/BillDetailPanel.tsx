'use client';
import Link from 'next/link';
import type { BillSummary } from '@/lib/types';
import { fixEncoding, formatDate, formatInstrumentType, statusBadge } from '@/lib/utils';
import { useBillLitigationCases } from '@/hooks/useBills';

interface BillDetailPanelProps {
  bill: BillSummary;
  onClose?: () => void;
}

function StatusBadge({ status, stance }: { status: string | null; stance: string | null }) {
  if (!status) return null;
  const { cls, marker, markerCls, label } = statusBadge(status, stance);
  return (
    <span
      title={label || undefined}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${cls}`}
    >
      {marker && <span className={`leading-none ${markerCls}`}>{marker}</span>}
      {status.replace(/\b\w/g, c => c.toUpperCase())}
    </span>
  );
}

/** Short human label for a policy stance, shown in the detail metadata row. */
function stanceLabel(stance: string | null): string | null {
  switch (stance) {
    case 'advances': return 'Advances the policy';
    case 'weakens': return 'Weakens / exempts the policy';
    default: return null;
  }
}

export function BillDetailPanel({ bill, onClose }: BillDetailPanelProps) {
  const cd = bill.compliance_details;
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
            <StatusBadge status={bill.status} stance={bill.policy_stance} />
          </div>
          <h3 className="text-text-primary text-lg font-bold leading-snug">
            {fixEncoding(bill.title) || 'Untitled'}
          </h3>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-text-muted hover:text-text-primary text-lg shrink-0 mt-0.5">
            ✕
          </button>
        )}
      </div>

      {/* Metadata row — type + last action only */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        <span>Type: <span className="text-text-secondary">{formatInstrumentType(bill.instrument_type)}</span></span>
        <span>Last Action: <span className="text-text-secondary">{formatDate(bill.last_action_date)}</span></span>
        {stanceLabel(bill.policy_stance) && (
          <span>Direction: <span className={bill.policy_stance === 'weakens' ? 'text-red-400' : 'text-green-accent'}>
            {stanceLabel(bill.policy_stance)}
          </span></span>
        )}
      </div>

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
                  <span className={`font-bold text-sm shrink-0 ${
                    c.preemption_risk >= 70 ? 'text-red-400'
                    : c.preemption_risk >= 40 ? 'text-amber-400'
                    : 'text-green-accent'
                  }`}>{c.preemption_risk}</span>
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
