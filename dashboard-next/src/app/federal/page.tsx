'use client';
import { useState, useMemo } from 'react';
import { useFederalActions, useLitigationCases, useLitigationCase } from '@/hooks/useFederal';
import { MetricCard } from '@/components/ui/MetricCard';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { RiskBadge } from '@/components/ui/RiskBadge';
import { formatDate, daysUntil, fixEncoding } from '@/lib/utils';
import type { FederalActionSummary, LitigationCaseSummary } from '@/lib/types';

function ActionTypeBadge({ type }: { type: string | null | undefined }) {
  if (!type) return null;
  return (
    <span className="bg-bg-primary border border-border-default rounded px-2 py-0.5 text-xs text-text-secondary">
      {type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
    </span>
  );
}

function FederalActionCard({ action }: { action: FederalActionSummary }) {
  const commentDays = daysUntil(action.comment_deadline);
  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {action.agency && <span className="text-green-accent text-xs font-mono">{action.agency}</span>}
            <ActionTypeBadge type={action.action_type} />
            {action.preemption_risk && <RiskBadge risk={action.preemption_risk} />}
          </div>
          <h3 className="text-text-primary font-medium text-sm leading-snug">
            {fixEncoding(action.title) || 'Untitled Action'}
          </h3>
        </div>
        <div className="text-text-muted text-xs shrink-0">{formatDate(action.published_date)}</div>
      </div>

      {action.ai_summary && (
        <p className="text-text-secondary text-sm">{fixEncoding(action.ai_summary)}</p>
      )}

      <div className="flex flex-wrap gap-4 text-xs text-text-muted">
        {action.comment_deadline && (
          <span className={commentDays !== null && commentDays <= 30 ? 'text-urgency-high' : ''}>
            Comment deadline: {formatDate(action.comment_deadline)}
            {commentDays !== null && commentDays >= 0 && ` (${commentDays}d)`}
          </span>
        )}
        {action.document_url && (
          <a href={action.document_url} target="_blank" rel="noopener noreferrer" className="text-green-accent hover:underline">
            View Document ↗
          </a>
        )}
      </div>
    </div>
  );
}

