'use client';
import { useState, useMemo } from 'react';
import { useBills } from '@/hooks/useBills';
import { useCompanies, useCompany, useExposureRanking, useExposureBrief } from '@/hooks/useCompanies';
import { MetricCard } from '@/components/ui/MetricCard';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { ScoreBadge } from '@/components/ui/ScoreBadge';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { formatCost, fixEncoding, scoreColor } from '@/lib/utils';

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
                      {sp.is_primary && <span className="text-green-accent ml-1">★</span>}
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

// ─── Request Access Form ─────────────────────────────────────────────────────

function RequestAccessForm({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <div className="text-center space-y-3 py-4">
        <div className="text-green-accent text-3xl">✓</div>
        <div className="text-text-primary font-semibold">Request received!</div>
        <div className="text-text-muted text-sm">We&apos;ll be in touch at <span className="text-text-secondary">{email}</span>.</div>
        <button onClick={onClose} className="text-text-muted text-xs underline hover:text-text-secondary mt-2">Close</button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex flex-col gap-1">
        <label className="text-text-muted text-xs uppercase">Name</label>
        <input
          type="text"
          required
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="Your name"
          className="bg-bg-primary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-text-muted text-xs uppercase">Work Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@company.com"
          className="bg-bg-primary border border-border-default rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
        />
      </div>
      <button
        type="submit"
        className="w-full bg-green-accent text-bg-primary font-semibold py-2 rounded-lg text-sm hover:opacity-90 transition-opacity"
      >
        Request Access
      </button>
    </form>
  );
}

// ─── Access Gate ─────────────────────────────────────────────────────────────

function AccessGate({ onUnlock }: { onUnlock: () => void }) {
  const [showForm, setShowForm] = useState(false);
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
          <div className="text-4xl">🔒</div>
          <div>
            <h1 className="text-2xl font-bold text-text-primary mb-2">Company Impact Analysis</h1>
            <p className="text-text-muted text-sm leading-relaxed">
              See your company&apos;s exposure to upcoming legislation and emerging opportunities.
            </p>
          </div>

          {!showForm && !showAdminLogin && (
            <div className="space-y-3">
              <button
                onClick={() => setShowForm(true)}
                className="w-full bg-green-accent text-bg-primary font-semibold py-3 rounded-lg text-sm hover:opacity-90 transition-opacity"
              >
                Request Access
              </button>
              <button
                onClick={() => setShowAdminLogin(true)}
                className="text-text-muted text-xs underline hover:text-text-secondary"
              >
                Admin? Sign in
              </button>
            </div>
          )}

          {showForm && (
            <div className="text-left">
              <RequestAccessForm onClose={() => setShowForm(false)} />
              <button onClick={() => setShowForm(false)} className="text-text-muted text-xs underline hover:text-text-secondary mt-3">
                Cancel
              </button>
            </div>
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
  const [activeTab, setActiveTab] = useState<'bill' | 'company'>('bill');
  const [isAuthed, setIsAuthed] = useState(false);

  if (!isAuthed) {
    return <AccessGate onUnlock={() => setIsAuthed(true)} />;
  }

  return (
    <div className="p-6 space-y-6">
      <DemoBanner />

      <div>
        <h1 className="text-2xl font-bold text-text-primary mb-1">Company Impact</h1>
        <p className="text-text-muted text-sm">Estimated EPR compliance exposure by company and bill</p>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 bg-bg-secondary border border-border-default rounded-lg p-1 w-fit">
        {[
          { id: 'bill' as const, label: 'Bill View' },
          { id: 'company' as const, label: 'Company View' },
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

      {activeTab === 'bill' ? <BillView /> : <CompanyView />}
    </div>
  );
}
