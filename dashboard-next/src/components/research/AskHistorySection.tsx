'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { CAP, useAuth } from '@/components/auth/AuthContext';
import { fetchMyResearchSessions, type ResearchSessionListItem } from '@/lib/api';
import { shareSession, unshareSession } from '@/lib/research-admin';
import { track } from '@/lib/analytics';

/**
 * "My research" — the signed-in member's own Ask-the-Atlas history, shown in My Library. Private by
 * default; each thread can be shared by its owner as an unlisted /r/?token= link (revocable — unshare
 * drops the token, so a leaked link dies). Self-gates: signed-out shows a sign-in nudge, a free
 * account (no `ask` capability) shows an upgrade nudge, a member sees their threads.
 */
export function AskHistorySection() {
  const { user, hasCapability, getToken } = useAuth();
  const canAsk = hasCapability(CAP.ASK);
  const [sessions, setSessions] = useState<ResearchSessionListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

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

  const markShared = (id: string, shared: boolean) =>
    setSessions(prev => prev?.map(s => (s.session_id === id ? { ...s, shared } : s)) ?? prev);

  // Share is copy-link in one motion: the backend mints-or-reuses the token, so calling it on an
  // already-shared thread is a safe way to get the URL back onto the clipboard.
  async function handleShare(id: string) {
    setBusyId(id); setError(null);
    try {
      const r = await shareSession(getToken, id);
      markShared(id, true);
      if (r.share_url) {
        await navigator.clipboard.writeText(r.share_url);
        setCopiedId(id);
        setTimeout(() => setCopiedId(prev => (prev === id ? null : prev)), 2500);
      }
      track('research_share', { action: 'share' });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not share the thread.');
    } finally {
      setBusyId(null);
    }
  }

  async function handleUnshare(id: string) {
    setBusyId(id); setError(null);
    try {
      await unshareSession(getToken, id);
      markShared(id, false);
      track('research_share', { action: 'unshare' });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not turn the link off.');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-serif text-2xl text-text-primary">My research</h2>
        <p className="text-text-secondary text-body max-w-3xl">
          Your Ask the Atlas history — private to you unless you share a thread. Sharing makes an
          unlisted link anyone can read; turn it off any time and the link stops working.
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
            <li
              key={s.session_id}
              className="flex items-start gap-3 border-l-2 border-green-accent/40 pl-3 py-1 rounded-sm hover:bg-bg-secondary transition-colors group"
            >
              <Link
                href={`/ask/?session=${s.session_id}`}
                className="block flex-1 min-w-0 focus:outline-none"
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
              <div className="flex shrink-0 items-center gap-3 pt-1 text-xs">
                <button
                  type="button"
                  onClick={() => handleShare(s.session_id)}
                  disabled={busyId === s.session_id}
                  className="text-green-accent hover:underline disabled:opacity-50"
                >
                  {copiedId === s.session_id ? 'Link copied ✓' : s.shared ? 'Copy link' : 'Share'}
                </button>
                {s.shared && (
                  <button
                    type="button"
                    onClick={() => handleUnshare(s.session_id)}
                    disabled={busyId === s.session_id}
                    className="text-text-muted hover:text-text-primary hover:underline disabled:opacity-50"
                  >
                    Unshare
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
