'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { LockIcon } from '@/components/ui/icons';
import { useAuth } from '@/components/auth/AuthContext';
import { MarkdownLite } from '@/components/ui/MarkdownLite';
import {
  fetchResearchTurns,
  shareSession,
  unshareSession,
  createDraft,
  fetchDrafts,
  updateDraft,
  deleteDraft,
  type ResearchTurnAdminItem,
  type ContentDraft,
} from '@/lib/research-admin';

type GetToken = () => Promise<string | null>;

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
// The reader origin for share links. The API returns an absolute share_url built from the deployed
// dashboard origin; in local dev we fall back to the current origin so a copied link is clickable.

function fmtDateTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

function useCopy(): [boolean, (text: string) => void] {
  const [copied, setCopied] = useState(false);
  const copy = useCallback((text: string) => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, []);
  return [copied, copy];
}

// ── Gate (mirrors /admin) ──────────────────────────────────────────────────

export default function ResearchAdminPage() {
  const { user, loading, isAdmin, openAuth, getToken } = useAuth();

  if (loading) return <Shell><p className="text-text-muted text-sm">Loading…</p></Shell>;
  if (!user) {
    return (
      <Shell>
        <div className="rounded-xl border border-green-accent bg-green-dark/20 p-8 text-center space-y-3 max-w-xl mx-auto">
          <LockIcon className="text-2xl text-green-accent mx-auto" />
          <h2 className="font-serif text-xl text-text-primary">Sign in required</h2>
          <button
            onClick={openAuth}
            className="inline-flex items-center gap-2 rounded-lg bg-green-accent text-bg-primary px-5 py-2.5 font-medium text-sm hover:opacity-90 transition-opacity"
          >
            Sign in
          </button>
        </div>
      </Shell>
    );
  }
  if (!isAdmin) {
    return <Shell><p className="text-text-muted text-sm text-center">404 — This page could not be found.</p></Shell>;
  }
  return <Console getToken={getToken} />;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <GazetteHeader title="Research & Content" subtitle="Every Ask-the-Bills turn, shareable threads, and the article staging area." />
      <p className="text-xs text-text-muted">
        <Link href="/admin" className="text-green-accent hover:underline">← Admin console</Link>
      </p>
      {children}
    </div>
  );
}

function Console({ getToken }: { getToken: GetToken }) {
  const [tab, setTab] = useState<'log' | 'staging'>('log');
  return (
    <Shell>
      <div className="flex gap-2 border-b border-border-default">
        <TabButton active={tab === 'log'} onClick={() => setTab('log')}>Research log</TabButton>
        <TabButton active={tab === 'staging'} onClick={() => setTab('staging')}>Staging</TabButton>
      </div>
      {tab === 'log' ? <ResearchLog getToken={getToken} /> : <Staging getToken={getToken} />}
    </Shell>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
        active ? 'border-green-accent text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary'
      }`}
    >
      {children}
    </button>
  );
}

// ── Research log ────────────────────────────────────────────────────────────

function ResearchLog({ getToken }: { getToken: GetToken }) {
  const [items, setItems] = useState<ResearchTurnAdminItem[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (query: string) => {
    setError(null);
    try {
      const res = await fetchResearchTurns(getToken, { q: query || undefined, limit: 50 });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the research log.');
    }
  }, [getToken]);

  useEffect(() => { load(''); }, [load]);

  // Share state is per-session; when a session is (un)shared, patch every turn in that session.
  function patchSession(sessionId: string, patch: Partial<ResearchTurnAdminItem>) {
    setItems(prev => prev.map(t => (t.session_id === sessionId ? { ...t, ...patch } : t)));
  }

  async function toggleShare(thread: Thread) {
    if (busy) return;
    setBusy(true); setNotice(null); setError(null);
    try {
      if (thread.visibility === 'link') {
        await unshareSession(getToken, thread.session_id);
        patchSession(thread.session_id, { visibility: 'private', share_token: null });
        setNotice('Share link turned off.');
      } else {
        const res = await shareSession(getToken, thread.session_id);
        patchSession(thread.session_id, { visibility: 'link', share_token: res.share_token });
        if (res.share_url) navigator.clipboard?.writeText(res.share_url).catch(() => {});
        setNotice('Share link created and copied to clipboard.');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update sharing.');
    } finally {
      setBusy(false);
    }
  }

  async function stage(thread: Thread, seqs: number[], editorial: boolean) {
    if (busy || seqs.length === 0) return;
    setBusy(true); setNotice(null); setError(null);
    try {
      await createDraft(getToken, { session_id: thread.session_id, seqs, editorial });
      const n = seqs.length;
      const what = n > 1 ? `${n} questions` : 'answer';
      setNotice(`${editorial ? 'Drafted' : 'Staged verbatim'} from ${what} → see the Staging tab.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not stage.');
    } finally {
      setBusy(false);
    }
  }

  const threads = groupThreads(items);

  return (
    <div className="space-y-4">
      <form
        onSubmit={e => { e.preventDefault(); load(q.trim()); }}
        className="flex items-center gap-2"
      >
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search questions…"
          className="flex-1 rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-green-accent focus:outline-none"
        />
        <button type="submit" className="rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-secondary hover:text-text-primary transition-colors">
          Search
        </button>
      </form>

      <div className="flex items-center justify-between">
        <p className="text-text-muted text-xs">{threads.length} thread(s) · {total} turn(s)</p>
        {busy && <p className="text-text-muted text-xs">Working…</p>}
      </div>
      {notice && <p className="text-green-accent text-xs">{notice}</p>}
      {error && <p className="text-red-400 text-xs">{error}</p>}

      <div className="space-y-3">
        {threads.map(th => (
          <ThreadCard
            key={th.session_id}
            thread={th}
            busy={busy}
            onToggleShare={() => toggleShare(th)}
            onStage={(seqs, ed) => stage(th, seqs, ed)}
          />
        ))}
        {threads.length === 0 && !error && <p className="text-text-muted text-sm">No research threads yet.</p>}
      </div>
    </div>
  );
}

