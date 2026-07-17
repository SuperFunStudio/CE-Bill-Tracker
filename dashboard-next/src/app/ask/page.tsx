'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { CAP, useAuth } from '@/components/auth/AuthContext';
import { ApiError, askResearch, fetchResearchBills } from '@/lib/api';
import type { BillSummary, ResearchAnswer, ResearchBillPage, ResearchCitation } from '@/lib/types';
import { BillTable } from '@/components/bills/BillTable';
import { BillModal } from '@/components/ui/BillModal';

// "Ask the Atlas" — a natural-language question over the extracted corpus. The answer is grounded in
// retrieved bills + SQL aggregates server-side (numbers are exact, claims are cited); this page just
// drives the prompt and renders the result. Access: an anonymous visitor gets one free question, then
// the sign-in/upgrade wall; members (Student+) get full, threaded, saved asks. Upload-and-compare
// (formerly Evaluate a Bill) folds in here in a fast follow.

// Local marker that an anonymous visitor has spent their one free question (server enforces the real
// per-IP/day limit; this just avoids a wasted round-trip and shows the wall immediately).
const FREE_ASK_KEY = 'atlas_free_ask_used';

const EXAMPLES = [
  'Do bills measure collection targets by weight or by value recovered?',
  'Which compliance dimensions are most common across bills?',
  'What design attributes do bills eco-modulate fees on?',
  'Which bills ban PFAS in packaging?',
];

/** The synthesis cites bills inline as `[STATE BILL_NUMBER]` (verbatim `ref`). Map each ref to its
 *  citation so the marker can open the same bill modal the table opens. */
function citationRef(c: ResearchCitation): string {
  return `${c.state ?? ''} ${c.bill_number ?? ''}`.trim();
}

/** Inline rendering: **bold** + clickable `[STATE BILL_NUMBER]` citations. A bracketed token that
 *  matches a known citation (with a bill payload) becomes a button that opens the bill modal; any
 *  other bracketed text renders literally. */
function inline(line: string, cites: Map<string, ResearchCitation>, onCite: (c: ResearchCitation) => void) {
  // Split keeping **bold** and [bracketed] tokens as their own parts (brackets don't nest).
  return line.split(/(\*\*[^*]+\*\*|\[[^\][]+\])/g).map((p, j) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      return <strong key={j} className="text-text-primary font-semibold">{p.slice(2, -2)}</strong>;
    }
    if (p.startsWith('[') && p.endsWith(']')) {
      const c = cites.get(p.slice(1, -1));
      if (c?.bill) {
        return (
          <button
            key={j}
            type="button"
            onClick={() => onCite(c)}
            title={`Open ${citationRef(c)} details`}
            className="font-mono text-green-accent hover:underline focus:outline-none focus:underline"
          >
            {p}
          </button>
        );
      }
    }
    return <span key={j}>{p}</span>;
  });
}

/** Render the deep-synthesis markdown: ## / ### headers, "- " bullets, --- rules, **bold**, and
 *  clickable inline `[STATE BILL_NUMBER]` citations. */
