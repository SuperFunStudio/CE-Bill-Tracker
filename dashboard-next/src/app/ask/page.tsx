'use client';

import { useState } from 'react';
import { useAuth } from '@/components/auth/AuthContext';
import { askResearch } from '@/lib/api';
import type { ResearchAnswer } from '@/lib/types';

// "Ask the Bills" (Pro) — a natural-language question over the extracted corpus. The answer is
// grounded in retrieved bills + SQL aggregates server-side (numbers are exact, claims are cited);
// this page just drives the prompt and renders the result. Upload-and-compare is a later mode.

const EXAMPLES = [
  'Do bills measure collection targets by weight or by value recovered?',
  'Which compliance dimensions are most common across bills?',
  'What design attributes do bills eco-modulate fees on?',
  'Which bills ban PFAS in packaging?',
];

/** Render answer text with minimal formatting: **bold** spans, one paragraph per line. */
function AnswerText({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-body text-text-primary leading-relaxed">
      {text.split('\n').filter(l => l.trim()).map((line, i) => {
        const parts = line.split(/(\*\*[^*]+\*\*)/g);
        return (
          <p key={i} className={line.trimStart().startsWith('- ') ? 'pl-4 -indent-4' : ''}>
            {parts.map((p, j) =>
              p.startsWith('**') && p.endsWith('**')
                ? <strong key={j} className="text-text-primary font-semibold">{p.slice(2, -2)}</strong>
                : <span key={j}>{p}</span>,
            )}
          </p>
        );
      })}
    </div>
  );
}

function AnswerChart({ title, bars }: { title: string; bars: { label: string; value: number }[] }) {
  const max = Math.max(1, ...bars.map(b => b.value));
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-4 space-y-3">
      <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">{title}</div>
      <div className="space-y-2">
        {bars.map(b => (
          <div key={b.label} className="flex items-center gap-3">
            <div className="w-48 shrink-0 text-xs text-text-secondary text-right">{b.label}</div>
            <div className="flex-1 h-4 rounded bg-bg-tertiary overflow-hidden">
              <div className="h-full rounded bg-green-accent/70" style={{ width: `${(b.value / max) * 100}%` }} />
            </div>
            <div className="w-10 shrink-0 text-xs text-text-primary font-mono">{b.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AskPage() {
  // Admin-gated for now (dogfooding in prod before it opens to Pro). To graduate to a Pro feature,
  // swap isAdmin→isPro here, flip the endpoint's require_admin→require_pro, and drop the nav adminOnly.
  const { isAdmin, getToken, loading: authLoading } = useAuth();
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<ResearchAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(q: string) {
    const trimmed = q.trim();
    if (trimmed.length < 3 || busy || !isAdmin) return;
    setBusy(true); setError(null); setAnswer(null);
    try {
      const token = await getToken();
      setAnswer(await askResearch(trimmed, token));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) return null;
  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center">
        <p className="text-text-secondary">This feature isn&apos;t available yet.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10 space-y-6">
      <div>
        <p className="text-[rgb(var(--green-accent))] text-xs font-semibold uppercase tracking-wider">Ask the Bills</p>
        <h1 className="font-serif text-2xl text-text-primary mt-1">Question the whole corpus</h1>
        <p className="text-text-secondary text-body mt-2 leading-relaxed">
          Ask an analytical question across every tracked bill. Answers are grounded in the bills&apos;
          extracted compliance data and cite the specific measures behind each claim — and where the
          question is a counting question, the numbers come straight from the database.
        </p>
      </div>

      <form onSubmit={e => { e.preventDefault(); ask(question); }} className="space-y-3">
        <textarea
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask(question); }}
          placeholder="e.g. Do bills measure collection targets by weight or by value recovered?"
          rows={3}
          className="w-full rounded-lg border border-border-default bg-bg-primary px-4 py-3 text-body text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent resize-none"
        />
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-text-muted">Admin preview · ⌘/Ctrl+Enter to ask</span>
          <button
            type="submit"
            disabled={busy || question.trim().length < 3}
            className="rounded-full bg-green-accent px-5 py-2 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {busy ? 'Thinking…' : 'Ask'}
          </button>
        </div>
      </form>

      {!answer && !busy && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map(ex => (
            <button
              key={ex}
              onClick={() => { setQuestion(ex); ask(ex); }}
              className="rounded-full border border-border-default px-3 py-1.5 text-xs text-text-secondary hover:border-text-primary/40 hover:text-text-primary text-left"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      {error && <p className="text-sm text-error">{error}</p>}

      {busy && <div className="h-24 w-full animate-pulse rounded-lg bg-bg-tertiary" />}

      {answer && (
        <div className="space-y-5 border-t border-border-default pt-6">
          <AnswerText text={answer.answer} />

          {answer.chart && answer.chart.bars.length > 0 && (
            <AnswerChart title={answer.chart.title} bars={answer.chart.bars} />
          )}

          {answer.citations.length > 0 && (
            <div className="space-y-2">
              <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
                Cited bills ({answer.citations.length})
              </div>
              <ul className="space-y-2">
                {answer.citations.map(c => (
                  <li key={c.bill_id} className="border-l-2 border-green-accent/40 pl-3">
                    <div className="text-body text-text-primary">
                      <span className="font-mono text-green-accent text-sm">{c.state} {c.bill_number}</span>
                      {c.region && c.region !== c.state && <span className="text-text-muted text-xs ml-2">{c.region}</span>}
                      {c.year && <span className="text-text-muted text-xs ml-2">{c.year}</span>}
                    </div>
                    {c.snippet && <p className="text-xs text-text-muted italic mt-0.5 leading-snug">…{c.snippet}…</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {answer.coverage_note && (
            <p className="text-xs text-text-muted border-t border-border-default pt-3">
              {answer.coverage_note}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
