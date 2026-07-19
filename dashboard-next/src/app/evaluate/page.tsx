'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/components/auth/AuthContext';
import { evaluateBill, fetchMaterialMap } from '@/lib/api';
import { dimensionMap, dimensionStatus, DIMENSION_LABELS } from '@/lib/dimensions';
import { MaterialPositionMap } from '@/components/insights/MaterialPositionMap';
import type {
  EvaluateResponse, RequirementResult, CorpusCrossCheck, CorpusAnalog, MaterialMapPoint,
} from '@/lib/types';

// "Evaluate a Bill" (Pro) — paste a draft/enacted measure; it's run through the same SonnetExtractor as
// the corpus, its target material is positioned into a regime (incremental-viable vs critical-mass), and
// its extracted mechanisms are scored against the baseline that regime demands. Strength is a *fit*:
// a lean battery bill and a heavy textiles bill can both be strong because each matches its own playbook.

const SAMPLE_TITLE = 'Responsible Textile Recovery Act (SB 707)';
const SAMPLE_TEXT =
  'This act establishes an extended producer responsibility program for apparel and textile articles. ' +
  'Producers of covered textile products must join a producer responsibility organization, which shall ' +
  'submit a plan for the collection, transportation, sorting, repair, reuse, and recycling of covered ' +
  'products. The program shall provide convenient collection locations statewide. Producers shall pay ' +
  'fees to the PRO to fund the program, with fees eco-modulated based on durability, repairability, and ' +
  'recycled content. The plan shall include collection targets measured by weight of textiles diverted.';

const BAND_STYLE: Record<string, string> = {
  strong: 'text-green-accent border-green-accent/40',
  moderate: 'text-amber-400 border-amber-400/40',
  weak: 'text-error border-error/40',
};
const STATUS_STYLE: Record<string, { dot: string; label: string }> = {
  met: { dot: 'bg-green-accent', label: 'In place' },
  partial: { dot: 'bg-amber-400', label: 'Partial' },
  missing: { dot: 'bg-error', label: 'Missing' },
};
const IMPORTANCE_LABEL: Record<string, string> = {
  load_bearing: 'Load-bearing', supporting: 'Supporting', bonus: 'Bonus',
};

function RegimeCard({ regime }: { regime: EvaluateResponse['regime'] }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-4 space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <span className="text-text-secondary text-xs font-semibold uppercase tracking-wide">Material regime</span>
          <div className="text-text-primary font-serif text-lg">{regime.label}</div>
        </div>
        <div className="text-right">
          <div className="text-sm text-text-primary">{regime.material}</div>
          {regime.confidence === 'estimated' && <div className="text-xs text-amber-400">axes estimated from bill text</div>}
          {regime.confidence === 'low' && <div className="text-xs text-amber-400">positioning uncertain</div>}
        </div>
      </div>
      <p className="text-sm text-text-secondary leading-relaxed">{regime.rationale}</p>
    </div>
  );
}