function LitigationCaseRow({ caseData, onSelect, isSelected }: {
  caseData: LitigationCaseSummary;
  onSelect: () => void;
  isSelected: boolean;
}) {
  const risk = caseData.preemption_risk;
  const riskColor = risk !== null && risk >= 70 ? 'text-urgency-high' :
    risk !== null && risk >= 40 ? 'text-urgency-medium' : 'text-green-accent';

  return (
    <div
      className={`bg-bg-secondary border rounded-lg p-4 cursor-pointer transition-colors ${isSelected ? 'border-green-accent/50' : 'border-border-default hover:border-green-accent/30'}`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {caseData.related_state && (
              <span className="text-green-accent font-mono text-xs">{caseData.related_state}</span>
            )}
            {caseData.challenge_type && (
              <span className="bg-bg-primary border border-border-default rounded px-2 py-0.5 text-xs text-text-secondary">
                {caseData.challenge_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
              </span>
            )}
            {caseData.case_status && (
              <span className="text-text-muted text-xs">{caseData.case_status}</span>
            )}
          </div>
          <div className="text-text-primary font-medium text-sm">{caseData.case_name}</div>
          {caseData.court_name && (
            <div className="text-text-muted text-xs mt-0.5">{caseData.court_name}</div>
          )}
        </div>
        <div className="text-right shrink-0">
          {risk !== null && (
            <div className={`font-bold text-lg ${riskColor}`}>{risk}</div>
          )}
          <div className="text-text-muted text-xs">{caseData.event_count} events</div>
        </div>
      </div>

      {caseData.key_plaintiffs && caseData.key_plaintiffs.length > 0 && (
        <div className="text-text-muted text-xs mt-2">
          Plaintiffs: {caseData.key_plaintiffs.slice(0, 3).join(', ')}
          {caseData.key_plaintiffs.length > 3 && ` +${caseData.key_plaintiffs.length - 3} more`}
        </div>
      )}

      <div className="text-text-muted text-xs mt-1">
        {isSelected ? '▲ Collapse' : '▼ Expand events'} · Last activity: {formatDate(caseData.last_activity_date)}
        {caseData.cl_url && (
          <> · <a href={caseData.cl_url} target="_blank" rel="noopener noreferrer" className="text-green-accent hover:underline" onClick={e => e.stopPropagation()}>CourtListener ↗</a></>
        )}
      </div>
    </div>
  );
}

function LitigationCaseDetail({ caseId }: { caseId: number }) {
  const { data } = useLitigationCase(caseId);
  if (!data?.events?.length) return <div className="text-text-muted text-sm px-4 py-2">No events recorded.</div>;
  return (
    <div className="bg-bg-primary border border-border-default rounded-lg mx-1 p-4 space-y-3">
      <div className="text-text-muted text-xs uppercase mb-2">Case Events</div>
      {data.events.map(ev => (
        <div key={ev.id} className="flex gap-3 text-sm">
          <div className="text-green-accent font-mono text-xs shrink-0 pt-0.5">{formatDate(ev.date_filed)}</div>
          <div>
            <div className="text-text-secondary font-medium text-xs">{ev.event_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</div>
            {ev.summary && <div className="text-text-muted text-xs mt-0.5">{ev.summary}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function FederalPage() {
  const [actionTypeFilter, setActionTypeFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [expandedCaseId, setExpandedCaseId] = useState<number | null>(null);

  const { data: actions = [], isLoading: actionsLoading } = useFederalActions({ limit: 100 });
  const { data: cases = [], isLoading: casesLoading } = useLitigationCases();

  const filteredActions = useMemo(() => {
    let filtered = actions;
    if (actionTypeFilter) filtered = filtered.filter(a => a.action_type === actionTypeFilter);
    if (riskFilter) filtered = filtered.filter(a => a.preemption_risk === riskFilter);
    return filtered;
  }, [actions, actionTypeFilter, riskFilter]);

  const highRisk = filteredActions.filter(a => a.preemption_risk === 'High').length;
  const actionTypes = Array.from(new Set(actions.map(a => a.action_type).filter(Boolean)));

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary mb-1">Federal Actions</h1>
        <p className="text-text-muted text-sm">Federal Register actions, preemption risk, and EPR litigation tracking</p>
      </div>

      {/* Preemption banner */}
      <div className="bg-red-100 dark:bg-red-950/50 border border-red-400 dark:border-red-800 rounded-lg p-4 space-y-1">
        <div className="text-red-700 dark:text-red-300 font-semibold text-sm">⚠ Federal Preemption Context</div>
        <p className="text-red-700/80 dark:text-red-200/80 text-sm">
          <strong>Oregon NAW v. Oregon DEQ</strong> (trial July 13, 2026) challenges Oregon's packaging EPR law under the Dormant Commerce Clause.
          A ruling could set precedent affecting all state EPR programs.
        </p>
        <p className="text-red-700/80 dark:text-red-200/80 text-sm">
          <strong>PACK Act</strong> (proposed federal packaging legislation) could preempt state programs if enacted.
          Monitor comment periods and committee activity.
        </p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <MetricCard label="Federal Actions" value={filteredActions.length} accent />
        <MetricCard label="High Preemption Risk" value={highRisk} sublabel={highRisk > 0 ? 'Review immediately' : 'None flagged'} />
        <MetricCard label="Active Litigation Cases" value={cases.filter(c => c.case_status?.toLowerCase() === 'active').length} />
      </div>

      {/* Filters */}
      <div className="bg-bg-secondary border border-border-default rounded-lg p-4 flex flex-wrap gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Action Type</label>
          <select
            value={actionTypeFilter}
            onChange={e => setActionTypeFilter(e.target.value)}
            className="bg-bg-primary border border-border-default rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-green-accent"
          >
            <option value="">All Types</option>
            {(actionTypes as string[]).map(t => (
              <option key={t} value={t}>{t!.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Preemption Risk</label>
          <select
            value={riskFilter}
            onChange={e => setRiskFilter(e.target.value)}
            className="bg-bg-primary border border-border-default rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-green-accent"
          >
            <option value="">All Risk Levels</option>
            {['High', 'Medium', 'Low'].map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
      </div>

      {/* Federal actions */}
      <div>
        <SectionHeader title={`Federal Register Actions (${filteredActions.length})`} />
        {actionsLoading ? (
          <div className="space-y-3">{[...Array(4)].map((_, i) => <div key={i} className="h-28 bg-bg-secondary rounded-lg animate-pulse" />)}</div>
        ) : filteredActions.length === 0 ? (
          <div className="text-center text-text-muted py-8">No federal actions found.</div>
        ) : (
          <div className="space-y-3">
            {filteredActions.map(a => <FederalActionCard key={a.id} action={a} />)}
          </div>
        )}
      </div>

      {/* Litigation */}
      <div>
        <SectionHeader
          title={`EPR Litigation Cases (${cases.length})`}
          subtitle="Judicial challenges to state EPR laws, tracked via CourtListener"
        />
        {casesLoading ? (
          <div className="space-y-3">{[...Array(3)].map((_, i) => <div key={i} className="h-20 bg-bg-secondary rounded-lg animate-pulse" />)}</div>
        ) : cases.length === 0 ? (
          <div className="text-center text-text-muted py-8">No litigation cases tracked.</div>
        ) : (
          <div className="space-y-2">
            {cases.map(c => (
              <div key={c.id}>
                <LitigationCaseRow
                  caseData={c}
                  onSelect={() => setExpandedCaseId(prev => prev === c.id ? null : c.id)}
                  isSelected={expandedCaseId === c.id}
                />
                {expandedCaseId === c.id && <LitigationCaseDetail caseId={c.id} />}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