// A research thread = all turns of one session, in ask order. Turns arrive newest-first and flat; group
// by session, sort each thread by seq, and order threads by their most recent turn.
interface Thread {
  session_id: string;
  title: string;
  visibility: string;
  share_token: string | null;
  turns: ResearchTurnAdminItem[];
}

function groupThreads(items: ResearchTurnAdminItem[]): Thread[] {
  const map = new Map<string, ResearchTurnAdminItem[]>();
  for (const t of items) {
    const arr = map.get(t.session_id);
    if (arr) arr.push(t);
    else map.set(t.session_id, [t]);
  }
  const threads: Thread[] = [];
  for (const [session_id, turns] of map) {
    turns.sort((a, b) => a.seq - b.seq);
    const first = turns[0];
    threads.push({
      session_id,
      title: first.session_title || first.question,
      visibility: first.visibility,
      share_token: first.share_token,
      turns,
    });
  }
  threads.sort((a, b) =>
    (b.turns[b.turns.length - 1].created_at ?? '').localeCompare(a.turns[a.turns.length - 1].created_at ?? ''),
  );
  return threads;
}

function ThreadCard({
  thread, busy, onToggleShare, onStage,
}: {
  thread: Thread;
  busy: boolean;
  onToggleShare: () => void;
  onStage: (seqs: number[], editorial: boolean) => void;
}) {
  // Every turn selected by default; untick a follow-up to leave it out of the draft.
  const [selected, setSelected] = useState<Set<number>>(() => new Set(thread.turns.map(t => t.seq)));
  const [copied, copy] = useCopy();
  const multi = thread.turns.length > 1;
  const shared = thread.visibility === 'link' && !!thread.share_token;
  const shareUrl = thread.share_token
    ? (typeof window !== 'undefined' ? `${window.location.origin}/r/?token=${thread.share_token}` : `${API}/r/?token=${thread.share_token}`)
    : null;

  const selectedSeqs = thread.turns.map(t => t.seq).filter(s => selected.has(s));
  function toggle(seq: number) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(seq)) next.delete(seq); else next.add(seq);
      return next;
    });
  }

  return (
    <div className="rounded-lg border border-border-default bg-bg-secondary p-4 space-y-3">
      {/* Thread header — title + share (session-level) */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-text-primary text-base font-serif truncate">{thread.title}</p>
          <p className="text-text-muted text-meta mt-0.5">
            {thread.turns.length} question{thread.turns.length > 1 ? 's' : ''} · {fmtDateTime(thread.turns[thread.turns.length - 1].created_at)}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {shared && <span className="text-meta uppercase tracking-wider border rounded-full px-1.5 py-0.5 text-green-accent border-green-accent/40">Shared</span>}
          <button onClick={onToggleShare} disabled={busy} className="text-xs text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50">
            {shared ? 'Unshare' : 'Share thread'}
          </button>
        </div>
      </div>

      {shared && shareUrl && (
        <div className="flex items-center gap-2 text-xs">
          <code className="flex-1 truncate rounded bg-bg-primary border border-border-default px-2 py-1 text-text-secondary">{shareUrl}</code>
          <button onClick={() => copy(shareUrl)} className="text-green-accent hover:underline">{copied ? 'Copied' : 'Copy'}</button>
        </div>
      )}

      {/* Turns — each with an include checkbox */}
      <div className="divide-y divide-border-default/60 border-y border-border-default/60">
        {thread.turns.map(t => (
          <TurnRow key={t.turn_id} turn={t} multi={multi} checked={selected.has(t.seq)} onToggle={() => toggle(t.seq)} />
        ))}
      </div>

      {/* Thread-level staging over the ticked questions */}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        <span className="text-text-muted text-xs">
          {selectedSeqs.length} of {thread.turns.length} selected
        </span>
        <button
          onClick={() => onStage(selectedSeqs, true)}
          disabled={busy || selectedSeqs.length === 0}
          className="inline-flex items-center gap-1.5 rounded-lg bg-green-accent text-bg-primary px-3 py-1.5 text-xs font-medium hover:opacity-90 transition-opacity disabled:opacity-40"
        >
          Draft article →
        </button>
        <button
          onClick={() => onStage(selectedSeqs, false)}
          disabled={busy || selectedSeqs.length === 0}
          className="text-xs text-text-secondary hover:text-text-primary transition-colors disabled:opacity-40"
          title="Stage the selected answers verbatim, without the editorial LLM pass"
        >
          Stage verbatim
        </button>
      </div>
    </div>
  );
}

