'use client';
import { useState, useMemo } from 'react';
import Link from 'next/link';
import { useBills } from '@/hooks/useBills';
import { useCompanies, useCompany, useCompanyObligations, useExposureRanking, useExposureBrief } from '@/hooks/useCompanies';
import { MetricCard } from '@/components/ui/MetricCard';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { ScoreBadge } from '@/components/ui/ScoreBadge';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { StarIcon } from '@/components/ui/icons';
import { WatchListSection } from '@/components/watchlist/WatchListSection';
import { SavedPackagesSection } from '@/components/studio/SavedPackages';
import { AskHistorySection } from '@/components/research/AskHistorySection';
import { useAuth } from '@/components/auth/AuthContext';
import { formatCost, fixEncoding, formatDate, daysUntil, STATE_NAMES } from '@/lib/utils';
import type { CompanyObligation, CompanyObligationsResponse, FinancialStakes } from '@/lib/types';

// ─── Obligations View ("Are you affected + here's your next deadline") ───────

const DEADLINE_TYPE_LABEL: Record<string, string> = {
  compliance: 'Compliance',
  effective: 'Effective date',
  reporting: 'Reporting',
  fee_payment: 'Fee payment',
  registration: 'Registration',
  other: 'Milestone',
};

const prettyMaterial = (m: string) =>
  m.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

