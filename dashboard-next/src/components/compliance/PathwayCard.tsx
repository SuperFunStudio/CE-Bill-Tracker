'use client';
import { formatDate } from '@/lib/utils';
import type { CompliancePathway } from '@/lib/types';

// The concrete next-step a producer takes for a law. Covers US (join_pro/file_individual_plan/…) and
// EU (register_with_state/monitor/report_to_program) action types from build_compliance_pathways.py.
export const ACTION_LABEL: Record<string, string> = {
  join_pro: 'Join a PRO',
  file_individual_plan: 'File a plan',
  register_with_state: 'Register',
  pay_into_program: 'Pay into program',
  arrange_collection: 'Arrange collection',
  report_to_program: 'Report to program',
  monitor: 'Monitor',
  none: 'No action yet',
};

/** One enacted law's "how do I comply" card: the action, the law, a plain-language next step, the
 *  registration link, soonest deadline and fee flag. Region-generic (used by the self-serve checker
 *  and state profiles). */
export function PathwayCard({ p }: { p: CompliancePathway }) {
  const actionLabel = ACTION_LABEL[p.action_type ?? ''] ?? 'Action';
  return (
    <li className="rounded-lg border border-border-default bg-bg-secondary p-4">
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="font-mono text-meta uppercase tracking-wide text-green-accent border border-green-accent/40 rounded px-1.5 py-0.5">
          {actionLabel}
        </span>
        <h3 className="font-serif text-text-primary">
          {p.bill_number}
          {p.bill_title && <span className="text-text-secondary font-sans text-sm"> · {p.bill_title}</span>}
        </h3>
      </div>
      <p className="text-text-secondary text-body mt-1.5 leading-relaxed">{p.action_summary}</p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-xs text-text-muted">
        {p.entity && (
          p.registration_url ? (
            <a href={p.registration_url} target="_blank" rel="noopener noreferrer" className="text-green-accent hover:underline">
              {p.entity.name} &rarr;
            </a>
          ) : (
            <span className="text-text-primary">{p.entity.name}</span>
          )
        )}
        {p.next_deadline_date && <span className="tabular-nums">Next deadline {formatDate(p.next_deadline_date)}</span>}
        {p.has_fee && <span>Fee applies</span>}
      </div>
    </li>
  );
}
