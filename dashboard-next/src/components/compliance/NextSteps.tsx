import { formatDate } from '@/lib/utils';
import { buildNextStep } from '@/lib/nextSteps';
import type { ComplianceDetails, CompliancePathway, DeadlineSummary } from '@/lib/types';

/**
 * The "Next steps for producers" block — the step between "this law exists" and "here's the action".
 * Stated as guidance, not as an order: we don't know the reader's role or whether a given law reaches
 * them, and the "Applies to" line below carries that qualification.
 *
 * Renders at the top of the deadline modal (framed by that date: pass `deadline`) and on the bill
 * detail panel / bill page (framed by the law as a whole: omit it). Pure and props-only, hook-free,
 * so the statically-exported /bill/[id]/[slug] page and the client modal render it identically —
 * same contract as BillComplianceLayers.
 *
 * Renders nothing when neither a pathway nor extracted obligations exist; see buildNextStep.
 */
export function NextSteps({
  pathway,
  deadline,
  details,
}: {
  pathway: CompliancePathway | null | undefined;
  deadline?: DeadlineSummary | null;
  details?: ComplianceDetails | null;
}) {
  const step = buildNextStep({ pathway, deadline, details });
  if (!step) return null;

  const due = deadline?.deadline_date ?? pathway?.next_deadline_date ?? null;
  const dueLabel = deadline ? 'Due' : 'Next deadline';

  return (
    <section
      aria-label="Next steps for producers"
      className="rounded-lg border border-green-accent/40 bg-green-accent/[0.06] p-4 space-y-2.5"
    >
      <div className="text-meta font-mono uppercase tracking-widest text-green-accent">
        Next steps for producers
      </div>

      <p className="text-text-primary text-base font-medium leading-snug">{step.action}</p>

      {/* The one line that distinguishes this date from the law's other dates — a law with three
          staged deadlines otherwise renders three identical blocks. */}
      {step.requirement && (
        <p className="text-body text-text-secondary leading-relaxed">
          <span className="text-text-muted text-xs uppercase tracking-wide mr-1.5">This date</span>
          {step.requirement}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
        {due && (
          <span>
            {dueLabel}: <span className="text-text-secondary font-mono tabular-nums">{formatDate(due)}</span>
          </span>
        )}
        {step.feeNote && <span className="text-text-secondary">{step.feeNote}</span>}
      </div>

      {step.who && (
        <p className="text-body text-text-secondary leading-relaxed">
          <span className="text-text-muted text-xs uppercase tracking-wide mr-1.5">Applies to</span>
          {step.who}
        </p>
      )}

      {step.obligations.length > 0 && (
        <div>
          <div className="text-text-muted text-xs uppercase tracking-wide mb-1">
            {step.obligationsMatched
              ? 'What this date requires'
              : 'Obligations under this law'}
          </div>
          <ul className="space-y-0.5">
            {step.obligations.map((o, i) => (
              <li key={i} className="text-text-primary text-body flex gap-2">
                <span className="text-green-accent/60 shrink-0 select-none">·</span>
                {o}
              </li>
            ))}
          </ul>
        </div>
      )}

      {step.link && (
        <a
          href={step.link.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-green-accent text-sm hover:underline"
        >
          {step.link.label} →
        </a>
      )}

      {/* Honesty rail: ~80% of pathways are the generic template (no designated PRO/agency action in
          the corpus). Say so rather than let a boilerplate line read as a filed-and-done instruction. */}
      {step.generic && (
        <p className="text-xs text-text-muted leading-snug">
          No designated program action is recorded for this measure yet — treat the above as the
          general obligation and verify against the source text.
        </p>
      )}
    </section>
  );
}