// Dimension-by-dimension: the draft's extracted envelopes vs the strong model bill for its regime.
function DimensionDiff({ draft, baseline }: { draft: EvaluateResponse['compliance_details']; baseline: EvaluateResponse['baseline_details'] }) {
  const dMap = dimensionMap(draft), bMap = dimensionMap(baseline);
  return (
    <div className="space-y-2">
      <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
        Your bill vs. the strong baseline, dimension by dimension
      </div>
      <div className="divide-y divide-border-default rounded-lg border border-border-default">
        {Object.keys(DIMENSION_LABELS).map(key => {
          const d = dMap[key], b = bMap[key];
          const baseStatus = dimensionStatus(baseline, key);
          const notRequired = baseStatus === 'not_applicable';
          const gap = !!b && !d;  // baseline expects it, draft doesn't have it
          return (
            <div key={key} className="grid grid-cols-[8rem_1fr_1fr] gap-2 px-3 py-2 text-xs">
              <div className="text-text-secondary font-medium flex items-center gap-1.5">
                {gap && <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" title="gap vs baseline" />}
                {DIMENSION_LABELS[key]}
              </div>
              <div className={d ? 'text-text-primary' : 'text-text-muted italic'}>
                {d ? d.summary : 'Not addressed'}
              </div>
              <div className={notRequired ? 'text-text-muted italic' : 'text-text-secondary'}>
                {notRequired ? 'Not required in this regime' : b ? b.summary : '—'}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex gap-4 px-1 text-[10px] text-text-muted">
        <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-amber-400" /> gap vs baseline</span>
        <span>middle column: your bill · right column: strong model bill</span>
      </div>
    </div>
  );
}

function RequirementRow({ r }: { r: RequirementResult }) {
  const s = STATUS_STYLE[r.status];
  return (
    <div className="py-1.5">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full shrink-0 ${s.dot}`} />
        <span className="text-body text-text-primary font-medium">{r.label}</span>
        <span className="text-[10px] uppercase tracking-wide text-text-muted">{IMPORTANCE_LABEL[r.importance]}</span>
        <span className="ml-auto text-xs text-text-secondary">{s.label}</span>
      </div>
      <div className="pl-4 mt-1 grid gap-1 text-xs sm:grid-cols-2">
        <div className="text-text-secondary"><span className="text-text-muted">This bill: </span>{r.your_value}</div>
        <div className="text-text-secondary"><span className="text-text-muted">Strong baseline: </span>{r.baseline}</div>
      </div>
    </div>
  );
}

const OUTCOME_STYLE: Record<string, string> = {
  positive: 'text-green-accent', negative: 'text-error', mixed: 'text-amber-400',
};

function AnalogCard({ a }: { a: CorpusAnalog }) {
  const metCount = Object.values(a.mechanisms).filter(v => v === 'met').length;
  const total = Object.keys(a.mechanisms).length;
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-green-accent text-sm">{a.state} {a.bill_number}</span>
        {a.year && <span className="text-text-muted text-xs">{a.year}</span>}
        {a.same_material
          ? <span className="text-[10px] uppercase tracking-wide rounded-full bg-green-accent/15 text-green-accent px-2 py-0.5">same material</span>
          : <span className="text-[10px] uppercase tracking-wide text-text-muted">{a.material}</span>}
        {a.reviewed && <span className="text-[10px] uppercase tracking-wide text-text-muted">reviewed</span>}
        <span className="ml-auto text-xs text-text-secondary">{metCount}/{total} mechanisms</span>
      </div>
      {a.title && <p className="text-sm text-text-secondary leading-snug">{a.title}</p>}
      {a.outcomes.length > 0 && (
        <div className="space-y-1 border-t border-border-default pt-2">
          {a.outcomes.map((o, i) => (
            <div key={i} className="text-xs leading-snug">
              <span className={`font-semibold ${OUTCOME_STYLE[o.direction] ?? ''}`}>
                {o.metric || o.direction}
              </span>
              <span className="text-text-secondary"> — {o.summary}</span>
              {o.source_url && (
                <a href={o.source_url} target="_blank" rel="noreferrer" className="text-text-muted hover:text-text-primary ml-1">
                  ({o.source_name || 'source'})
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CrossCheck({ corpus }: { corpus: CorpusCrossCheck }) {
  return (
    <div className="space-y-4 border-t border-border-default pt-6">
      <div>
        <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
          How this might land — vs. enacted laws in this regime
        </div>
        <p className="text-xs text-text-muted mt-1 leading-relaxed">{corpus.note}</p>
      </div>

      {/* Did the laws that got enacted carry each mechanism? — analog share vs your draft. */}
      <div className="space-y-2">
        {corpus.baseline.map(b => {
          const s = STATUS_STYLE[b.your_status];
          return (
            <div key={b.key} className="flex items-center gap-3">
              <div className="w-48 shrink-0 text-xs text-text-secondary text-right">{b.label}</div>
              <div className="flex-1 h-4 rounded bg-bg-tertiary overflow-hidden">
                <div className="h-full rounded bg-green-accent/50" style={{ width: `${Math.round(b.analog_share * 100)}%` }} />
              </div>
              <div className="w-12 shrink-0 text-xs text-text-muted font-mono">{Math.round(b.analog_share * 100)}%</div>
              <div className="w-24 shrink-0 flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${s.dot}`} />
                <span className="text-xs text-text-secondary">you: {s.label.toLowerCase()}</span>
              </div>
            </div>
          );
        })}
      </div>
      {corpus.value_basis_share != null && (
        <p className="text-xs text-text-secondary">
          <span className="text-text-muted">Value-aligned targets: </span>
          {Math.round(corpus.value_basis_share * 100)}% of these enacted analogs measure recovery by value
          recovered / material-specific rather than raw weight.
        </p>
      )}

      {corpus.analogs.length > 0 && (
        <div className="space-y-2">
          <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
            Closest enacted analogs ({corpus.analogs.length})
          </div>
          <div className="grid gap-2">
            {corpus.analogs.map(a => <AnalogCard key={`${a.bill_id}-${a.bill_number}`} a={a} />)}
          </div>
        </div>
      )}
    </div>
  );
}

