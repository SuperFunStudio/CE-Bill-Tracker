'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchSharedSession, type SharedSession } from '@/lib/research-admin';
import { MarkdownLite } from '@/components/ui/MarkdownLite';

// Reads ?token=… from the URL and renders the shared thread. Kept out of page.tsx so that file can stay
// a server component (for the noindex metadata) while this half runs on the client.

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

export function SharedResearch() {
  const [state, setState] = useState<'loading' | 'ok' | 'error'>('loading');
  const [session, setSession] = useState<SharedSession | null>(null);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token') ?? '';
    if (!token) {
      setState('error');
      setError('No share link token.');
      return;
    }
    fetchSharedSession(token)
      .then(s => {
        setSession(s);
        setState('ok');
      })
      .catch(e => {
        setError(e instanceof Error ? e.message : 'Could not load this link.');
        setState('error');
      });
  }, []);

  if (state === 'loading') {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <div className="h-24 w-full animate-pulse rounded-lg bg-bg-tertiary" />
      </div>
    );
  }

  if (state === 'error' || !session) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center space-y-3">
        <p className="text-text-secondary">{error}</p>
        <Link href="/" className="text-green-accent hover:underline text-sm">
          Go to Atlas Circular →
        </Link>
      </div>
    );
  }

  const multi = session.turns.length > 1;
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 space-y-6">
      <div>
        <p className="text-[rgb(var(--green-accent))] text-xs font-semibold uppercase tracking-wider">
          Shared research · Atlas Circular
        </p>
        <h1 className="font-serif text-2xl text-text-primary mt-1">{session.title || 'Research thread'}</h1>
        {session.created_at && <p className="text-text-muted text-xs mt-1">{fmtDate(session.created_at)}</p>}
      </div>

      {session.turns.map((t, ti) => (
        <div key={ti} className="space-y-4 border-t border-border-default pt-6">
          <div className="flex gap-2 font-serif text-lg text-text-primary">
            <span className="shrink-0 text-green-accent">{multi ? `Q${ti + 1}.` : 'Q.'}</span>
            <span>{t.question}</span>
          </div>

          {t.answer && <MarkdownLite text={t.answer} />}

          {t.citations.length > 0 && (
            <div className="space-y-2">
              <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
                Cited bills ({t.citations.length})
              </div>
              <ul className="space-y-1">
                {t.citations.map(c => (
                  <li key={c.bill_id}>
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-baseline gap-2 border-l-2 border-green-accent/40 pl-3 hover:bg-bg-secondary rounded-sm"
                    >
                      <span className="font-mono text-green-accent text-sm">{c.ref}</span>
                      {c.region && <span className="text-text-muted text-xs">{c.region}</span>}
                      {c.year && <span className="text-text-muted text-xs">{c.year}</span>}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ))}

      <div className="border-t border-border-default pt-6 text-center">
        <p className="text-text-secondary text-sm">
          Grounded in the circular-economy legislation corpus at{' '}
          <Link href="/" className="text-green-accent hover:underline">
            Atlas Circular
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
