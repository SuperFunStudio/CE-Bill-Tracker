'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { fetchBillTextCoverage, fetchFeeSummary } from '@/lib/api';
import { track } from '@/lib/analytics';

// Developer docs — the public API surface, drafted for the "Developers — build on the data" buyer.
// Read endpoints are open + rate-limited today (no key); write/LLM endpoints (evaluate, ask) are Pro.
// Higher volume, commercial terms, and bulk/webhook access are lead-captured via the request modal.

// Same env var the rest of the app reads, so the pending api.atlascircular.com cutover is one
// environment change rather than a string edit here that would drift from what the client calls.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'https://signalscout-api-36712717703.us-central1.run.app';

// Real ids, verified against prod. A placeholder id here used to 404 (and, before that fix, 500) —
// the first request a developer copies out of our own docs has to succeed.
const EXAMPLE_BILL_ID = 72452; // OR SB-582, Recycling Modernization Act — a densely extracted record.

interface Endpoint {
  method: 'GET' | 'POST';
  path: string;
  desc: string;
  auth?: 'pro'; // undefined = open (rate-limited)
}

const GROUPS: { title: string; blurb: string; endpoints: Endpoint[] }[] = [
  {
    title: 'Bills',
    blurb: 'The core dataset — circular-economy bills across all 50 US states, the EU, and 35+ national jurisdictions, kept current with extracted compliance detail. compliance_details is served in full on the per-bill record, free and unauthenticated; the bulk list omits it.',
    endpoints: [
      { method: 'GET', path: '/bills', desc: 'List / filter bills. Params: ce_relevant, state, region, regions (CSV), status, instrument_type, material_category, policy_stance, urgency, limit, offset.' },
      { method: 'GET', path: '/bills/{id}', desc: 'One bill in full, including the extracted compliance_details (the 8 dimension envelopes).' },
      { method: 'GET', path: '/bills/search?q=', desc: 'Full-text search over persisted bill text; returns highlighted snippets.' },
      { method: 'GET', path: '/bills/outcomes', desc: 'Documented real-world outcomes attributable to enacted laws (each source-cited).' },
      { method: 'GET', path: '/bills/deadlines/upcoming', desc: 'Upcoming compliance deadlines extracted from enacted laws.' },
    ],
  },
  {
    title: 'Analytics',
    blurb: 'Pre-computed aggregates — the same series behind the Insights dashboards, ready to chart.',
    endpoints: [
      { method: 'GET', path: '/bills/timeline', desc: 'Bill counts per year by status (introduced → enacted). Counts distinct laws: acts that only amend another law are excluded unless include_amending=true. Params: instrument_type, material_category, regions, include_amending.' },
      { method: 'GET', path: '/bills/laws-in-force', desc: 'Enacted law totals per region, by year in force. Excludes amending acts unless include_amending=true.' },
      { method: 'GET', path: '/bills/stance-momentum', desc: 'Per-year counts by policy stance (advances / weakens / neutral).' },
      { method: 'GET', path: '/bills/instrument-material-matrix', desc: 'Coverage heatmap: bill counts per (policy instrument × material).' },
      { method: 'GET', path: '/bills/collection-target-basis', desc: 'How collection targets are measured (weight vs value-recovered vs …), per region.' },
      // /insights/state-gap and /insights/champions were listed here as open endpoints. They are now
      // admin-only (app/api/insights.py): both rest on OpenStates sponsor and vote data backfilled
      // for US states alone, so the analysis isn't finished enough to sell. Documenting an endpoint
      // that answers a developer with 403 is worse than not documenting it — they come back when the
      // coverage is real.
    ],
  },
  {
    title: 'Compliance & regulatory',
    blurb: 'The obligations behind the laws — fees, pathways, federal action, and litigation. Fee data comes in two layers: the amounts a law itself STATES (fee-amounts, cited to the enacting text) and curated per-material rate tables set by agency/PRO rulemaking (fee-schedule).',
    endpoints: [
      { method: 'GET', path: '/compliance/fee-amounts', desc: 'Producer fees a law states — per-tonne / per-unit / flat / %-revenue, each cited to a verbatim excerpt. US-only free; the full 40+ jurisdictions need an API plan.' },
      { method: 'GET', path: '/compliance/fee-amounts/summary', desc: 'Open aggregate: fee coverage counts by jurisdiction, kind, basis, and currency.' },
      { method: 'GET', path: '/compliance/eco-modulation', desc: 'Eco-modulation criteria (design attributes that raise/lower fees) per law, cited. US-only free; full set with an API plan.' },
      { method: 'GET', path: '/compliance/fee-schedule', desc: 'Curated per-material producer-fee rate tables + eco-modulation math (CA SB 54, UK pEPR, Japan) — the runnable rates set by agency/PRO rulemaking, not the statute.' },
      { method: 'GET', path: '/compliance/pathways', desc: 'The primary next-action per enacted law (join this PRO / file this plan).' },
      { method: 'GET', path: '/federal-actions', desc: 'Tracked federal regulatory actions (US).' },
      { method: 'GET', path: '/litigation-cases', desc: 'Circular-economy litigation cases; drill into a case for events.' },
    ],
  },
  {
    title: 'Analysis (AI)',
    blurb: 'Structured judgment over the corpus. These accept a request body and are Pro-gated (Bearer token).',
    endpoints: [
      { method: 'POST', path: '/research/ask', desc: 'Ask a natural-language question over the corpus; returns a cited answer + optional SQL-backed chart.', auth: 'pro' },
      { method: 'POST', path: '/evaluate/bill', desc: 'Score a draft or enacted bill against the regime baseline for its material — where it is strong, where it is thin.', auth: 'pro' },
    ],
  },
];

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-lg border border-border-default bg-bg-tertiary p-4 text-xs text-text-primary font-mono leading-relaxed">
      {children}
    </pre>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="font-serif text-xl text-text-primary border-b border-border-default pb-1">{title}</h2>
      {children}
    </section>
  );
}