function Result({ data, mapPoints }: { data: EvaluateResponse; mapPoints: MaterialMapPoint[] }) {
  return (
    <div className="space-y-5 border-t border-border-default pt-6">
      {/* Score + regime */}
      <div className="grid gap-4 sm:grid-cols-[auto_1fr] sm:items-stretch">
        <div className={`rounded-lg border p-4 flex flex-col items-center justify-center min-w-[120px] ${BAND_STYLE[data.score.band]}`}>
          <div className="text-4xl font-mono font-semibold">{data.score.value}</div>
          <div className="text-xs uppercase tracking-wide mt-1">{data.score.band} fit</div>
        </div>
        <div className="flex items-center">
          <p className="text-sm text-text-secondary leading-relaxed">{data.score.summary}</p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 sm:items-start">
        <RegimeCard regime={data.regime} />
        {mapPoints.length > 0 && (
          <MaterialPositionMap
            points={mapPoints} highlight={data.regime.material}
            highlightAxes={data.regime.axes} confidence={data.regime.confidence}
          />
        )}
      </div>

      {/* Flags */}
      {data.flags.length > 0 && (
        <div className="space-y-2">
          {data.flags.map((f, i) => (
            <p key={i} className="rounded-lg border border-amber-400/30 bg-amber-400/5 px-3 py-2 text-sm text-text-secondary leading-relaxed">
              {f}
            </p>
          ))}
        </div>
      )}

      {/* Mechanism-by-mechanism vs the regime baseline */}
      <div className="space-y-1">
        <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide mb-1">
          Mechanisms vs. the {data.regime.label.toLowerCase()} baseline
        </div>
        {data.requirements.map(r => <RequirementRow key={r.key} r={r} />)}
      </div>

      {/* Envelope-to-envelope diff against the strong model bill for this regime */}
      <DimensionDiff draft={data.compliance_details} baseline={data.baseline_details} />

      {/* Grounding: the draft against enacted laws in the same regime + what landed */}
      {data.corpus && <CrossCheck corpus={data.corpus} />}
    </div>
  );
}

export default function EvaluatePage() {
  const { isAdmin, getToken, openAuth, loading: authLoading } = useAuth();
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [result, setResult] = useState<EvaluateResponse | null>(null);
  const [mapPoints, setMapPoints] = useState<MaterialMapPoint[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The material map is static reference data — fetch once, reuse across evaluations.
  useEffect(() => { fetchMaterialMap().then(setMapPoints).catch(() => {}); }, []);

  async function run() {
    if (text.trim().length < 200 || busy) return;
    if (!isAdmin) { openAuth(); return; }
    setBusy(true); setError(null); setResult(null);
    try {
      const token = await getToken();
      setResult(await evaluateBill(
        { text: text.trim(), title: title.trim() || undefined, jurisdiction: jurisdiction.trim() || undefined },
        token,
      ));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  function loadSample() {
    setTitle(SAMPLE_TITLE); setJurisdiction('CA'); setText(SAMPLE_TEXT);
  }

  // Hidden internal tool: gated to admins while we watch for demand before folding it into Ask.
  // A signed-in non-admin gets a plain not-available message, not a hint that this exists.
  if (authLoading || !isAdmin) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10">
        <p className="mt-20 text-center text-text-muted text-sm italic">
          {authLoading ? 'Checking access…' : 'This page is not available.'}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10 space-y-6">
      <div>
        <p className="text-[rgb(var(--green-accent))] text-xs font-semibold uppercase tracking-wider">Evaluate a Bill</p>
        <h1 className="font-serif text-2xl text-text-primary mt-1">How would this bill land?</h1>
        <p className="text-text-secondary text-body mt-2 leading-relaxed">
          Paste a draft or enacted measure. We read it into the same compliance dimensions as every tracked
          bill, figure out which <span className="text-text-primary">intervention regime</span> its target
          material demands — a lean fee fix for high-value materials that already circulate, or engineered
          critical mass for dispersed low-value ones — and score whether the bill carries the mechanisms that
          regime needs. Strength is a <em>fit</em>, not a checklist.
        </p>
      </div>

      <div className="space-y-3">
        <div className="flex gap-3">
          <input
            value={title} onChange={e => setTitle(e.target.value)} placeholder="Bill title (optional)"
            className="flex-1 rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
          />
          <input
            value={jurisdiction} onChange={e => setJurisdiction(e.target.value)} placeholder="Jurisdiction (e.g. CA)"
            className="w-40 rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent"
          />
        </div>
        <textarea
          value={text} onChange={e => setText(e.target.value)}
          placeholder="Paste the bill's operative text — covered products, collection targets, fees, PRO structure, obligations…"
          rows={8}
          className="w-full rounded-lg border border-border-default bg-bg-primary px-4 py-3 text-body text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent resize-none"
        />
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-xs text-text-muted">Pro feature</span>
            <button onClick={loadSample} className="text-xs text-green-accent hover:underline">Load a sample</button>
          </div>
          <button
            onClick={run}
            disabled={busy || text.trim().length < 200}
            className="rounded-full bg-green-accent px-5 py-2 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {busy ? 'Analyzing…' : 'Evaluate'}
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-error">{error}</p>}
      {busy && <div className="h-40 w-full animate-pulse rounded-lg bg-bg-tertiary" />}
      {result && <Result data={result} mapPoints={mapPoints} />}
    </div>
  );
}
