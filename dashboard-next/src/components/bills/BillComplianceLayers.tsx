import type { ComplianceDetails } from '@/lib/types';
import { formatDate } from '@/lib/utils';
import { presentDimensions } from '@/lib/dimensions';

/**
 * The extracted compliance content for a bill — the "primary" layer (covered products, producer
 * obligations, key deadlines), the "secondary" layer (producer definition, fees, enforcement,
 * preemption), and the structured compliance dimensions. Pure/props-only and hook-free, so it renders
 * identically in the client-side BillDetailPanel and in the statically-exported /bill/[id]/[slug] page.
 */
export function BillComplianceLayers({ cd }: { cd: ComplianceDetails | null | undefined }) {
  if (!cd) return null;

  const hasPrimary = (cd.covered_products?.length ?? 0) > 0
    || (cd.producer_obligations?.length ?? 0) > 0
    || (cd.deadlines?.length ?? 0) > 0;
  const hasSecondary = cd.producer_definition || cd.fees || cd.enforcement || cd.preemption_notes;
  const dimensions = presentDimensions(cd);

  if (!hasPrimary && !hasSecondary && dimensions.length === 0) return null;

  return (
    <>
      {/* ── Primary compliance content ── */}
      {hasPrimary && (
        <div className="space-y-3">
          {cd.covered_products && cd.covered_products.length > 0 && (
            <div className="border-l-2 border-green-accent/40 pl-3">
              <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide mb-1">
                Covered Products
              </div>
              <ul className="space-y-0.5">
                {cd.covered_products.map((p, i) => (
                  <li key={i} className="text-text-primary text-body flex gap-2">
                    <span className="text-green-accent/60 shrink-0 select-none">·</span>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {cd.producer_obligations && cd.producer_obligations.length > 0 && (
            <div className="border-l-2 border-green-accent/40 pl-3">
              <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide mb-1">
                Producer Obligations
              </div>
              <ul className="space-y-0.5">
                {cd.producer_obligations.map((o, i) => (
                  <li key={i} className="text-text-primary text-body flex gap-2">
                    <span className="text-green-accent/60 shrink-0 select-none">·</span>
                    {o}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {cd.deadlines && cd.deadlines.length > 0 && (
            <div className="border-l-2 border-green-accent/40 pl-3">
              <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide mb-1">
                Key Deadlines
              </div>
              <div className="space-y-1">
                {cd.deadlines.map((d, i) => (
                  <div key={i} className="flex gap-3">
                    <span className="text-green-accent font-mono text-xs shrink-0 pt-0.5">{formatDate(d.date)}</span>
                    <span className="text-text-primary text-body">{d.type}: {d.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Secondary detail ── */}
      {hasSecondary && (
        <div className="border-t border-border-default pt-3 space-y-3 text-body">
          {cd.producer_definition && (
            <div>
              <div className="text-text-muted text-xs uppercase mb-1">Producer Definition</div>
              <div className="text-text-secondary">{cd.producer_definition}</div>
            </div>
          )}

          {cd.fees && (
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

          {cd.enforcement && (
            <div>
              <div className="text-text-muted text-xs uppercase mb-1">Enforcement</div>
              <div className="text-text-secondary">
                <span className="font-medium">{cd.enforcement.agency}: </span>
                {cd.enforcement.penalties}
              </div>
            </div>
          )}

          {cd.preemption_notes && (
            <div>
              <div className="text-text-muted text-xs uppercase mb-1">Preemption Notes</div>
              <div className="text-text-secondary">{cd.preemption_notes}</div>
            </div>
          )}
        </div>
      )}

      {/* ── Structured compliance dimensions — each with a verbatim citation (see lib/dimensions.ts) ── */}
      {dimensions.length > 0 && (
        <div className="border-t border-border-default pt-3 space-y-2.5">
          <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
            Compliance Dimensions
          </div>
          {dimensions.map(d => (
            <div key={d.key} className="border-l-2 border-green-accent/40 pl-3">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-text-secondary text-xs font-medium">{d.label}</span>
                <span className="text-text-primary text-body">{d.summary}</span>
              </div>
              {d.excerpt && (
                <p className="text-xs text-text-muted italic mt-0.5 leading-snug">“{d.excerpt}”</p>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
