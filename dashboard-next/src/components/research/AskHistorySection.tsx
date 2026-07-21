'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { CAP, useAuth } from '@/components/auth/AuthContext';
import { fetchMyResearchSessions, type ResearchSessionListItem } from '@/lib/api';

/**
 * "My research" — the signed-in member's own Ask-the-Atlas history, shown in My Library. Private by
 * design: these threads are the caller's own (visibility=private) and never enter the public atlas
 * unless an admin drafts one into an article. Self-gates: signed-out shows a sign-in nudge, a free
 * account (no `ask` capability) shows an upgrade nudge, a member sees their threads.
 */
export function AskHistorySection() {
  const { user, hasCapability, getToken } = useAuth();
  const canAsk = hasCapability(CAP.ASK);
  const [sessions, setSessions] = useState<ResearchSessionListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!user || !canAsk) { setSessions(null); return; }
    (async () => {
      try {
        const rows = await fetchMyResearchSessions(await getToken());
        if (!cancelled) setSessions(rows);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load your research.');
      }
    })();
    return () => { cancelled = true; };
  }, [user, canAsk, getToken]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-serif text-2xl text-text-primary">My research</h2>
        <p className="text-text-secondary text-body max-w-3xl">
          Your Ask the Atlas history — private to you. Nothing here is published to the atlas.
        </p>
      </div>

      {!user && (
        <p className="text-text-secondary text-body">
          <Link href="/" className="text-green-accent hover:underline">Ask the Atlas</Link> a question to
          start building your research history.
        </p>
      )}

      {user && !canAsk && (
        <p className="text-text-secondary text-body">
          Ask the Atlas is a member feature.{' '}
          <Link href="/pricing" className="text-green-accent hover:underline">See memberships</Link> to
          start saving research.
        </p>
      )}

      {error && <p className="text-sm text-error">{error}</p>}

      {user && canAsk && sessions !== null && sessions.length === 0 && (
        <p className="text-text-secondary text-body">
          No saved threads yet.{' '}
          <Link href="/" className="text-green-accent hover:underline">Ask your first question →</Link>
        </p>
      )}

      {user && canAsk && sessions && sessions.length > 0 && (
        <ul className="space-y-2">
          {sessions.map(s => (
            <li key={s.session_id}>
              <Link
                href={`/?session=${s.session_id}`}
                className="block border-l-2 border-green-accent/40 pl-3 py-1 rounded-sm hover:bg-bg-secondary focus:outline-none focus:bg-bg-secondary transition-colors group"
              >
                <div className="flex items-center gap-2">
                  <span className="text-body text-text-primary font-medium group-hover:text-green-accent transition-colors">{s.title}</span>
                  {s.shared && (
                    <span className="text-meta uppercase tracking-wider text-green-accent border border-green-accent/40 rounded-full px-2 py-0.5">
                      Shared
                    </span>
                  )}
                </div>
                {s.preview && <p className="text-xs text-text-muted italic mt-0.5 leading-snug">{s.preview}</p>}
                <p className="text-xs text-text-muted mt-0.5">
                  {s.turns} question{s.turns === 1 ? '' : 's'}
                  {s.updated_at ? ` · ${new Date(s.updated_at).toLocaleDateString()}` : ''}
                  <span className="text-green-accent ml-2 opacity-0 group-hover:opacity-100 transition-opacity">Open →</span>
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
