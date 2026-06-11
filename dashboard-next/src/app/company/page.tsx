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
import { LockIcon, StarIcon } from '@/components/ui/icons';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { formatCost, fixEncoding, formatDate, daysUntil, STATE_NAMES } from '@/lib/utils';
import type { CompanyObligation } from '@/lib/types';

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
    <div className="bg-bg-primary border border-border-default rounded-lg p-4 hover:border-green-accent/30 transition-colors">
      <div className="flex items-start justify-between gap-4">
        {/* Left: what law, why it applies to you */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-green-accent font-mono text-xs font-semibold">{o.state}</span>
            {o.bill_number && <span className="text-text-secondary text-sm font-medium">{o.bill_number}</span>}
          </div>
          <div className="text-text-primary text-sm leading-snug mb-2">{fixEncoding(o.bill_title) || 'Untitled'}</div>
          <div className="flex flex-wrap gap-1.5 items-center">
            {o.matched_materials.map(m => (
              <span key={m} className="bg-blue-100 dark:bg-[#1e3a5f] text-blue-700 dark:text-[#93c5fd] text-xs px-2 py-0.5 rounded">
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

        {/* Right: next deadline */}
        <div className="shrink-0 text-right w-44">
          {dl ? (
            <>
              <div className="flex items-center justify-end gap-2">
                <span className="text-text-muted text-[10px] uppercase tracking-wide">{DEADLINE_TYPE_LABEL[dl.deadline_type] ?? dl.deadline_type}</span>
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
      {(dl?.source_url || o.source_url) && (
        <div className="mt-2">
          <a href={dl?.source_url || o.source_url || '#'} target="_blank" rel="noopener noreferrer"
             className="text-green-accent text-xs hover:underline">View bill text →</a>
        </div>
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
      {/* Company search + selector */}
      <div className="flex gap-3 max-w-2xl">
        <div className="flex-1 flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Search Company</label>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Company name…"
            className="bg-bg-secondary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
          />
        </div>
        <div className="flex-1 flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Select Company</label>
          <select
            value={selectedId ?? ''}
            onChange={e => setSelectedId(e.target.value || null)}
            className="bg-bg-secondary border border-border-default rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-green-accent"
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
        <div className="text-center text-text-muted py-12">
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
              <div className="text-text-muted text-sm">
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

function BillView() {
  const { data: bills = [] } = useBills({ epr_relevant: true, limit: 5000 });
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
        <div className="text-center text-text-muted py-12">Select a bill to see company exposure rankings.</div>
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
  if (error) return <div className="text-urgency-high text-sm">Failed to load exposure brief. The brief may not exist yet — run the interpretation job first.</div>;
  if (!data?.brief_json) return <div className="text-text-muted text-sm">No brief available for this company/bill combination.</div>;

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
          <p className="text-text-secondary leading-relaxed">{execSummary}</p>
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
          <p className="text-green-light text-sm">{recommendedAction}</p>
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
  const { data: bills = [] } = useBills({ epr_relevant: true, limit: 5000 });

  return (
    <div className="space-y-6">
      {/* Company search + selector */}
      <div className="flex gap-3 max-w-2xl">
        <div className="flex-1 flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Search Company</label>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Company name…"
            className="bg-bg-secondary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
          />
        </div>
        <div className="flex-1 flex flex-col gap-1">
          <label className="text-text-muted text-xs uppercase">Select Company</label>
          <select
            value={selectedId ?? ''}
            onChange={e => { setSelectedId(e.target.value || null); setSelectedBillId(null); }}
            className="bg-bg-secondary border border-border-default rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-green-accent"
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
        <div className="text-center text-text-muted py-12">Select a company to see its EPR exposure profile.</div>
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
                  <span key={m.id} className="bg-blue-100 dark:bg-[#1e3a5f] text-blue-700 dark:text-[#93c5fd] text-xs px-2 py-0.5 rounded">
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
                    className={`bg-bg-primary border rounded-lg px-4 py-3 flex items-center justify-between cursor-pointer transition-colors ${selectedBillId === b.id ? 'border-green-accent/50' : 'border-border-default hover:border-green-accent/30'}`}
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

// ─── Access Gate ─────────────────────────────────────────────────────────────

function AccessGate({ onUnlock }: { onUnlock: () => void }) {
  const [showModal, setShowModal] = useState(false);
  const [showAdminLogin, setShowAdminLogin] = useState(false);
  const [password, setPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');

  function handleAdminUnlock(e: React.FormEvent) {
    e.preventDefault();
    if (password === 'scout2026') {
      onUnlock();
    } else {
      setPasswordError('Incorrect password');
    }
  }

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <div className="max-w-md w-full">
        <div className="bg-bg-secondary border border-border-default rounded-2xl p-8 text-center space-y-5">
          <LockIcon className="text-4xl mx-auto text-text-muted" />
          <div>
            <span className="inline-block mb-2 text-[10px] uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
              Pro &amp; Enterprise
            </span>
            <h1 className="text-2xl font-bold text-text-primary mb-2">Portfolio Exposure</h1>
            <p className="text-text-muted text-sm leading-relaxed">
              See exactly which enacted laws hit your portfolio, what each one requires, and when your
              next deadline falls — the exposure translation compliance teams pay for.
            </p>
          </div>

          {!showAdminLogin && (
            <div className="space-y-3">
              <button
                onClick={() => setShowModal(true)}
                className="w-full bg-green-accent text-bg-primary font-semibold py-3 rounded-lg text-sm hover:opacity-90 transition-opacity"
              >
                Request access &amp; pricing →
              </button>
              <p className="text-text-muted text-xs">
                Or <Link href="/pricing" className="text-green-accent hover:underline">compare plans</Link>.
              </p>
              <button
                onClick={() => setShowAdminLogin(true)}
                className="text-text-muted text-xs underline hover:text-text-secondary"
              >
                Admin? Sign in
              </button>
            </div>
          )}

          {showModal && (
            <RequestAccessModal
              plan="company_impact"
              planLabel="Portfolio Exposure"
              source="company_gate"
              onClose={() => setShowModal(false)}
            />
          )}

          {showAdminLogin && (
            <form onSubmit={handleAdminUnlock} className="text-left space-y-3">
              <div className="flex flex-col gap-1">
                <label className="text-text-muted text-xs uppercase">Admin Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={e => { setPassword(e.target.value); setPasswordError(''); }}
                  placeholder="Enter password"
                  autoFocus
                  className="bg-bg-primary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
                />
                {passwordError && <div className="text-urgency-high text-xs">{passwordError}</div>}
              </div>
              <button
                type="submit"
                className="w-full bg-green-dark text-green-accent border border-green-accent/30 font-medium py-2 rounded-lg text-sm hover:opacity-90 transition-opacity"
              >
                Unlock
              </button>
              <button type="button" onClick={() => setShowAdminLogin(false)} className="text-text-muted text-xs underline hover:text-text-secondary">
                Cancel
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function CompanyImpactPage() {
  const [activeTab, setActiveTab] = useState<'obligations' | 'bill' | 'company'>('obligations');
  const [isAuthed, setIsAuthed] = useState(false);

  if (!isAuthed) {
    return <AccessGate onUnlock={() => setIsAuthed(true)} />;
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <DemoBanner />

      <GazetteHeader title="Portfolio Exposure" subtitle="Which enacted laws affect you, and when your next deadline falls" />

      {/* Tab switcher */}
      <div className="flex gap-1 bg-bg-secondary border border-border-default rounded-lg p-1 w-fit">
        {[
          { id: 'obligations' as const, label: 'Obligations & Deadlines' },
          { id: 'bill' as const, label: 'Cost Estimate (beta)' },
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

      {activeTab === 'obligations' ? <ObligationsView /> : activeTab === 'bill' ? <BillView /> : <CompanyView />}
    </div>
  );
}
