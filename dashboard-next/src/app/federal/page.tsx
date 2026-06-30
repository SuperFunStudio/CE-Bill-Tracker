'use client';
import { useState, useMemo } from 'react';
import { useFederalActions, useLitigationCases, useLitigationCase } from '@/hooks/useFederal';
import { MetricCard } from '@/components/ui/MetricCard';
import { AlertBanner } from '@/components/ui/AlertBanner';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { RiskBadge } from '@/components/ui/RiskBadge';
import { AlertIcon } from '@/components/ui/icons';
import { formatDate, daysUntil, fixEncoding, formatInstrumentType } from '@/lib/utils';
import { MATERIAL_CATEGORIES } from '@/components/bills/BillFilters';
import type { FederalActionSummary, LitigationCaseSummary } from '@/lib/types';
import { SkeletonList } from '@/components/ui/SkeletonList';
import { EmptyState } from '@/components/ui/EmptyState';

const titleCase = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

// Trial date for the Oregon NAW v. DEQ preemption case — single source so the banner phrasing
// updates from the date rather than carrying a hand-typed "trial July 13, 2026" that goes stale.
const NAW_TRIAL_DATE = '2026-07-13';

function ActionTypeBadge({ type }: { type: string | null | undefined }) {
  if (!type) return null;
  return (
    <span className="bg-bg-primary border border-border-default rounded px-2 py-0.5 text-xs text-text-secondary">
      {titleCase(type)}
    </span>
  );
}

// friction_type is the federal-specific axis: how this action pressures state EPR programs.
function FrictionBadge({ friction }: { friction: string | null | undefined }) {
  if (!friction || friction === 'none') return null;
  return (
    <span className="bg-amber-100 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800 rounded px-2 py-0.5 text-xs text-amber-800 dark:text-amber-300">
      {titleCase(friction)}
    </span>
  );
}