/** What the corpus actually holds, read live from the two open aggregate endpoints rather than
 *  hardcoded — a stale number on a docs page is worse than no number. Renders nothing until both
 *  land, so a fetch failure degrades to the prose above instead of showing zeroes. */
function CorpusStats() {
  const [stats, setStats] = useState<{ label: string; value: string }[] | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([fetchBillTextCoverage(), fetchFeeSummary()])
      .then(([coverage, fees]) => {
        if (!live) return;
        setStats([
          { label: 'bills tracked', value: coverage.total_bills.toLocaleString() },
          { label: 'cited fee rates', value: fees.total_rate_entries.toLocaleString() },
          { label: 'jurisdictions with fee data', value: String(fees.by_region.length) },
          { label: 'currencies', value: String(fees.by_currency.length) },
        ]);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  if (!stats) return null;
  return (
    <dl className="grid grid-cols-2 sm:grid-cols-4 gap-px overflow-hidden rounded-lg border border-border-default bg-border-default">
      {stats.map(s => (
        <div key={s.label} className="bg-bg-tertiary px-3 py-3 text-center">
          <dt className="font-serif text-xl text-text-primary">{s.value}</dt>
          <dd className="text-[11px] uppercase tracking-wide text-text-muted mt-0.5 leading-tight">
            {s.label}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function DevelopersPage() {
  const [modal, setModal] = useState(false);

  function requestAccess() {
    track('cta_click', { plan: 'api', entry_source: 'developers' });
    setModal(true);
  }

  return (
    <div className="p-6 space-y-8 max-w-3xl mx-auto">
      <GazetteHeader
        title="Build on the data"
        subtitle="The Atlas Circular API — circular-economy legislation as structured, current data"
      />

      <p className="text-text-secondary leading-relaxed">
        Every bill, status, deadline, fee, and AI classification behind Atlas Circular is available
        over a plain REST/JSON API. <strong className="text-text-primary">Read endpoints are open and
        rate-limited</strong> — no key needed to start. For production volume, commercial terms, bulk
        exports, or webhooks, <button onClick={requestAccess} className="text-green-accent hover:underline">request
        API access</button> — see <Link href="/pricing" className="text-green-accent hover:underline">pricing</Link>.
      </p>

      <CorpusStats />

      <p className="text-text-secondary text-sm leading-relaxed">
        Extracted figures are <strong className="text-text-primary">grounded</strong>: every fee rate,
        target, and deadline carries a <code className="text-green-accent">source_excerpt</code> quoting
        the enacting text verbatim, so you can render the citation next to the number instead of asking
        your users to trust a model. Rows we could not tie back to statutory language are flagged rather
        than dropped.
      </p>

      <Section title="Base URL">
        <CodeBlock>{API_BASE}</CodeBlock>
        <p className="text-text-secondary text-sm leading-relaxed">
          Responses are JSON. All endpoints are versionless today; breaking changes will be announced to
          access-holders before they ship.
        </p>
      </Section>

      <Section title="Quickstart">
        <p className="text-text-secondary text-sm">The 25 most recent enacted EPR laws, newest first:</p>
        <CodeBlock>{`curl "${API_BASE}/bills?ce_relevant=true&status=enacted&limit=25"`}</CodeBlock>
        <p className="text-text-secondary text-sm">
          One bill in full — Oregon’s Recycling Modernization Act, with its extracted compliance detail:
        </p>
        <CodeBlock>{`curl "${API_BASE}/bills/${EXAMPLE_BILL_ID}"`}</CodeBlock>
        <p className="text-text-secondary text-sm leading-relaxed rounded-lg border border-border-default bg-bg-tertiary p-3">
          <strong className="text-text-primary">Note:</strong> list results omit{' '}
          <code className="text-green-accent">compliance_details</code> by design — the extraction is
          per-bill, and shipping it on every row of a bulk list would make the corpus-wide dataset a
          single call. Fetch it from <code className="text-green-accent">/bills/{'{id}'}</code>, which is
          free and needs no key. If the field looks missing, you’re reading a list response.
        </p>
      </Section>

      <Section title="Authentication & limits">
        <ul className="space-y-2 text-text-secondary text-sm leading-relaxed list-disc pl-5">
          <li><strong className="text-text-primary">Read endpoints</strong> need no auth — they are rate-limited per IP. Fine for prototyping, dashboards, and research.</li>
          <li><strong className="text-text-primary">Analysis endpoints</strong> (<code className="text-green-accent">POST /evaluate/bill</code>, <code className="text-green-accent">POST /research/ask</code>) run large-model inference and are Pro-gated — pass a Bearer token: <code className="text-green-accent">Authorization: Bearer &lt;token&gt;</code>.</li>
          <li><strong className="text-text-primary">Production use</strong> — higher rate limits, a stable SLA, bulk/webhook delivery, and commercial licensing come with an API plan. Usage-based pricing.</li>
        </ul>
      </Section>

      <Section title="Endpoints">
        <div className="space-y-6">
          {GROUPS.map(g => (
            <div key={g.title} className="space-y-2">
              <h3 className="font-serif text-base text-text-primary">{g.title}</h3>
              <p className="text-text-muted text-sm leading-relaxed">{g.blurb}</p>
              <div className="divide-y divide-border-default rounded-lg border border-border-default">
                {g.endpoints.map(e => (
                  <div key={e.path} className="grid grid-cols-[3rem_1fr] gap-3 px-3 py-2.5">
                    <span className={`text-[10px] font-mono font-semibold self-start mt-0.5 ${e.method === 'POST' ? 'text-amber-400' : 'text-green-accent'}`}>
                      {e.method}
                    </span>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <code className="text-xs text-text-primary font-mono">{e.path}</code>
                        {e.auth === 'pro' && (
                          <span className="text-[10px] uppercase tracking-wide rounded-full bg-amber-400/15 text-amber-400 px-2 py-0.5">Pro</span>
                        )}
                      </div>
                      <p className="text-xs text-text-secondary mt-0.5 leading-snug">{e.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Example response">
        <p className="text-text-secondary text-sm">
          <code className="text-green-accent">GET /bills/{EXAMPLE_BILL_ID}</code> returns the bill plus its
          extracted compliance envelopes — abridged here, but every field below is verbatim from the live
          response:
        </p>
        <CodeBlock>{`{
  "id": ${EXAMPLE_BILL_ID},
  "region": "US",
  "state": "OR",
  "bill_number": "SB-582",
  "title": "Relating to modernizing Oregon's recycling system.",
  "status": "enacted",
  "instrument_type": "epr",
  "compliance_details": {
    "extraction_version": 5,
    "collection_targets": {
      "status": "present",
      "targets": [
        { "material": "Plastic", "percent": 25, "by_year": "2028", "basis": "material_specific" },
        { "material": "Plastic", "percent": 50, "by_year": "2040", "basis": "material_specific" },
        { "material": "Plastic", "percent": 70, "by_year": "2050", "basis": "material_specific" }
      ],
      "source_excerpt": "It is the goal of the State of Oregon that the statewide recycling rate
                         for plastic be: (A) At least 25 percent by calendar year 2028…"
    },
    "pro_structure": { "status": "present", "model": "competitive_pros", "source_excerpt": "…" },
    "eco_modulation": {
      "status": "present",
      "criteria": ["Post-consumer recycled content", "Product-to-package ratio", "Recyclability"],
      "source_excerpt": "…"
    }
    // …fee_amounts, penalties, recycled_content, bans_restrictions, labeling
  }
}`}</CodeBlock>
        <p className="text-text-muted text-xs leading-relaxed">
          Each envelope carries a <code className="text-green-accent">status</code> of{' '}
          <code className="text-green-accent">present</code>,{' '}
          <code className="text-green-accent">absent</code>, or{' '}
          <code className="text-green-accent">not_applicable</code> — so a dimension a law genuinely
          does not address is distinguishable from one we have not extracted.
        </p>
      </Section>

      <section className="border-t border-border-default pt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="max-w-xl">
          <h3 className="font-serif text-lg text-text-primary mb-1">Ready for production?</h3>
          <p className="text-text-secondary text-sm leading-relaxed">
            Tell us your use case and volume — we’ll set you up with an API plan, higher limits, and
            commercial terms. See <Link href="/pricing" className="text-green-accent hover:underline">pricing</Link>.
          </p>
        </div>
        <button
          onClick={requestAccess}
          className="shrink-0 rounded-lg border border-green-accent bg-green-dark px-5 py-2.5 font-serif text-green-accent font-medium hover:opacity-90 transition-opacity"
        >
          Request API access →
        </button>
      </section>

      {modal && (
        <RequestAccessModal plan="api" planLabel="API" source="developers" onClose={() => setModal(false)} />
      )}
    </div>
  );
}
