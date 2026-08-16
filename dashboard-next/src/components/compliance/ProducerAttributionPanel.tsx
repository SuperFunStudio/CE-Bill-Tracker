'use client';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { track } from '@/lib/analytics';
import {
  fetchProducerAttribution,
  REGIME_LABELS,
  SOURCING_LABELS,
  type AttributionRegime,
  type AttributionSourcing,
  type ProducerAttributionRow,
} from '@/lib/producerAttribution';

// Sentinel for "my jurisdiction isn't listed" — deliberately a visible choice, not a fallthrough,
// so the unknown card is something the reader asked for and reads as an answer.
const OTHER = '__other__';

const CONFIDENCE_HINTS: Record<string, string> = {
  statutory: 'written in the statute itself',
  regulatory: 'set by regulation — easier to amend than a statute',
  guidance: 'agency guidance — binds nobody',
  unresolved: 'no authority has settled this yet',
};

/**
 * "Who is the producer?" — the attribution answer, cited to the article. One card per lookup:
 * jurisdiction × regime × (franchised, sourcing), rendered from the hand-researched table behind
 * GET /compliance/producer-attribution.
 *
 * The absent-row contract is load-bearing: a combination the table doesn't cover renders as an
 * explicit "unknown — verify yourself" card, NEVER as "not obligated". Silence is not an exemption.
 */
