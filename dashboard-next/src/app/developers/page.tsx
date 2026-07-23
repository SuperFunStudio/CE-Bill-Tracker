'use client';

import { useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { RequestAccessModal } from '@/components/access/RequestAccessModal';
import { track } from '@/lib/analytics';

// Developer docs — the public API surface, drafted for the "Developers — build on the data" buyer.
// Read endpoints are open + rate-limited today (no key); write/LLM endpoints (evaluate, ask) are Pro.
// Higher volume, commercial terms, and bulk/webhook access are lead-captured via the request modal.

const API_BASE = 'https://signalscout-api-36712717703.us-central1.run.app';

interface Endpoint {
  method: 'GET' | 'POST';
  path: string;
  desc: string;
  auth?: 'pro'; // undefined = open (rate-limited)
}

const GROUPS: { title: string; blurb: string; endpoints: Endpoint[] }[] = [
  {
    title: 'Bills',
    blurb: 'The core dataset — circular-economy bills across all 50 US states, the EU, and 25+ national jurisdictions, kept current with extracted compliance detail.',
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
      { method: 'GET', path: '/bills/timeline', desc: 'Bill counts per year by status (introduced → enacted). Params: instrument_type, material_category, regions.' },
      { method: 'GET', path: '/bills/laws-in-force', desc: 'Cumulative enacted laws in force over time, per region.' },
      { method: 'GET', path: '/bills/stance-momentum', desc: 'Per-year counts by policy stance (advances / weakens / neutral).' },
      { method: 'GET', path: '/bills/instrument-material-matrix', desc: 'Coverage heatmap: bill counts per (policy instrument × material).' },
      { method: 'GET', path: '/bills/collection-target-basis', desc: 'How collection targets are measured (weight vs value-recovered vs …), per region.' },
      { method: 'GET', path: '/insights/state-gap', desc: 'Each US state’s CE passage rate vs its all-bills baseline.' },
      { method: 'GET', path: '/insights/champions', desc: 'Legislators leading CE bills, ranked; drill into their bills.' },
    ],
  },
  {
    title: 'Compliance & regulatory',
    blurb: 'The obligations behind the laws — fees, pathways, federal action, and litigation.',
    endpoints: [
      { method: 'GET', path: '/compliance/fee-schedule', desc: 'Producer-fee estimates with citations grounded in enacted text.' },
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

export default function DevelopersPage() {
  const [modal, setModal] = useState(false);

  function requestAccess() {
    track('cta_click', { plan: 'api', source: 'developers' });
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
        API access</button>.
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
        <p className="text-text-secondary text-sm">One bill in full, with extracted compliance detail:</p>
        <CodeBlock>{`curl "${API_BASE}/bills/12345"`}</CodeBlock>
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
        <p className="text-text-secondary text-sm"><code className="text-green-accent">GET /bills/{'{id}'}</code> returns the bill plus its extracted compliance envelopes:</p>
        <CodeBlock>{`{
  "id": 12345,
  "region": "US",
  "state": "CA",
  "bill_number": "SB 54",
  "title": "Plastic Pollution Producer Responsibility Act",
  "status": "enacted",
  "instrument_type": "epr",
  "material_categories": ["plastic packaging"],
  "compliance_details": {
    "collection_targets": {
      "status": "present",
      "targets": [{ "material": "packaging", "percent": 65, "by_year": "2032", "basis": "weight" }]
    },
    "pro_structure": { "status": "present", "model": "single_pro" },
    "eco_modulation": { "status": "present", "criteria": ["recyclability", "recycled_content"] }
    // …fee_amounts, penalties, recycled_content, bans_restrictions, labeling
  }
}`}</CodeBlock>
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