function TurnRow({
  turn: t, multi, checked, onToggle,
}: {
  turn: ResearchTurnAdminItem;
  multi: boolean;
  checked: boolean;
  onToggle: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="py-2.5">
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          className="mt-1 accent-green-accent shrink-0"
          title="Include this question in the draft"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <p className="text-text-primary text-sm">
              {multi && <span className="text-green-accent font-mono mr-1.5">Q{t.seq}.</span>}
              {t.question}
            </p>
            <button onClick={() => setOpen(o => !o)} className="text-xs text-text-secondary hover:text-text-primary transition-colors shrink-0">
              {open ? 'Hide' : 'View'}
            </button>
          </div>
          <p className="text-text-muted text-meta mt-1">
            {t.strategy || '—'} · {t.bill_total} bills · {t.cited_count} cited
          </p>
          {open && t.answer && (
            <div className="mt-2 rounded-lg border border-border-default bg-bg-primary p-3 max-h-96 overflow-auto">
              <MarkdownLite text={t.answer} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Staging ─────────────────────────────────────────────────────────────────

const STATUSES = ['staged', 'draft', 'published'] as const;

function Staging({ getToken }: { getToken: GetToken }) {
  const [items, setItems] = useState<ContentDraft[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchDrafts(getToken, { status: statusFilter || undefined, limit: 100 });
      setItems(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load drafts.');
    }
  }, [getToken, statusFilter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-text-secondary text-sm">
          Articles distilled from research answers — citations already linked to live bill pages. Edit here, then
          copy the markdown into Substack. Nothing publishes automatically.
        </p>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-primary focus:border-green-accent focus:outline-none shrink-0"
        >
          <option value="">All</option>
          {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {error && <p className="text-red-400 text-xs">{error}</p>}
      <div className="space-y-3">
        {items.map(d => (
          <DraftCard key={d.id} draft={d} getToken={getToken} onChanged={load} />
        ))}
        {items.length === 0 && !error && (
          <p className="text-text-muted text-sm">Nothing staged yet — send an answer over from the Research log.</p>
        )}
      </div>
    </div>
  );
}

function draftMarkdown(d: { title: string; dek: string | null; body_markdown: string }): string {
  const head = `# ${d.title}\n`;
  const dek = d.dek ? `\n_${d.dek}_\n` : '';
  return `${head}${dek}\n${d.body_markdown}\n`;
}

function DraftCard({ draft, getToken, onChanged }: { draft: ContentDraft; getToken: GetToken; onChanged: () => void }) {
  const [d, setD] = useState<ContentDraft>(draft);
  const [editing, setEditing] = useState(false);
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDel, setConfirmDel] = useState(false);
  const [copied, copy] = useCopy();

  useEffect(() => { setD(draft); }, [draft]);

  async function save() {
    if (busy) return;
    setBusy(true); setError(null);
    try {
      const saved = await updateDraft(getToken, d.id, { title: d.title, dek: d.dek, body_markdown: d.body_markdown });
      setD(saved);
      setEditing(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save.');
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(status: string) {
    if (busy) return;
    setBusy(true); setError(null);
    try {
      const saved = await updateDraft(getToken, d.id, { status });
      setD(saved);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update status.');
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy(true); setError(null);
    try {
      await deleteDraft(getToken, d.id);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete.');
      setBusy(false);
    }
  }

  const statusTone = d.status === 'published' ? 'text-green-accent border-green-accent/40'
    : d.status === 'draft' ? 'text-amber-400 border-amber-400/40'
    : 'text-text-muted border-border-default';

  return (
    <div className="rounded-lg border border-border-default bg-bg-secondary p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {editing ? (
            <input
              value={d.title}
              onChange={e => setD({ ...d, title: e.target.value })}
              className="w-full rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-primary focus:border-green-accent focus:outline-none"
            />
          ) : (
            <p className="text-text-primary text-base font-serif">{d.title}</p>
          )}
          {!editing && d.dek && <p className="text-text-secondary text-sm mt-0.5">{d.dek}</p>}
          <p className="text-text-muted text-meta mt-1">
            updated {fmtDateTime(d.updated_at)}{d.created_by ? ` · ${d.created_by}` : ''}
          </p>
        </div>
        <span className={`text-meta uppercase tracking-wider border rounded-full px-1.5 py-0.5 shrink-0 ${statusTone}`}>{d.status}</span>
      </div>

      {editing && (
        <div className="space-y-2">
          <input
            value={d.dek ?? ''}
            onChange={e => setD({ ...d, dek: e.target.value })}
            placeholder="Dek / subtitle"
            className="w-full rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-green-accent focus:outline-none"
          />
          <textarea
            value={d.body_markdown}
            onChange={e => setD({ ...d, body_markdown: e.target.value })}
            rows={16}
            className="w-full rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm font-mono text-text-primary focus:border-green-accent focus:outline-none"
          />
        </div>
      )}

      {!editing && preview && (
        <div className="rounded-lg border border-border-default bg-bg-primary p-3 max-h-[32rem] overflow-auto">
          <MarkdownLite text={d.body_markdown} />
        </div>
      )}

      {error && <p className="text-red-400 text-xs">{error}</p>}

      <div className="flex flex-wrap items-center gap-3 pt-1 text-xs">
        {editing ? (
          <>
            <button onClick={save} disabled={busy} className="rounded-lg bg-green-accent text-bg-primary px-3 py-1.5 font-medium hover:opacity-90 transition-opacity disabled:opacity-50">
              {busy ? 'Saving…' : 'Save'}
            </button>
            <button onClick={() => { setD(draft); setEditing(false); }} className="text-text-muted hover:text-text-secondary transition-colors">Cancel</button>
          </>
        ) : (
          <>
            <button onClick={() => setEditing(true)} className="text-text-secondary hover:text-text-primary transition-colors">Edit</button>
            <button onClick={() => setPreview(p => !p)} className="text-text-secondary hover:text-text-primary transition-colors">{preview ? 'Hide preview' : 'Preview'}</button>
            <button onClick={() => copy(draftMarkdown(d))} className="text-green-accent hover:underline">{copied ? 'Copied for Substack' : 'Copy markdown'}</button>
            <span className="text-border-default">·</span>
            {d.status !== 'published' && (
              <button onClick={() => setStatus('published')} disabled={busy} className="text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50">Mark published</button>
            )}
            {d.status !== 'staged' && (
              <button onClick={() => setStatus('staged')} disabled={busy} className="text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50">Back to staged</button>
            )}
            {confirmDel ? (
              <span className="inline-flex items-center gap-2">
                <span className="text-text-muted">Delete?</span>
                <button onClick={remove} disabled={busy} className="text-red-400 hover:text-red-300 transition-colors disabled:opacity-50">Yes</button>
                <button onClick={() => setConfirmDel(false)} className="text-text-muted hover:text-text-secondary transition-colors">No</button>
              </span>
            ) : (
              <button onClick={() => setConfirmDel(true)} disabled={busy} className="text-red-400/80 hover:text-red-300 transition-colors disabled:opacity-50">Delete</button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