/** Countdown pill, colored by urgency. */
function DeadlineCountdown({ date }: { date: string }) {
  const days = daysUntil(date);
  if (days === null) return null;
  const cls =
    days <= 30
      ? 'bg-red-100 dark:bg-red-900/40 text-urgency-high border-urgency-high/30'
      : days <= 90
        ? 'bg-amber-100 dark:bg-amber-900/40 text-urgency-medium border-urgency-medium/30'
        : 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 border-green-400/30';
  const label = days === 0 ? 'Today' : days < 0 ? 'Passed' : days < 45 ? `${days} days` : `~${Math.round(days / 30)} mo`;
  return <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${cls}`}>{label}</span>;
}

function ObligationCard({ o }: { o: CompanyObligation }) {
  const dl = o.next_deadline;
  return (
    <div className="surface-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        {/* Left: what law, why it applies to you */}
        <div className="flex-1 min-w-0 basis-56">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-green-accent font-mono text-xs font-semibold">{o.state}</span>
            {o.bill_number && <span className="text-text-secondary text-sm font-medium">{o.bill_number}</span>}
          </div>
          <div className="text-text-primary text-sm leading-snug mb-2">{fixEncoding(o.bill_title) || 'Untitled'}</div>
          <div className="flex flex-wrap gap-1.5 items-center">
            {o.matched_materials.map(m => (
              <span key={m} className="badge-material text-xs px-2 py-0.5 rounded">
                {prettyMaterial(m)}
              </span>
            ))}
            {o.presence_types.length > 0 && (
              <span className="text-text-muted text-xs">
                · you operate in {STATE_NAMES[o.state] ?? o.state} ({o.presence_types.map(p => p.replace(/_/g, ' ')).join(', ')})
              </span>
            )}
          </div>
        </div>

        {/* Right: next deadline — its own full-width row on phones, right column at sm+ */}
        <div className="shrink-0 w-full text-left sm:w-44 sm:text-right">
          {dl ? (
            <>
              <div className="flex items-center justify-start sm:justify-end gap-2">
                <span className="text-text-muted text-meta uppercase tracking-wide">{DEADLINE_TYPE_LABEL[dl.deadline_type] ?? dl.deadline_type}</span>
                <DeadlineCountdown date={dl.deadline_date} />
              </div>
              <div className="text-text-primary text-sm font-semibold mt-0.5">{formatDate(dl.deadline_date)}</div>
              {o.upcoming_deadline_count > 1 && (
                <div className="text-text-muted text-xs mt-0.5">+{o.upcoming_deadline_count - 1} more deadline{o.upcoming_deadline_count - 1 > 1 ? 's' : ''}</div>
              )}
            </>
          ) : (
            <div className="text-text-muted text-xs">Enacted — no upcoming deadline</div>
          )}
        </div>
      </div>

      {/* Who's affected / obligation detail */}
      {dl?.who_affected && (
        <div className="mt-3 pt-3 border-t border-border-default text-xs text-text-secondary">
          <span className="text-text-muted">Obligation: </span>{dl.who_affected}
        </div>
      )}
      {dl?.description && !dl.who_affected && (
        <div className="mt-3 pt-3 border-t border-border-default text-xs text-text-secondary">{dl.description}</div>
      )}
      {/* Financial stakes for this law */}
      {o.stakes?.has_any && <ObligationStakes s={o.stakes} />}

      {(dl?.source_url || o.source_url) && (
        <div className="mt-2">
          <a href={dl?.source_url || o.source_url || '#'} target="_blank" rel="noopener noreferrer"
             className="text-green-accent text-xs hover:underline">View bill text →</a>
        </div>
      )}
    </div>
  );
}

/** Compact USD: $50k, $1.2m, $480m. */
function fmtUsd(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}m`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}k`;
  return `$${Math.round(n).toLocaleString()}`;
}

/** Portfolio "what's at stake" hero. Leads with the statutory penalty (grounded), then
 *  the annual program-fee range, then the eco-modulation design lever. */
function StakesPanel({ ob }: { ob: CompanyObligationsResponse }) {
  const penalty = ob.max_penalty_per_day_usd;
  const feeLow = ob.portfolio_annual_fee_low_usd;
  const feeHigh = ob.portfolio_annual_fee_high_usd;
  const swing = ob.portfolio_eco_modulation_swing_usd;
  if (penalty == null && feeLow == null) return null;

  return (
    <div className="bg-bg-secondary border border-border-default rounded-xl p-6 space-y-5">
      <div>
        <div className="text-text-muted text-xs uppercase tracking-wide mb-1">What&apos;s financially at stake</div>
        <p className="text-text-secondary text-body leading-relaxed max-w-3xl">
          Three things drive the cost of these enacted laws: the <span className="text-text-primary font-medium">penalty</span> for
          non-compliance, the recurring <span className="text-text-primary font-medium">program fees</span> you pay to a producer
          responsibility organization (PRO) on the packaging you put into each state, and the{' '}
          <span className="text-text-primary font-medium">eco-modulation</span> built into those fees — where recyclable,
          mono-material designs are charged far less than hard-to-recycle ones.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Penalty — grounded in statute, leads */}
        <div className="bg-bg-primary border border-urgency-high/30 rounded-lg p-4">
          <div className="text-urgency-high text-meta uppercase tracking-wide font-semibold mb-1">Non-compliance penalty</div>
          <div className="text-2xl font-bold text-text-primary">{penalty != null ? `${fmtUsd(penalty)}` : '—'}<span className="text-sm font-normal text-text-muted">{penalty != null ? ' / day' : ''}</span></div>
          <div className="text-text-muted text-xs mt-1">Largest daily civil penalty across your affected laws — written into statute, per violation.</div>
        </div>

        {/* Annual program fee */}
        <div className="bg-bg-primary border border-border-default rounded-lg p-4">
          <div className="text-text-muted text-meta uppercase tracking-wide font-semibold mb-1">Est. annual program fees</div>
          <div className="text-2xl font-bold text-green-light">
            {feeLow != null ? `${fmtUsd(feeLow)}–${fmtUsd(feeHigh)}` : '—'}
          </div>
          <div className="text-text-muted text-xs mt-1">
            {ob.any_fee_grounded
              ? 'From published fee schedules (CA SB 54 2027, OR CAA), apportioned to your state footprint.'
              : 'Benchmark estimate — no published schedule yet.'}
          </div>
        </div>

        {/* Eco-modulation lever */}
        <div className="bg-bg-primary border border-green-accent/30 rounded-lg p-4">
          <div className="text-green-accent text-meta uppercase tracking-wide font-semibold mb-1">Design lever (eco-modulation)</div>
          <div className="text-2xl font-bold text-green-accent">{swing != null ? `${fmtUsd(swing)}` : '—'}<span className="text-sm font-normal text-text-muted">{swing != null ? ' / yr' : ''}</span></div>
          <div className="text-text-muted text-xs mt-1">Annual fee swing between best-case recyclable formats and worst-case hard-to-recycle ones, on your materials.</div>
        </div>
      </div>

      <p className="text-text-muted text-meta leading-relaxed">
        Fees scale with the volume you sell in each state; we apportion your reported volume by state population as a proxy.
        Penalty figures are quoted verbatim from each statute. Fee ranges reflect each program&apos;s own published low–high scenario.
      </p>
    </div>
  );
}

/** Per-obligation stakes line: penalty + fee range + PRO + the design-lever formats. */
function ObligationStakes({ s }: { s: FinancialStakes }) {
  return (
    <div className="mt-3 pt-3 border-t border-border-default space-y-2">
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs">
        {s.penalty && (
          <span>
            <span className="text-text-muted">Penalty: </span>
            <span className="text-urgency-high font-semibold">{fmtUsd(s.penalty.amount_usd)}/{s.penalty.unit}</span>
          </span>
        )}
        {s.fee && (
          <span>
            <span className="text-text-muted">Annual fee: </span>
            <span className="text-green-light font-semibold">{fmtUsd(s.fee.annual_fee_low_usd)}–{fmtUsd(s.fee.annual_fee_high_usd)}</span>
            <span className={`ml-1.5 text-meta px-1.5 py-0.5 rounded-full border ${s.fee.annual_fee_grounded ? 'border-green-accent/40 text-green-accent' : 'border-border-default text-text-muted'}`}>
              {s.fee.annual_fee_grounded ? 'published rate' : 'estimate'}
            </span>
          </span>
        )}
        {s.pro_membership_usd != null && s.pro_membership_usd > 0 && (
          <span>
            <span className="text-text-muted">PRO registration: </span>
            <span className="text-text-secondary font-medium">{fmtUsd(s.pro_membership_usd)}</span>
          </span>
        )}
      </div>
      {s.fee?.eco_modulation_notes && s.fee.eco_modulation_notes.length > 0 && (
        <div className="text-meta text-text-muted">
          <span className="text-green-accent">Design lever: </span>
          {s.fee.eco_modulation_notes.join('  ·  ')}
        </div>
      )}
      {s.fee?.fee_basis && (
        <div className="text-meta text-text-muted italic">{s.fee.fee_basis}</div>
      )}
    </div>
  );
}

function ObligationsView() {
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: companies = [], isLoading: companiesLoading } = useCompanies(search || undefined);
  const { data: obligations, isLoading: obLoading } = useCompanyObligations(selectedId);

  const withDeadline = obligations?.obligations.filter(o => o.next_deadline) ?? [];
  const enactedNoDeadline = obligations?.obligations.filter(o => !o.next_deadline) ?? [];

  return (
    <div className="space-y-6">
      {/* Company search + selector — stacked on phones; min-w-0 so long company names in the
          select can't force the row (and the page) wider than the viewport */}
      <div className="flex flex-col sm:flex-row gap-3 max-w-2xl">
        <div className="flex-1 min-w-0 flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Search Company</label>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Company name…"
            className="w-full min-w-0 bg-bg-secondary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
          />
        </div>
        <div className="flex-1 min-w-0 flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Select Company</label>
          <select
            value={selectedId ?? ''}
            onChange={e => setSelectedId(e.target.value || null)}
            className="w-full min-w-0 bg-bg-secondary border border-border-default rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-green-accent"
          >
            <option value="">Select a company…</option>
            {companiesLoading && <option disabled>Loading…</option>}
            {companies.map(c => (
              <option key={c.id} value={c.id}>{c.name}{c.hq_state ? ` (${c.hq_state})` : ''}</option>
            ))}
          </select>
        </div>
      </div>

      {!selectedId && (
        <div className="text-center text-text-secondary py-12 text-body">
          Select a company to see which enacted laws affect it and when its next deadline falls.
        </div>
      )}

      {selectedId && obLoading && (
        <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-bg-secondary rounded-lg animate-pulse" />)}</div>
      )}

      {selectedId && obligations && !obLoading && (
        <>
          {/* Hero answer */}
          {obligations.affected_bill_count === 0 ? (
            <div className="bg-bg-secondary border border-border-default rounded-xl p-6 text-center">
              <div className="text-text-primary text-lg font-semibold mb-1">{obligations.company_name}</div>
              <div className="text-text-secondary text-body">
                No enacted laws currently match this company&apos;s materials and operating footprint.
              </div>
            </div>
          ) : (
            <div className="bg-bg-secondary border border-border-default rounded-xl p-6">
              <div className="text-text-muted text-xs uppercase tracking-wide mb-1">Compliance exposure</div>
              <div className="text-text-primary text-xl font-bold mb-3">{obligations.company_name}</div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <div className="text-3xl font-bold text-green-accent">{obligations.affected_bill_count}</div>
                  <div className="text-text-muted text-xs">enacted laws affect you<br />across {obligations.affected_states.length} state{obligations.affected_states.length !== 1 ? 's' : ''} ({obligations.affected_states.join(', ')})</div>
                </div>
                <div>
                  <div className="text-3xl font-bold text-text-primary">{obligations.upcoming_deadline_count}</div>
                  <div className="text-text-muted text-xs">upcoming compliance deadlines</div>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <div className="text-2xl font-bold text-text-primary">{obligations.next_deadline_date ? formatDate(obligations.next_deadline_date) : '—'}</div>
                    {obligations.next_deadline_date && <DeadlineCountdown date={obligations.next_deadline_date} />}
                  </div>
                  <div className="text-text-muted text-xs">your next deadline</div>
                </div>
              </div>
            </div>
          )}

          {/* What's financially at stake */}
          {obligations.affected_bill_count > 0 && <StakesPanel ob={obligations} />}

          {/* Laws with upcoming deadlines */}
          {withDeadline.length > 0 && (
            <div>
              <SectionHeader title="Next deadlines" subtitle="Enacted laws you're affected by, soonest deadline first" />
              <div className="space-y-2">
                {withDeadline.map(o => <ObligationCard key={o.bill_id} o={o} />)}
              </div>
            </div>
          )}

          {/* Enacted, no upcoming deadline */}
          {enactedNoDeadline.length > 0 && (
            <div>
              <SectionHeader title="Also enacted (no upcoming deadline)" subtitle="In effect or deadlines already passed — monitor for amendments" />
              <div className="space-y-2">
                {enactedNoDeadline.map(o => <ObligationCard key={o.bill_id} o={o} />)}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Bill View ──────────────────────────────────────────────────────────────
// Cost Estimate (beta) — DISABLED until PROs publish real per-tonne fee schedules (most enacted
// bills set fees via post-enactment rulemaking, not statute, so it rendered "$0 / N/A"). Kept
// intact (with its endpoints) for re-enable as a sub-tab in ObligationsTool.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function BillView() {
  const { data: bills = [] } = useBills({ ce_relevant: true, limit: 5000 });
  const [selectedBillId, setSelectedBillId] = useState<number | undefined>(undefined);
  const { data: ranking = [], isLoading } = useExposureRanking(selectedBillId, 50);

  const billOptions = useMemo(() => {
    const demo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
    return bills.filter(b => !demo || b.state === 'OR');
  }, [bills]);

  const totalCost = ranking.reduce((s, r) => s + (r.impact_score.estimated_annual_cost ?? 0), 0);
  const avgScore = ranking.length
    ? ranking.reduce((s, r) => s + r.impact_score.composite_score, 0) / ranking.length
    : 0;

  return (
    <div className="space-y-6">
      {/* Bill selector */}
      <div className="flex flex-col gap-1 max-w-lg">
        <label className="text-text-muted text-xs uppercase">Select Bill</label>
        <select
          value={selectedBillId ?? ''}
          onChange={e => setSelectedBillId(e.target.value ? Number(e.target.value) : undefined)}
          className="bg-bg-secondary border border-border-default rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-green-accent"
        >
          <option value="">Select a bill…</option>
          {billOptions.map(b => (
            <option key={b.id} value={b.id}>
              {b.state} {b.bill_number ?? ''} — {fixEncoding(b.title)?.slice(0, 60) ?? 'Untitled'}
            </option>
          ))}
        </select>
      </div>

      {selectedBillId === undefined && (
        <div className="text-center text-text-secondary py-12 text-body">Select a bill to see company exposure rankings.</div>
      )}

      {selectedBillId !== undefined && (
        <>
          {/* Metrics */}
          <div className="grid grid-cols-3 gap-4">
            <MetricCard label="Companies Exposed" value={ranking.length} accent />
            <MetricCard label="Total Industry Cost" value={formatCost(totalCost)} sublabel="estimated annual" />
            <MetricCard label="Avg Exposure Score" value={isLoading ? '\u2026' : Math.round(avgScore)} />
          </div>

          {/* Cost bar chart — simple CSS-based */}
          {ranking.length > 0 && (
            <div>
              <SectionHeader title="Top Companies by Estimated Cost" />
              <div className="space-y-2">
                {ranking.slice(0, 20).map((r, i) => {
                  const maxCost = Math.max(...ranking.slice(0, 20).map(x => x.impact_score.estimated_annual_cost ?? 0), 1);
                  const pct = ((r.impact_score.estimated_annual_cost ?? 0) / maxCost) * 100;
                  return (
                    <div key={r.company.id} className="flex items-center gap-3 text-sm">
                      <div className="text-text-muted w-5 text-right shrink-0 text-xs">{i + 1}</div>
                      <div className="text-text-secondary w-40 truncate shrink-0">{r.company.name}</div>
                      <div className="flex-1 bg-bg-primary rounded-full h-5 overflow-hidden">
                        <div
                          className="h-full bg-green-dark rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="text-green-light font-medium w-20 text-right shrink-0">
                        {formatCost(r.impact_score.estimated_annual_cost)}
                      </div>
                      <ScoreBadge score={r.impact_score.composite_score} size="sm" />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Full ranking table */}
          <div>
            <SectionHeader title={`Exposure Ranking (${ranking.length} companies)`} />
            {isLoading ? (
              <div className="space-y-2">{[...Array(6)].map((_, i) => <div key={i} className="h-10 bg-bg-secondary rounded animate-pulse" />)}</div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border-default">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-bg-secondary border-b border-border-default text-text-muted text-xs uppercase">
                      <th className="px-3 py-2 text-left w-10">#</th>
                      <th className="px-3 py-2 text-left">Company</th>
                      <th className="px-3 py-2 text-left w-12">HQ</th>
                      <th className="px-3 py-2 text-right w-24">Score</th>
                      <th className="px-3 py-2 text-right w-28">Est. Annual Cost</th>
                      <th className="px-3 py-2 text-right w-20">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ranking.map((r, i) => (
                      <tr key={r.company.id} className="border-b border-border-default hover:bg-bg-secondary transition-colors">
                        <td className="px-3 py-2 text-text-muted text-xs">{i + 1}</td>
                        <td className="px-3 py-2 text-text-primary font-medium">{r.company.name}</td>
                        <td className="px-3 py-2 text-text-muted text-xs">{r.company.hq_state ?? '\u2014'}</td>
                        <td className="px-3 py-2 text-right">
                          <ScoreBadge score={r.impact_score.composite_score} />
                        </td>
                        <td className="px-3 py-2 text-right text-green-light font-medium">
                          {formatCost(r.impact_score.estimated_annual_cost)}
                        </td>
                        <td className="px-3 py-2 text-right text-text-muted text-xs">
                          {r.impact_score.cost_confidence != null
                            ? `${Math.round(r.impact_score.cost_confidence * 100)}%`
                            : '\u2014'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ─── Exposure Brief ──────────────────────────────────────────────────────────

function ExposureBriefPanel({ companyId, billId }: { companyId: string; billId: number }) {
  const { data, isLoading, error } = useExposureBrief(companyId, billId);

  if (isLoading) return <div className="h-32 bg-bg-secondary rounded-lg animate-pulse" />;
  if (error) return <div className="text-urgency-high text-body">Failed to load exposure brief. The brief may not exist yet — run the interpretation job first.</div>;
  if (!data?.brief_json) return <div className="text-text-secondary text-body">No brief available for this company/bill combination.</div>;

  const brief = data.brief_json as Record<string, unknown>;

  const execSummary = brief.executive_summary != null ? String(brief.executive_summary) : null;
  const costEstimate = brief.cost_estimate != null ? String(brief.cost_estimate) : null;
  const keyObligations = Array.isArray(brief.key_obligations) ? (brief.key_obligations as string[]) : [];
  const redesignOps = Array.isArray(brief.redesign_opportunities) ? (brief.redesign_opportunities as string[]) : [];
  const recommendedAction = brief.recommended_action != null ? String(brief.recommended_action) : null;

  return (
    <div className="bg-bg-primary border border-border-default rounded-lg p-5 space-y-4 text-sm">
      {execSummary && (
        <div>
          <div className="text-text-muted text-xs uppercase mb-1">Executive Summary</div>
          <p className="text-text-secondary leading-relaxed text-body">{execSummary}</p>
        </div>
      )}
      {costEstimate && (
        <div>
          <div className="text-text-muted text-xs uppercase mb-1">Cost Estimate</div>
          <p className="text-green-light font-medium">{costEstimate}</p>
        </div>
      )}
      {keyObligations.length > 0 && (
        <div>
          <div className="text-text-muted text-xs uppercase mb-1">Key Obligations</div>
          <ul className="list-disc list-inside space-y-0.5 text-text-secondary">
            {keyObligations.map((o, i) => <li key={i}>{o}</li>)}
          </ul>
        </div>
      )}
      {redesignOps.length > 0 && (
        <div>
          <div className="text-text-muted text-xs uppercase mb-1">Redesign Opportunities</div>
          <ul className="list-disc list-inside space-y-0.5 text-text-secondary">
            {redesignOps.map((o, i) => <li key={i}>{o}</li>)}
          </ul>
        </div>
      )}
      {recommendedAction && (
        <div className="bg-green-dark/40 border border-green-accent/20 rounded p-3">
          <div className="text-green-accent text-xs uppercase mb-1">Recommended Action</div>
          <p className="text-green-light text-body">{recommendedAction}</p>
        </div>
      )}
      <div className="text-text-muted text-xs">
        Generated: {data.generated_at ? new Date(data.generated_at).toLocaleDateString() : '\u2014'}
      </div>
    </div>
  );
}

// ─── Company View ────────────────────────────────────────────────────────────

function CompanyView() {
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedBillId, setSelectedBillId] = useState<number | null>(null);

  const { data: companies = [], isLoading: companiesLoading } = useCompanies(search || undefined);
  const { data: company } = useCompany(selectedId);
  const { data: bills = [] } = useBills({ ce_relevant: true, limit: 5000 });

  return (
    <div className="space-y-6">
      {/* Company search + selector — same responsive treatment as ObligationsView's */}
      <div className="flex flex-col sm:flex-row gap-3 max-w-2xl">
        <div className="flex-1 min-w-0 flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Search Company</label>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Company name…"
            className="w-full min-w-0 bg-bg-secondary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
          />
        </div>
        <div className="flex-1 min-w-0 flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Select Company</label>
          <select
            value={selectedId ?? ''}
            onChange={e => { setSelectedId(e.target.value || null); setSelectedBillId(null); }}
            className="w-full min-w-0 bg-bg-secondary border border-border-default rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-green-accent"
          >
            <option value="">Select a company…</option>
            {companiesLoading && <option disabled>Loading…</option>}
            {companies.map(c => (
              <option key={c.id} value={c.id}>{c.name}{c.hq_state ? ` (${c.hq_state})` : ''}</option>
            ))}
          </select>
        </div>
      </div>

      {!selectedId && (
        <div className="text-center text-text-secondary py-12 text-body">Select a company to see its EPR exposure profile.</div>
      )}

      {selectedId && company && (
        <div className="space-y-5">
          {/* Company card */}
          <div className="bg-bg-primary border border-border-default rounded-xl p-5">
            <div className="text-text-primary text-xl font-bold mb-1">{company.name}</div>
            <div className="flex flex-wrap gap-4 text-xs text-text-muted mt-2">
              {company.hq_state && <span>HQ: <span className="text-text-secondary">{company.hq_state}</span></span>}
              {company.total_annual_volume_tonnes != null && (
                <span>Volume: <span className="text-text-secondary">{company.total_annual_volume_tonnes.toLocaleString()} t/yr</span></span>
              )}
              {company.naics_codes && company.naics_codes.length > 0 && (
                <span>NAICS: <span className="text-text-secondary">{company.naics_codes.slice(0, 3).join(', ')}</span></span>
              )}
            </div>

            {/* Materials */}
            {company.materials && company.materials.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {company.materials.map(m => (
                  <span key={m.id} className="badge-material text-xs px-2 py-0.5 rounded">
                    {m.material_category.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    {m.annual_volume_tonnes != null && ` \u00b7 ${m.annual_volume_tonnes.toLocaleString()}t`}
                  </span>
                ))}
              </div>
            )}

            {/* State presences */}
            {company.state_presences && company.state_presences.length > 0 && (
              <div className="mt-3">
                <div className="text-text-muted text-xs uppercase mb-1">State Presences</div>
                <div className="flex flex-wrap gap-2">
                  {company.state_presences.map(sp => (
                    <span key={sp.id} className="bg-bg-secondary border border-border-default rounded px-2 py-0.5 text-xs text-text-secondary">
                      {sp.state} <span className="text-text-muted">({sp.presence_type.replace(/_/g, ' ')})</span>
                      {sp.is_primary && <StarIcon className="inline-block ml-1 text-green-accent align-[-0.1em]" />}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Bill exposure list */}
          <div>
            <SectionHeader title="Bill Exposure" subtitle="Select a bill to generate an exposure brief" />
            <div className="space-y-2">
              {bills
                .filter(b => {
                  const demo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
                  return !demo || b.state === 'OR';
                })
                .slice(0, 30)
                .map(b => (
                  <div
                    key={b.id}
                    onClick={() => setSelectedBillId(prev => prev === b.id ? null : b.id)}
                    className={`list-card px-4 py-3 flex items-center justify-between ${selectedBillId === b.id ? '!border-green-accent/60' : ''}`}
                  >
                    <div className="flex-1 min-w-0">
                      <span className="text-green-accent font-mono text-xs mr-2">{b.state}</span>
                      {b.bill_number && <span className="text-text-muted text-xs mr-2">{b.bill_number}</span>}
                      <span className="text-text-secondary text-sm truncate">{fixEncoding(b.title)?.slice(0, 70)}</span>
                    </div>
                    <div className="text-text-muted text-xs ml-4 shrink-0">
                      {selectedBillId === b.id ? 'Hide brief ▲' : 'View brief ▼'}
                    </div>
                  </div>
                ))}
            </div>
          </div>

          {/* Exposure brief */}
          {selectedBillId !== null && (
            <div>
              <SectionHeader title="Exposure Brief" subtitle="AI-generated compliance exposure summary" />
              <ExposureBriefPanel companyId={selectedId} billId={selectedBillId} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Obligations Tool ────────────────────────────────────────────────────────

/** The live obligations tool (admins / demos): company-exposure obligations + the Company Profile,
 *  folded together as sub-tabs of the Beta section. */
function ObligationsTool() {
  const [activeTab, setActiveTab] = useState<'obligations' | 'company'>('obligations');

  return (
    <div className="space-y-5">
      <DemoBanner />
      {/* Sub-tabs — Company Profile folded in here per the My Portfolio IA. Cost Estimate (BillView)
          stays disabled; the component + endpoints are intact for re-enable. */}
      <div className="flex flex-wrap gap-1 bg-bg-secondary border border-border-default rounded-lg p-1 w-fit">
        {[
          { id: 'obligations' as const, label: 'Obligations & Deadlines' },
          { id: 'company' as const, label: 'Company Profile' },
        ].map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
              activeTab === id
                ? 'bg-green-dark text-green-accent'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'obligations' ? <ObligationsView /> : <CompanyView />}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function MyPortfolioPage() {
  const { isAdmin, loading } = useAuth();

  if (loading) {
    return <div className="p-6 max-w-6xl mx-auto"><div className="h-64 bg-bg-secondary rounded-xl animate-pulse" /></div>;
  }

  return (
    <div className="p-6 space-y-8 max-w-6xl mx-auto">
      <GazetteHeader title="My Library" subtitle="Your research, alerts, and saved packaging — in one place." />

      {/* ── Ask the Atlas history — private to the member; self-gates for anon/free ── */}
      <section>
        <AskHistorySection />
      </section>

      {/* ── Watch list & alerts — the self-serve Pro content; gates itself for anon/non-Pro ── */}
      <section className="border-t border-border-default pt-8">
        <WatchListSection />
      </section>

      {/* ── Saved studio packages — free-tier account data; gates itself for anon ── */}
      <section className="border-t border-border-default pt-8">
        <SavedPackagesSection />
      </section>

      {/* ── Obligations & Deadlines (Beta) — admin-only while it's still in beta; hidden entirely for
          everyone else (previously non-admins saw a bespoke-inquiry card here). ── */}
      {isAdmin && (
        <section className="space-y-4 border-t border-border-default pt-8">
          <div className="flex items-center gap-2">
            <h2 className="font-serif text-2xl text-text-primary">Obligations &amp; Deadlines</h2>
            <span className="text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
              Beta
            </span>
          </div>
          <p className="text-text-secondary text-body max-w-3xl">
            Which enacted laws affect a company, what each requires, and when its next deadline falls.
          </p>
          <ObligationsTool />
        </section>
      )}
    </div>
  );
}
