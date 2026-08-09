'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/auth/AuthContext';
import { useResearch, ResearchThread, ResearchWall, RESEARCH_EXAMPLES } from '@/components/research/ResearchThread';
import { useTypedPlaceholder, WORKING_PHRASES } from '@/components/research/useTypedPlaceholder';

/**
 * Ask the Atlas — the home for questions.
 *
 * The homepage owns browsing (keyword filtering, facets, the globe) and routes here the moment Ask is
 * pressed; this page owns the conversation. Giving the thread its own address is what makes it
 * survivable: `?session=` is restorable by refresh, Back, and My Library, where React state on the
 * homepage was destroyed by any of the three. See docs/ASK_SURFACE_SPEC.md.
 *
 * URL states:
 *   /ask                  the empty surface — bar + examples
 *   /ask?q=<question>     handoff from the homepage; this page owns the request
 *   /ask?session=<id>     canonical: an owned thread, follow-ups append to it (useResearch restores it)
 *
 * No AI-Analysis toggle here — on this page the bar is always a question box, which is the whole point
 * of having a separate surface. The toggle stays on the homepage, where the bar does double duty.
 */
export default function AskPage() {
  const research = useResearch();
  const { openAuth } = useAuth();
  const [query, setQuery] = useState('');
  const handled = useRef(false);

  // Handoff from the homepage. Waits for auth to resolve so the walls and the token are right, and
  // fires exactly once (a ref, not state — StrictMode mounts effects twice in dev, and a double-fire
  // here is a duplicate deep read).
  useEffect(() => {
    if (research.authLoading || handled.current) return;
    const params = new URLSearchParams(window.location.search);
    const q = params.get('q');
    if (!q || params.get('session')) return;   // ?session= is the hook's own restore path
    handled.current = true;
    // The question stays in the URL while it runs: a reload mid-ask lands back here with it intact, and
    // resume() looks for the saved copy before spending another deep read on the same question.
    void research.resume(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [research.authLoading]);

  // Once an answer is on screen the question no longer needs to ride the URL — drop ?q= so Back and
  // refresh behave, and so newThread() starts genuinely clean.
  useEffect(() => {
    if (!research.hasAsked) return;
    const params = new URLSearchParams(window.location.search);
    if (!params.get('q')) return;
    params.delete('q');
    const qs = params.toString();
    window.history.replaceState(null, '', `/ask/${qs ? `?${qs}` : ''}`);
  }, [research.hasAsked]);

  const typedPlaceholder = useTypedPlaceholder(
    research.busy ? WORKING_PHRASES : RESEARCH_EXAMPLES,
    research.busy || (!research.hasAsked && query === ''),
    research.busy,
  );

  const submit = () => {
    const q = query.trim();
    if (q.length < 3 || research.busy) return;
    research.ask(q);
    setQuery('');
  };

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <h1 className="font-serif text-2xl sm:text-3xl text-text-primary">Ask the Atlas</h1>
          <p className="mt-1 text-sm text-text-muted">
            Grounded in the corpus, cited to the bills it read.
          </p>
        </div>
        <div className="flex items-center gap-4">
          {research.hasAsked && (
            <button type="button" onClick={research.newThread} className="text-sm text-green-accent hover:underline">
              New question
            </button>
          )}
          <Link href="/" className="text-sm text-green-accent hover:underline">
            ← Back to the Atlas
          </Link>
        </div>
      </div>

      {/* The bar the homepage hands off to. `ask-bar` is the shared element the view transition flies
          from its place on the homepage into this one — see globals.css. */}
      <form onSubmit={e => { e.preventDefault(); submit(); }} style={{ viewTransitionName: 'ask-bar' }}>
        <div className="flex items-center gap-2 rounded-xl border-2 border-green-accent/60 bg-bg-secondary px-3 py-2 focus-within:border-green-accent transition-colors">
          <span aria-hidden className="text-text-muted text-lg leading-none">⌕</span>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={
              research.busy
                ? (typedPlaceholder || 'Working…')
                : research.hasAsked ? 'Ask a follow-up…' : (typedPlaceholder || 'Ask a question about the corpus…')
            }
            aria-label="Ask a question"
            autoFocus
            className="flex-1 min-w-0 bg-transparent text-body text-text-primary placeholder-text-muted focus:outline-none"
          />
          <button
            type="submit"
            disabled={research.busy || query.trim().length < 3}
            className="shrink-0 rounded-lg bg-green-accent text-bg-primary font-medium text-sm px-5 py-2 hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {research.busy ? 'Thinking…' : research.hasAsked ? 'Ask follow-up' : 'Ask →'}
          </button>
        </div>
      </form>

      {/* Before the first question: what this surface is for, in the reader's own examples. */}
      {!research.active && (
        <div className="space-y-2">
          <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">Try asking</div>
          <ul className="space-y-1.5">
            {RESEARCH_EXAMPLES.map(ex => (
              <li key={ex}>
                <button
                  type="button"
                  onClick={() => research.ask(ex)}
                  className="text-left text-body text-text-secondary hover:text-green-accent transition-colors"
                >
                  {ex}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <section className="space-y-5">
        {research.wall && <ResearchWall wall={research.wall} onSignIn={openAuth} />}
        {research.restoring && (
          <div className="space-y-2 border-t border-border-default pt-6">
            <div className="h-6 w-2/3 animate-pulse rounded bg-bg-tertiary" />
            <div className="h-24 w-full animate-pulse rounded-lg bg-bg-tertiary" />
          </div>
        )}
        <ResearchThread research={research} />
      </section>
    </div>
  );
}
