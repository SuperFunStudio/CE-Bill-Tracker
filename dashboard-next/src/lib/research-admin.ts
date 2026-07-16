// Client for the admin research log + sharing + content staging (the Substack content engine).
// The admin calls carry the Firebase ID token (backend gates each with require_admin); the shared-session
// read is PUBLIC (no token). See app/api/research.py.
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

type GetToken = () => Promise<string | null>;

async function authedFetch<T>(path: string, getToken: GetToken, init: RequestInit = {}): Promise<T> {
  const token = await getToken();
  if (!token) throw new Error('Please sign in first.');
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Request failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

// ── Research log ─────────────────────────────────────────────────────────────

export interface ResearchTurnAdminItem {
  turn_id: string;
  session_id: string;
  session_title: string | null;
  owner_uid: string;
  seq: number;
  question: string;
  answer: string | null; // linked markdown ([REF] rewritten to /?bill=<id>)
  strategy: string | null;
  bill_total: number;
  cited_count: number;
  visibility: string; // private | link
  share_token: string | null;
  created_at: string | null;
}

export interface ResearchTurnAdminPage {
  total: number;
  items: ResearchTurnAdminItem[];
}

export function fetchResearchTurns(
  getToken: GetToken,
  opts: { q?: string; limit?: number; offset?: number } = {},
): Promise<ResearchTurnAdminPage> {
  const p = new URLSearchParams();
  if (opts.q) p.set('q', opts.q);
  p.set('limit', String(opts.limit ?? 50));
  p.set('offset', String(opts.offset ?? 0));
  return authedFetch<ResearchTurnAdminPage>(`/research/admin/turns?${p}`, getToken);
}

// ── Sharing ──────────────────────────────────────────────────────────────────

export interface ShareResult {
  session_id: string;
  visibility: string; // link | private
  share_token: string | null;
  share_url: string | null;
}

export const shareSession = (getToken: GetToken, sessionId: string) =>
  authedFetch<ShareResult>(`/research/session/${sessionId}/share`, getToken, { method: 'POST' });

export const unshareSession = (getToken: GetToken, sessionId: string) =>
  authedFetch<ShareResult>(`/research/session/${sessionId}/unshare`, getToken, { method: 'POST' });

// ── Content staging (drafts) ─────────────────────────────────────────────────

export interface ContentDraft {
  id: string;
  source_session_id: string | null;
  source_seq: number | null;
  title: string;
  dek: string | null;
  body_markdown: string;
  status: string; // staged | draft | published
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ContentDraftPage {
  total: number;
  items: ContentDraft[];
}

export const createDraft = (
  getToken: GetToken,
  body: { session_id: string; seq?: number | null; editorial?: boolean },
) =>
  authedFetch<ContentDraft>('/research/drafts', getToken, {
    method: 'POST',
    body: JSON.stringify(body),
  });

export function fetchDrafts(
  getToken: GetToken,
  opts: { status?: string; limit?: number; offset?: number } = {},
): Promise<ContentDraftPage> {
  const p = new URLSearchParams();
  if (opts.status) p.set('status', opts.status);
  p.set('limit', String(opts.limit ?? 50));
  p.set('offset', String(opts.offset ?? 0));
  return authedFetch<ContentDraftPage>(`/research/drafts?${p}`, getToken);
}

export type DraftPatch = Partial<Pick<ContentDraft, 'title' | 'dek' | 'body_markdown' | 'status'>>;

export const updateDraft = (getToken: GetToken, id: string, patch: DraftPatch) =>
  authedFetch<ContentDraft>(`/research/drafts/${id}`, getToken, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });

export const deleteDraft = (getToken: GetToken, id: string) =>
  authedFetch<{ deleted: boolean; id: string }>(`/research/drafts/${id}`, getToken, {
    method: 'DELETE',
  });

// ── Public shared session (no auth) ──────────────────────────────────────────

export interface SharedCitation {
  bill_id: number;
  ref: string;
  region: string | null;
  year: number | null;
  url: string;
}

export interface SharedTurn {
  seq: number;
  question: string;
  answer: string | null; // linked markdown
  citations: SharedCitation[];
}

export interface SharedSession {
  title: string | null;
  created_at: string | null;
  turns: SharedTurn[];
}

/** PUBLIC read of a shared research thread. Throws on 404 (bad/revoked token). */
export async function fetchSharedSession(token: string): Promise<SharedSession> {
  const res = await fetch(`${API}/research/shared/${encodeURIComponent(token)}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(res.status === 404 ? 'This link is invalid or has been turned off.' : `Error ${res.status}`);
  return res.json();
}