export function ProducerAttributionPanel() {
  const [regime, setRegime] = useState<AttributionRegime>('packaging_epr');
  const [jurisdiction, setJurisdiction] = useState<string>('');
  const [franchised, setFranchised] = useState(false);
  const [sourcing, setSourcing] = useState<AttributionSourcing | ''>('');

  const { data, isLoading } = useQuery({
    queryKey: ['producer-attribution', regime, franchised, sourcing],
    queryFn: () => fetchProducerAttribution({ regime, franchised, sourcing: sourcing || null }),
    staleTime: 30 * 60 * 1000, // curated in-code table; changes only on deploy
  });

  const rows = useMemo(
    () => [...(data?.rows ?? [])].sort((a, b) => a.jurisdiction_label.localeCompare(b.jurisdiction_label)),
    [data],
  );
  const row = jurisdiction && jurisdiction !== OTHER
    ? rows.find(r => r.jurisdiction === jurisdiction) ?? null
    : null;

  const pick = (code: string) => {
    setJurisdiction(code);
    if (code) track('attribution_lookup', { regime, jurisdiction: code, franchised });
  };

  const controlCls =
    'bg-bg-primary border border-border-default rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-green-accent';

  return (
    <section className="rounded-xl border border-border-default bg-bg-tertiary/30 p-5">
      <h2 className="font-serif text-2xl text-text-primary">Who is the producer?</h2>
      <p className="text-text-secondary text-sm mt-1">
        The party that owes the obligation differs by jurisdiction and by regime — and the answer is
        written in the law. Pick your situation to see the rule, cited to the article it lives in.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="flex items-center gap-1.5 text-xs text-text-muted uppercase tracking-wider">
          Regime
          <select
            value={regime}
            onChange={e => { setRegime(e.target.value as AttributionRegime); setJurisdiction(''); }}
            className={controlCls}
          >
            {Object.entries(REGIME_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-xs text-text-muted uppercase tracking-wider">
          Where you sell
          <select value={jurisdiction} onChange={e => pick(e.target.value)} className={controlCls}>
            <option value="">Choose…</option>
            {rows.map(r => (
              <option key={r.jurisdiction} value={r.jurisdiction}>{r.jurisdiction_label}</option>
            ))}
            <option value={OTHER}>Somewhere else…</option>
          </select>
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={franchised}
            onChange={e => setFranchised(e.target.checked)}
            className="accent-green-accent"
          />
          We franchise
        </label>
        <label className="flex items-center gap-1.5 text-xs text-text-muted uppercase tracking-wider">
          Sourcing
          <select
            value={sourcing}
            onChange={e => setSourcing(e.target.value as AttributionSourcing | '')}
            className={controlCls}
          >
            <option value="">Not sure</option>
            {Object.entries(SOURCING_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4">
        {!jurisdiction ? (
          data && (
            <p className="text-xs text-text-muted">
              Cited rules for {rows.length} jurisdiction{rows.length === 1 ? '' : 's'} under{' '}
              {REGIME_LABELS[regime]} · researched {data.coverage.researched}. Anything not listed is
              unknown to us — not exempt.
            </p>
          )
        ) : isLoading ? (
          <p className="text-sm text-text-muted">Looking it up…</p>
        ) : row ? (
          <AttributionCard row={row} sourcing={sourcing || null} />
        ) : (
          <UnknownCard regime={regime} />
        )}
      </div>
    </section>
  );
}

function AttributionCard({ row, sourcing }: { row: ProducerAttributionRow; sourcing: AttributionSourcing | null }) {
  const conf = row.confidence;
  const confHint = CONFIDENCE_HINTS[conf] ?? '';
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-4 space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-text-primary font-semibold">
          {row.jurisdiction_label} · {row.liable_party ?? row.rule.replace(/_/g, ' ')}
        </h3>
        <span
          title={confHint}
          className={`text-meta uppercase tracking-wider rounded-full border px-1.5 py-px ${
            conf === 'statutory'
              ? 'border-green-accent/40 text-green-accent'
              : conf === 'unresolved'
                ? 'border-urgency-high/40 text-urgency-high'
                : 'border-border-default text-text-secondary'
          }`}
        >
          {conf}
        </span>
      </div>

      <p className="text-sm text-text-secondary">{row.because}</p>

      <p className="text-xs text-text-muted">
        {row.source_url ? (
          <a href={row.source_url} target="_blank" rel="noopener noreferrer" className="text-green-accent hover:underline">
            {row.citation}
          </a>
        ) : (
          row.citation
        )}
      </p>

      {row.quote && (
        <details>
          <summary className="cursor-pointer text-xs text-text-muted hover:text-text-primary">
            What the law says, verbatim →
          </summary>
          <blockquote className="mt-2 border-l-2 border-green-accent/40 pl-3 text-sm italic text-text-secondary">
            {row.quote}
          </blockquote>
        </details>
      )}

      {row.threshold_summary && (
        <p className="text-sm text-text-secondary">
          <span className="text-text-primary font-medium">Size thresholds:</span> {row.threshold_summary}
        </p>
      )}

      {row.exemptions.length > 0 && (
        <p className="text-sm text-text-secondary">
          <span className="text-text-primary font-medium">Exemptions:</span>{' '}
          {row.exemptions.map(e => e.label ?? e.detail).filter(Boolean).join(' · ')}
        </p>
      )}

      {row.sourcing_sensitive && !sourcing && (
        <p className="text-xs text-urgency-medium">
          In this jurisdiction the answer flips on your sourcing route — set “Sourcing” above for
          the branch that applies to you.
        </p>
      )}

      {row.open_questions.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs text-text-muted hover:text-text-primary">
            {row.open_questions.length} open question{row.open_questions.length === 1 ? '' : 's'} we
            haven&apos;t resolved →
          </summary>
          <ul className="mt-2 list-disc pl-5 text-xs text-text-muted space-y-1">
            {row.open_questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </details>
      )}

      <p className="text-meta text-text-muted">
        Cited from primary sources; not legal advice. Confirm with counsel before you rely on it.
      </p>
    </div>
  );
}

/** The absent-row answer. Amber and explicit: unknown must not look safe. */
function UnknownCard({ regime }: { regime: AttributionRegime }) {
  return (
    <div className="rounded-lg border border-urgency-medium/40 bg-bg-primary p-4 space-y-2">
      <h3 className="text-urgency-medium font-semibold">Unknown — we hold no cited rule here</h3>
      <p className="text-sm text-text-secondary">
        We haven&apos;t researched who owes the {REGIME_LABELS[regime].toLowerCase()} obligation in
        that jurisdiction, so we won&apos;t guess. That is <em>not</em> the same as being exempt —
        verify with the regulator or counsel before assuming anything.
      </p>
    </div>
  );
}
