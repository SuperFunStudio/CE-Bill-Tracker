// Client helpers for the hidden /admin console. Every call carries the Firebase ID token; the backend
// gates each route with require_admin (settings.admin_emails), so a non-admin token gets 403. See
// app/api/admin.py.
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

type GetToken = () => Promise<string | null>;

async function authedFetch<T>(
  path: string,
  getToken: GetToken,
  init: RequestInit = {},
): Promise<T> {
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

export interface AdminStats {
  subscribers_active: number;
  subscribers_total: number;
  pro_total: number;
  pro_paid: number;
  pro_comp: number;
  access_requests: number;
  bills_total: number;
  bills_relevant: number;
  data_freshness: {
    bills_last_updated: string | null;
    bills_last_fetched: string | null;
    bills_last_action: string | null;
    federal_last_published: string | null;
  };
}

export interface Subscriber {
  id: number;
  email: string | null;
  organization: string | null;
  states: string[];
  instrument_types: string[];
  material_categories: string[];
  active: boolean;
  created_at: string | null;
}

export interface AccessRequestRow {
  id: number;
  email: string;
  name: string | null;
  organization: string | null;
  plan_interest: string;
  message: string | null;
  source: string | null;
  created_at: string | null;
}

export interface EntitlementRow {
  email: string;
  plan: string;
  status: string | null;
  is_pro: boolean;
  comp: boolean;
  comp_note: string | null;
  comp_granted_by: string | null;
  comp_granted_at: string | null;
  has_stripe: boolean;
  current_period_end: string | null;
  created_at: string | null;
}

interface Page<T> {
  total: number;
  items: T[];
}

export const fetchAdminStats = (getToken: GetToken) =>
  authedFetch<AdminStats>('/admin/stats', getToken);

export function fetchSubscribers(
  getToken: GetToken,
  opts: { search?: string; active?: boolean; limit?: number; offset?: number } = {},
): Promise<Page<Subscriber>> {
  const p = new URLSearchParams();
  if (opts.search) p.set('search', opts.search);
  if (opts.active !== undefined) p.set('active', String(opts.active));
  p.set('limit', String(opts.limit ?? 100));
  p.set('offset', String(opts.offset ?? 0));
  return authedFetch<Page<Subscriber>>(`/admin/subscribers?${p}`, getToken);
}

export const setSubscriberActive = (getToken: GetToken, id: number, active: boolean) =>
  authedFetch<{ id: number; active: boolean }>(`/admin/subscribers/${id}/active`, getToken, {
    method: 'POST',
    body: JSON.stringify({ active }),
  });

export function fetchAccessRequests(
  getToken: GetToken,
  opts: { limit?: number; offset?: number } = {},
): Promise<Page<AccessRequestRow>> {
  const p = new URLSearchParams();
  p.set('limit', String(opts.limit ?? 100));
  p.set('offset', String(opts.offset ?? 0));
  return authedFetch<Page<AccessRequestRow>>(`/admin/access-requests?${p}`, getToken);
}

export function fetchEntitlements(
  getToken: GetToken,
  opts: { search?: string; plan?: string; limit?: number; offset?: number } = {},
): Promise<Page<EntitlementRow>> {
  const p = new URLSearchParams();
  if (opts.search) p.set('search', opts.search);
  if (opts.plan) p.set('plan', opts.plan);
  p.set('limit', String(opts.limit ?? 100));
  p.set('offset', String(opts.offset ?? 0));
  return authedFetch<Page<EntitlementRow>>(`/admin/entitlements?${p}`, getToken);
}

export const grantPro = (
  getToken: GetToken,
  body: { email: string; days?: number | null; note?: string | null },
) =>
  authedFetch<EntitlementRow>('/admin/grant-pro', getToken, {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const revokePro = (getToken: GetToken, email: string) =>
  authedFetch<EntitlementRow>('/admin/revoke-pro', getToken, {
    method: 'POST',
    body: JSON.stringify({ email }),
  });

// ── Account management ──────────────────────────────────────────────────────

export interface FirebaseInfo {
  uid: string;
  disabled: boolean;
  email_verified: boolean;
  providers: string[];
  created_at: string | null;
  last_sign_in_at: string | null;
}

export interface AccountDetail {
  email: string;
  exists: boolean;
  entitlement: EntitlementRow | null;
  firebase: FirebaseInfo | null;
  firebase_error: string | null;
  uids_known: string[];
  watchlist_count: number;
  settings_present: boolean;
  subscriptions: {
    id: number;
    scope: string;
    active: boolean;
    states: string[];
    instrument_types: string[];
    created_at: string | null;
  }[];
}

export const fetchAccount = (getToken: GetToken, email: string) =>
  authedFetch<AccountDetail>(`/admin/account?email=${encodeURIComponent(email)}`, getToken);

export const deleteAccountByEmail = (getToken: GetToken, email: string) =>
  authedFetch<{ deleted: boolean; email: string; uids: number; firebase_deleted: number }>(
    '/admin/account/delete',
    getToken,
    { method: 'POST', body: JSON.stringify({ email }) },
  );

export const setAccountDisabled = (getToken: GetToken, email: string, disabled: boolean) =>
  authedFetch<{ email: string; disabled: boolean }>('/admin/account/disable', getToken, {
    method: 'POST',
    body: JSON.stringify({ email, disabled }),
  });