function FederalActionCard({ action }: { action: FederalActionSummary }) {
  const commentDays = daysUntil(action.comment_deadline);
  return (
    <div className="surface-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {action.agency && <span className="text-green-accent text-xs font-mono">{action.agency}</span>}
            <ActionTypeBadge type={action.action_type} />
            {action.instrument_type && action.instrument_type !== 'other' && (
              <span className="bg-bg-primary border border-green-accent/40 rounded px-2 py-0.5 text-xs text-green-accent">
                {formatInstrumentType(action.instrument_type)}
              </span>
            )}
            <FrictionBadge friction={action.friction_type} />
            {action.preemption_risk && action.preemption_risk !== 'none' && <RiskBadge risk={action.preemption_risk} />}
          </div>
          <h3 className="text-text-primary font-medium text-sm leading-snug">
            {fixEncoding(action.title) || 'Untitled Action'}
          </h3>
        </div>
        <div className="text-text-muted text-xs shrink-0">{formatDate(action.published_date)}</div>
      </div>

      {action.ai_summary && (
        <p className="text-text-secondary text-body">{fixEncoding(action.ai_summary)}</p>
      )}

      {action.material_categories && action.material_categories.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {action.material_categories.filter(m => m !== 'other').map(m => (
            <span key={m} className="bg-bg-primary border border-border-default rounded px-1.5 py-0.5 text-meta text-text-muted">
              {titleCase(m)}
            </span>
          ))}
        </div>
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
      className={`list-card p-4 ${isSelected ? '!border-green-accent/60' : ''}`}
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
  if (!data?.events?.length) return <div className="text-text-secondary text-sm px-4 py-2">No events recorded.</div>;
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
  const [instrumentFilter, setInstrumentFilter] = useState('');
  const [materialFilter, setMaterialFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [expandedCaseId, setExpandedCaseId] = useState<number | null>(null);

  // ce_relevant defaults true server-side; pass it explicitly so the page only ever shows
  // classified-relevant federal actions (the API still supports ce_relevant=false to inspect noise).
  const { data: actions = [], isLoading: actionsLoading } = useFederalActions({ limit: 100, ce_relevant: true, days_back: 3650 });
  const { data: cases = [], isLoading: casesLoading } = useLitigationCases();

  const filteredActions = useMemo(() => {
    let filtered = actions;
    if (instrumentFilter) filtered = filtered.filter(a => a.instrument_type === instrumentFilter);
    if (materialFilter) filtered = filtered.filter(a => a.material_categories?.includes(materialFilter));
    if (riskFilter) filtered = filtered.filter(a => (a.preemption_risk ?? '').toLowerCase() === riskFilter);
    return filtered;
  }, [actions, instrumentFilter, materialFilter, riskFilter]);

  const highRisk = filteredActions.filter(a => (a.preemption_risk ?? '').toLowerCase() === 'high').length;
  // Curated context, but the date drives the phrasing so the banner can't read as stale once the
  // trial passes (it flips to "watch for a ruling" instead of advertising a date in the past).
  const trialDays = daysUntil(NAW_TRIAL_DATE);
  const trialPhrase =
    trialDays == null ? `trial ${formatDate(NAW_TRIAL_DATE)}`
    : trialDays > 0 ? `trial ${formatDate(NAW_TRIAL_DATE)}`
    : trialDays === 0 ? 'trial underway'
    : `trial concluded ${formatDate(NAW_TRIAL_DATE)} — watch for a ruling`;
  // Only surface facet options actually present in the data, so empty dropdowns don't appear.
  const instrumentOptions = Array.from(new Set(actions.map(a => a.instrument_type).filter((t): t is string => !!t && t !== 'other'))).sort();
  const materialOptions = MATERIAL_CATEGORIES.filter(m => m !== 'other' && actions.some(a => a.material_categories?.includes(m)));

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <GazetteHeader title="Federal Actions" subtitle="Federal Register actions, preemption risk, and EPR litigation" />

      {/* Preemption context — a standing editorial brief, not a live alert. Kept neutral so alarm-red
          stays reserved for the data-driven "High Preemption Risk" metric below. */}
      <div className="surface-card p-4 space-y-1">
        <div className="flex items-center gap-2 text-text-secondary font-semibold text-sm">
          <AlertIcon className="text-base shrink-0 text-amber-500" /> Federal Preemption Context
        </div>
        <p className="text-text-secondary text-sm">
          <strong className="text-text-primary">Oregon NAW v. Oregon DEQ</strong> ({trialPhrase}) challenges Oregon&rsquo;s packaging EPR law under the Dormant Commerce Clause.
          A ruling could set precedent affecting all state EPR programs.
        </p>
        <p className="text-text-secondary text-sm">
          <strong className="text-text-primary">PACK Act</strong> (proposed federal packaging legislation) could preempt state programs if enacted.
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
          <label className="text-text-muted text-xs uppercase">Instrument</label>
          <select
            value={instrumentFilter}
            onChange={e => setInstrumentFilter(e.target.value)}
            className="bg-bg-primary border border-border-default rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-green-accent"
          >
            <option value="">All Instruments</option>
            {instrumentOptions.map(t => (
              <option key={t} value={t}>{formatInstrumentType(t)}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Material / Product</label>
          <select
            value={materialFilter}
            onChange={e => setMaterialFilter(e.target.value)}
            className="bg-bg-primary border border-border-default rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-green-accent"
          >
            <option value="">All Materials</option>
            {materialOptions.map(m => (
              <option key={m} value={m}>{titleCase(m)}</option>
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
            {['high', 'medium', 'low'].map(r => <option key={r} value={r}>{titleCase(r)}</option>)}
          </select>
        </div>
      </div>

      {/* Federal actions */}
      <div>
        <SectionHeader title={`Federal Register Actions (${filteredActions.length})`} />
        {actionsLoading ? (
          <SkeletonList rows={4} height="h-28" />
        ) : filteredActions.length === 0 ? (
          <EmptyState title="No federal actions found." />
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
          <SkeletonList rows={3} height="h-20" />
        ) : cases.length === 0 ? (
          <EmptyState title="No litigation cases tracked." />
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