function AnswerText({ text, cites, onCite }: {
  text: string;
  cites: Map<string, ResearchCitation>;
  onCite: (c: ResearchCitation) => void;
}) {
  return (
    <div className="space-y-2 text-body text-text-primary leading-relaxed">
      {text.split('\n').map(l => l.trimEnd()).filter(l => l.trim()).map((line, i) => {
        const t = line.trimStart();
        const hm = t.match(/^(#{1,6})\s+(.*)$/);
        if (hm) {
          const cls = hm[1].length <= 2
            ? 'font-serif text-lg text-text-primary mt-4 mb-1'
            : 'text-sm font-semibold uppercase tracking-wide text-text-secondary mt-3';
          return <div key={i} className={cls}>{inline(hm[2], cites, onCite)}</div>;
        }
        if (/^-{3,}$/.test(t)) return <hr key={i} className="border-border-default my-2" />;
        if (t.startsWith('- ') || t.startsWith('* ')) {
          return <p key={i} className="pl-4 -indent-4">{inline('• ' + t.slice(2), cites, onCite)}</p>;
        }
        return <p key={i}>{inline(line, cites, onCite)}</p>;
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

/** The cited-bills list for one answer. Each entry opens the same bill modal the inline [markers] and
 *  the relevant-bills table open. */
function CitedBills({ citations, onOpen }: { citations: ResearchCitation[]; onOpen: (b: BillSummary) => void }) {
  return (
    <div className="space-y-2">
      <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
        Cited bills ({citations.length})
      </div>
      <ul className="space-y-2">
        {citations.map(c => {
          const body = (
            <>
              <div className="text-body text-text-primary">
                <span className="font-mono text-green-accent text-sm">{c.state} {c.bill_number}</span>
                {c.region && c.region !== c.state && <span className="text-text-muted text-xs ml-2">{c.region}</span>}
                {c.year && <span className="text-text-muted text-xs ml-2">{c.year}</span>}
              </div>
              {c.snippet && <p className="text-xs text-text-muted italic mt-0.5 leading-snug">…{c.snippet}…</p>}
            </>
          );
          return c.bill ? (
            <li key={c.bill_id}>
              <button
                type="button"
                onClick={() => onOpen(c.bill!)}
                className="w-full text-left border-l-2 border-green-accent/40 pl-3 rounded-sm hover:bg-bg-secondary focus:outline-none focus:bg-bg-secondary transition-colors"
              >
                {body}
              </button>
            </li>
          ) : (
            <li key={c.bill_id} className="border-l-2 border-green-accent/40 pl-3">{body}</li>
          );
        })}
      </ul>
    </div>
  );
}

export default function AskPage() {
  // Open to everyone: members (Student+ carry the `ask` capability, or admins) get full threaded asks;
  // an anonymous visitor gets one free question, then the wall. A signed-in FREE account has no ask
  // capability and is walled toward an upgrade. The backend enforces all of this — see /research/ask.
  const { user, hasCapability, openAuth, getToken, loading: authLoading } = useAuth();
  const canAsk = hasCapability(CAP.ASK);
  // Which wall to show, if any: 'signin' after an anonymous visitor spends their free question,
  // 'upgrade' for a signed-in free account.
  const [wall, setWall] = useState<null | 'signin' | 'upgrade'>(null);
  const [freeAskUsed, setFreeAskUsed] = useState(false);
  const [question, setQuestion] = useState('');
  // The conversation: each turn is a question + its grounded answer. A follow-up is asked with the
  // current sessionId so the server condenses it against the thread before retrieving.
  const [turns, setTurns] = useState<{ q: string; answer: ResearchAnswer }[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [billPage, setBillPage] = useState<ResearchBillPage | null>(null);  // relevant-bills table for the LAST turn
  const [lastQuery, setLastQuery] = useState('');   // the retrieval query backing that table (for paging)
  const [busy, setBusy] = useState(false);
  const [pageBusy, setPageBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modalBill, setModalBill] = useState<BillSummary | null>(null);  // opened from a citation

  // Anonymous visitors: remember once they've spent their free question so the wall shows immediately.
  useEffect(() => {
    if (!user && typeof window !== 'undefined') {
      try { setFreeAskUsed(localStorage.getItem(FREE_ASK_KEY) === '1'); } catch { /* ignore */ }
    }
  }, [user]);

  async function ask(q: string) {
    const trimmed = q.trim();
    if (trimmed.length < 3 || busy) return;
    // Wall the right people before spending a request: a signed-in free account (no ask capability)
    // gets the upgrade wall; an anonymous visitor who already used their free question gets sign-in.
    if (user && !canAsk) { setWall('upgrade'); return; }
    if (!user && freeAskUsed) { setWall('signin'); return; }
    setBusy(true); setError(null); setWall(null);
    try {
      const token = await getToken();
      const a = await askResearch(trimmed, token, sessionId);   // sessionId null on the first turn
      setTurns(prev => [...prev, { q: trimmed, answer: a }]);
      setSessionId(a.session_id ?? sessionId);
      setBillPage(a.bills ?? null);
      setLastQuery(a.retrieval_query ?? trimmed);
      setQuestion('');
      // Mark the anonymous free question as spent — the next ask hits the sign-in wall.
      if (!user && typeof window !== 'undefined') {
        try { localStorage.setItem(FREE_ASK_KEY, '1'); } catch { /* ignore */ }
        setFreeAskUsed(true);
      }
    } catch (e) {
      // Translate the server's gate 403s into the matching wall; other errors show inline.
      if (e instanceof ApiError && e.status === 403) {
        setWall(e.detail === 'ask_upgrade_required' ? 'upgrade' : 'signin');
        if (!user) { try { localStorage.setItem(FREE_ASK_KEY, '1'); } catch { /* ignore */ } setFreeAskUsed(true); }
      } else {
        setError(e instanceof Error ? e.message : 'Something went wrong.');
      }
    } finally {
      setBusy(false);
    }
  }

  function newThread() {
    setTurns([]); setSessionId(null); setBillPage(null); setLastQuery('');
    setQuestion(''); setError(null);
  }

  async function goToPage(page: number) {
    if (!billPage || pageBusy) return;
    setPageBusy(true);
    try {
      const token = await getToken();
      setBillPage(await fetchResearchBills(lastQuery, page, billPage.page_size, token));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setPageBusy(false);
    }
  }

  if (authLoading) return null;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-6">
      <div>
        <p className="text-[rgb(var(--green-accent))] text-xs font-semibold uppercase tracking-wider">Ask the Atlas</p>
        <h1 className="font-serif text-2xl text-text-primary mt-1">Question the whole corpus</h1>
        <p className="text-text-secondary text-body mt-2 leading-relaxed">
          Ask an analytical question across every tracked measure in the atlas. Answers are grounded in
          the bills&apos; extracted compliance data and cite the specific measures behind each claim — and
          where the question is a counting question, the numbers come straight from the database.
        </p>
        {!user && !freeAskUsed && (
          <p className="text-text-muted text-xs mt-2">
            Your first question is free — sign in for unlimited, threaded, saved research.
          </p>
        )}
      </div>

      {wall && (
        <div className="rounded-lg border border-green-accent/40 bg-green-dark/40 p-5 space-y-3">
          <h2 className="font-serif text-lg text-text-primary">
            {wall === 'signin' ? 'That was your free question' : 'Ask the Atlas is a member feature'}
          </h2>
          <p className="text-body text-text-secondary">
            {wall === 'signin'
              ? 'Create a free account and choose a membership to keep asking — Students pay what they wish with a verified .edu email.'
              : 'Your plan includes the Bill Explorer. Upgrade to a Student, Research, or Pro membership to ask the Atlas.'}
          </p>
          <div className="flex flex-wrap gap-2">
            {wall === 'signin' ? (
              <button
                type="button"
                onClick={openAuth}
                className="rounded-full bg-green-accent px-5 py-2 text-sm font-medium text-bg-primary hover:opacity-90"
              >
                Sign in / sign up
              </button>
            ) : null}
            <Link
              href="/pricing"
              className="rounded-full border border-border-default px-5 py-2 text-sm text-text-secondary hover:text-text-primary"
            >
              See memberships
            </Link>
          </div>
        </div>
      )}

      <form onSubmit={e => { e.preventDefault(); ask(question); }} className="space-y-3">
        <textarea
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask(question); }}
          placeholder={turns.length === 0
            ? 'e.g. Do bills measure collection targets by weight or by value recovered?'
            : 'Ask a follow-up — e.g. "what about Japan?" or "just the enacted ones"'}
          rows={3}
          className="w-full rounded-lg border border-border-default bg-bg-primary px-4 py-3 text-body text-text-primary placeholder-text-muted focus:outline-none focus:border-green-accent resize-none"
        />
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-text-muted">
            {turns.length > 0
              ? 'Follow-up · keeps the thread’s context'
              : (!user ? 'One free question' : 'Ask the Atlas')} · ⌘/Ctrl+Enter to ask
          </span>
          <div className="flex items-center gap-2">
            {turns.length > 0 && (
              <button
                type="button"
                onClick={newThread}
                disabled={busy}
                className="rounded-full border border-border-default px-4 py-2 text-sm text-text-secondary hover:text-text-primary disabled:opacity-40"
              >
                New thread
              </button>
            )}
            <button
              type="submit"
              disabled={busy || question.trim().length < 3}
              className="rounded-full bg-green-accent px-5 py-2 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {busy ? 'Thinking…' : turns.length > 0 ? 'Ask follow-up' : 'Ask'}
            </button>
          </div>
        </div>
      </form>

      {turns.length === 0 && !busy && (
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

      {/* The conversation, oldest first. Each turn shows its question, the grounded answer, any chart
          and cited bills; only the latest turn carries the paginated relevant-bills table. */}
      {turns.map((t, ti) => {
        const isLast = ti === turns.length - 1;
        const cites = new Map<string, ResearchCitation>();
        for (const c of t.answer.citations) if (c.bill) cites.set(citationRef(c), c);
        return (
          <div key={ti} className="space-y-5 border-t border-border-default pt-6">
            <div className="flex gap-2 font-serif text-lg text-text-primary">
              <span className="shrink-0 text-green-accent">{turns.length > 1 ? `Q${ti + 1}.` : 'Q.'}</span>
              <span>{t.q}</span>
            </div>

            <AnswerText text={t.answer.answer} cites={cites} onCite={c => c.bill && setModalBill(c.bill)} />

            {t.answer.chart && t.answer.chart.bars.length > 0 && (
              <AnswerChart title={t.answer.chart.title} bars={t.answer.chart.bars} />
            )}

            {t.answer.citations.length > 0 && (
              <CitedBills citations={t.answer.citations} onOpen={setModalBill} />
            )}

            {isLast && billPage && billPage.total > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
                    Relevant bills ({billPage.total})
                  </div>
                  <span className="text-xs text-text-muted">{strategyLabel(billPage.strategy)}</span>
                </div>
                <div className={pageBusy ? 'opacity-50 transition-opacity' : 'transition-opacity'}>
                  <BillTable bills={billPage.items} />
                </div>
                <BillPager page={billPage} busy={pageBusy} onGo={goToPage} />
              </div>
            )}

            {t.answer.coverage_note && (
              <p className="text-xs text-text-muted border-t border-border-default pt-3">
                {t.answer.coverage_note}
              </p>
            )}
          </div>
        );
      })}

      {busy && (
        <div className="space-y-3 border-t border-border-default pt-6">
          <p className="text-sm text-text-secondary">
            {turns.length > 0
              ? 'Following up on the thread — reading the most relevant bills and synthesizing a cited answer.'
              : 'Reading the full text of the most relevant bills and synthesizing a cited answer — this takes a moment.'}
          </p>
          <div className="h-24 w-full animate-pulse rounded-lg bg-bg-tertiary" />
        </div>
      )}

      {/* Modal opened from an inline citation or the cited-bills list. The bottom relevant-bills
          table owns its own modal instance; this one covers cited bills that may not be on page 1. */}
      <BillModal bill={modalBill} onClose={() => setModalBill(null)} />
    </div>
  );
}

/** Human-readable note for which retrieval tier produced the relevant set. Strategy may carry a
 *  jurisdiction suffix after "·" (e.g. "text·France,United States" or "jurisdiction·France"). */
function strategyLabel(strategy: string): string {
  const [base, tags] = strategy.split('·');
  const where = tags ? ` · ${tags}` : '';
  if (base.startsWith('dimension:')) {
    return `Compliance dimension: ${base.slice('dimension:'.length).replace(/_/g, ' ')}${where}`;
  }
  if (base === 'jurisdiction') return `Jurisdiction${tags ? `: ${tags}` : ''}`;
  if (base === 'material') return `Product / material${tags ? `: ${tags}` : ''}`;
  if (base === 'product') return `Product${tags ? `: ${tags}` : ''}`;
  if (base === 'instrument') return `Instrument${tags ? `: ${tags}` : ''}`;
  if (base === 'all') return 'All bills';
  if (base === 'text_broad') return `Broadened text & title match${where}`;
  return `Text & title match${where}`;
}

/** Server-driven Prev/Next pager over the full relevant set (BillTable's own pager is left off so
 *  paging fetches from the API rather than slicing an in-memory array). */
function BillPager({ page, busy, onGo }: { page: ResearchBillPage; busy: boolean; onGo: (p: number) => void }) {
  const pageCount = Math.max(1, Math.ceil(page.total / page.page_size));
  if (pageCount <= 1) return null;
  const start = (page.page - 1) * page.page_size + 1;
  const end = start + page.items.length - 1;
  return (
    <div className="flex items-center justify-between gap-3 pt-1">
      <span className="text-xs text-text-muted">{start}–{end} of {page.total}</span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onGo(page.page - 1)}
          disabled={busy || page.page <= 1}
          className="rounded-full border border-border-default px-3 py-1 text-xs text-text-secondary hover:text-text-primary disabled:opacity-30"
        >
          Prev
        </button>
        <span className="text-xs text-text-muted">Page {page.page} / {pageCount}</span>
        <button
          onClick={() => onGo(page.page + 1)}
          disabled={busy || page.page >= pageCount}
          className="rounded-full border border-border-default px-3 py-1 text-xs text-text-secondary hover:text-text-primary disabled:opacity-30"
        >
          Next
        </button>
      </div>
    </div>
  );
}
