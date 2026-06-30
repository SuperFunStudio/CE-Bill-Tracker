'use client';
import { useCallback, useEffect, useState } from 'react';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { LockIcon } from '@/components/ui/icons';
import { useAuth } from '@/components/auth/AuthContext';
import {
  fetchAdminStats,
  fetchSubscribers,
  fetchAccessRequests,
  fetchEntitlements,
  setSubscriberActive,
  grantPro,
  revokePro,
  fetchAccount,
  deleteAccountByEmail,
  setAccountDisabled,
  fetchOutcomes,
  updateOutcome,
  approveOutcome,
  deleteOutcome,
  type AdminStats,
  type Subscriber,
  type AccessRequestRow,
  type EntitlementRow,
  type AccountDetail,
  type AdminOutcome,
  type OutcomeEdit,
} from '@/lib/admin';

type GetToken = () => Promise<string | null>;

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

export default function AdminPage() {
  const { user, loading, isAdmin, openAuth, getToken } = useAuth();

  if (loading) {
    return <Shell><p className="text-text-muted text-sm">Loading…</p></Shell>;
  }
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
    // Hidden console: a signed-in non-admin gets a plain not-found, not a hint that this exists.
    return (
      <Shell>
        <p className="text-text-muted text-sm text-center">404 — This page could not be found.</p>
      </Shell>
    );
  }
  return <Console getToken={getToken} adminEmail={user.email ?? ''} />;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="p-6 space-y-8 max-w-5xl mx-auto">
      <GazetteHeader title="Admin Console" subtitle="Sign-ups, complimentary upgrades, and data health." />
      {children}
    </div>
  );
}

function Console({ getToken, adminEmail }: { getToken: GetToken; adminEmail: string }) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [statsErr, setStatsErr] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const bump = useCallback(() => setReloadKey(k => k + 1), []);

  const loadStats = useCallback(async () => {
    setStatsErr(null);
    try {
      setStats(await fetchAdminStats(getToken));
    } catch (e) {
      setStatsErr(e instanceof Error ? e.message : 'Could not load stats.');
    }
  }, [getToken]);

  useEffect(() => {
    loadStats();
  }, [loadStats, reloadKey]);

  return (
    <Shell>
      <StatsPanel stats={stats} error={statsErr} />
      <OutcomesPanel getToken={getToken} reloadKey={reloadKey} />
      <GrantPanel getToken={getToken} onChange={bump} />
      <AccountPanel getToken={getToken} adminEmail={adminEmail} onChange={bump} />
      <EntitlementsPanel getToken={getToken} reloadKey={reloadKey} onChange={bump} />
      <SubscribersPanel getToken={getToken} reloadKey={reloadKey} />
      <AccessRequestsPanel getToken={getToken} reloadKey={reloadKey} />
      <p className="text-text-muted text-xs text-center pt-2">Signed in as admin · {adminEmail}</p>
    </Shell>
  );
}

// ── Layout primitives ──────────────────────────────────────────────────────

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border-default bg-bg-secondary p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-serif text-lg text-text-primary">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Pill({ children, tone = 'muted' }: { children: React.ReactNode; tone?: 'muted' | 'green' | 'amber' | 'red' }) {
  const tones: Record<string, string> = {
    muted: 'text-text-muted border-border-default',
    green: 'text-green-accent border-green-accent/40',
    amber: 'text-amber-400 border-amber-400/40',
    red: 'text-red-400 border-red-400/40',
  };
  return (
    <span className={`text-meta uppercase tracking-wider border rounded-full px-1.5 py-0.5 ${tones[tone]}`}>
      {children}
    </span>
  );
}

function Th({ children }: { children?: React.ReactNode }) {
  return <th className="text-left font-medium text-text-muted px-2 py-1.5 whitespace-nowrap">{children}</th>;
}
function Td({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-2 py-1.5 align-top ${className}`}>{children}</td>;
}

function SearchBar({ placeholder, onSearch }: { placeholder: string; onSearch: (q: string) => void }) {
  const [q, setQ] = useState('');
  return (
    <form
      onSubmit={e => { e.preventDefault(); onSearch(q.trim()); }}
      className="flex items-center gap-2"
    >
      <input
        value={q}
        onChange={e => setQ(e.target.value)}
        placeholder={placeholder}
        className="rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-green-accent focus:outline-none"
      />
      <button type="submit" className="rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary transition-colors">
        Search
      </button>
    </form>
  );
}

// ── Stats ───────────────────────────────────────────────────────────────────

function StatsPanel({ stats, error }: { stats: AdminStats | null; error: string | null }) {
  if (error) return <Section title="Overview"><p className="text-red-400 text-xs">{error}</p></Section>;
  if (!stats) return <Section title="Overview"><p className="text-text-muted text-sm">Loading…</p></Section>;
  const f = stats.data_freshness;
  return (
    <Section title="Overview">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Stat label="Subscribers" value={stats.subscribers_active} sub={`${stats.subscribers_total} all-time`} />
        <Stat label="Pro (total)" value={stats.pro_total} sub={`${stats.pro_paid} paid`} />
        <Stat label="Comp Pro" value={stats.pro_comp} sub="complimentary" />
        <Stat label="Leads" value={stats.access_requests} sub="access requests" />
        <Stat label="Bills" value={stats.bills_total} sub={`${stats.bills_relevant} relevant`} />
        <Stat label="Fed actions" value={f.federal_last_published ? '✓' : '—'} sub="see freshness" />
      </div>
      <div className="rounded-lg border border-border-default bg-bg-primary p-3 text-xs text-text-secondary space-y-1">
        <p className="text-text-muted uppercase tracking-wider text-meta mb-1">Data freshness</p>
        <p>Bills last synced (fetched): <span className="text-text-primary">{fmtDateTime(f.bills_last_fetched)}</span></p>
        <p>Bills last updated in DB: <span className="text-text-primary">{fmtDateTime(f.bills_last_updated)}</span></p>
        <p>Latest tracked action <span className="text-text-muted">(EPR-relevant)</span>: <span className="text-text-primary">{fmtDate(f.bills_last_action)}</span></p>
        <p>Latest federal action: <span className="text-text-primary">{fmtDate(f.federal_last_published)}</span></p>
      </div>
    </Section>
  );
}

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-3">
      <p className="text-text-muted text-meta uppercase tracking-wider">{label}</p>
      <p className="font-serif text-2xl text-text-primary leading-tight">{value}</p>
      {sub && <p className="text-text-muted text-meta">{sub}</p>}
    </div>
  );
}

// ── Grant complimentary Pro ───────────────────────────────────────────────────

function GrantPanel({ getToken, onChange }: { getToken: GetToken; onChange: () => void }) {
  const [email, setEmail] = useState('');
  const [days, setDays] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setMsg(null);
    setBusy(true);
    try {
      const parsedDays = days.trim() ? Number(days.trim()) : null;
      if (parsedDays !== null && (!Number.isFinite(parsedDays) || parsedDays <= 0)) {
        throw new Error('Days must be a positive number, or blank for indefinite.');
      }
      const res = await grantPro(getToken, { email: email.trim(), days: parsedDays, note: note.trim() || null });
      setMsg({
        ok: true,
        text: `Granted Pro to ${res.email}${res.current_period_end ? ` until ${fmtDate(res.current_period_end)}` : ' (indefinite)'}.`,
      });
      setEmail(''); setDays(''); setNote('');
      onChange();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : 'Could not grant Pro.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="Grant complimentary Pro">
      <p className="text-text-secondary text-sm leading-relaxed">
        Give any email a Pro seat with no Stripe charge. Leave <span className="text-text-primary">days</span> blank for an
        indefinite grant, or set a number to auto-expire. Re-granting an existing comp account refreshes its expiry.
      </p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[2fr_1fr] items-start">
        <input
          type="email"
          required
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="person@example.com"
          className="rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-green-accent focus:outline-none"
        />
        <input
          type="number"
          min={1}
          value={days}
          onChange={e => setDays(e.target.value)}
          placeholder="days (blank = forever)"
          className="rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-green-accent focus:outline-none"
        />
        <input
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="note — why (e.g. design-jam attendee)"
          className="sm:col-span-2 rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-green-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy}
          className="sm:col-span-2 justify-self-start inline-flex items-center gap-2 rounded-lg bg-green-accent text-bg-primary px-4 py-2 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {busy ? 'Granting…' : 'Grant Pro'}
        </button>
      </form>
      {msg && <p className={`text-xs ${msg.ok ? 'text-green-accent' : 'text-red-400'}`}>{msg.text}</p>}
    </Section>
  );
}

// ── Account management ─────────────────────────────────────────────────────────

function AccountPanel({ getToken, adminEmail, onChange }: { getToken: GetToken; adminEmail: string; onChange: () => void }) {
  const [query, setQuery] = useState('');
  const [acct, setAcct] = useState<AccountDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const isSelf = !!acct?.email && acct.email.toLowerCase() === adminEmail.toLowerCase();

  async function lookup(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null); setNotice(null); setConfirm(''); setAcct(null);
    setBusy(true);
    try {
      setAcct(await fetchAccount(getToken, query.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lookup failed.');
    } finally {
      setBusy(false);
    }
  }

  async function refresh() {
    if (!acct) return;
    try { setAcct(await fetchAccount(getToken, acct.email)); } catch { /* keep prior */ }
  }

  async function toggleDisabled() {
    if (!acct?.firebase || busy) return;
    setError(null); setNotice(null); setBusy(true);
    try {
      const next = !acct.firebase.disabled;
      await setAccountDisabled(getToken, acct.email, next);
      setNotice(next ? 'Sign-in disabled.' : 'Sign-in re-enabled.');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update sign-in.');
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!acct || busy) return;
    setError(null); setNotice(null); setBusy(true);
    try {
      const res = await deleteAccountByEmail(getToken, acct.email);
      setNotice(`Deleted ${res.email} — ${res.uids} Firebase id(s), ${res.firebase_deleted} auth user(s) removed.`);
      setAcct(null); setQuery(''); setConfirm('');
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete account.');
    } finally {
      setBusy(false);
    }
  }

  const armed = !!acct && confirm.trim().toLowerCase() === acct.email.toLowerCase();

  return (
    <Section title="Account management" action={
      <form onSubmit={lookup} className="flex items-center gap-2">
        <input
          type="email"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="email to look up…"
          className="rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-green-accent focus:outline-none"
        />
        <button type="submit" disabled={busy} className="rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50">
          {busy && !acct ? '…' : 'Look up'}
        </button>
      </form>
    }>
      <p className="text-text-secondary text-sm leading-relaxed">
        Look up any account by email to inspect its identity and data, freeze sign-in, or permanently delete it.
      </p>
      {error && <p className="text-red-400 text-xs">{error}</p>}
      {notice && <p className="text-green-accent text-xs">{notice}</p>}

      {acct && !acct.exists && (
        <p className="text-text-muted text-sm">No account, entitlement, or data found for <span className="text-text-primary">{acct.email}</span>.</p>
      )}

      {acct && acct.exists && (
        <div className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="Email" value={acct.email} />
            <Field label="Plan" value={
              acct.entitlement
                ? <span className="inline-flex items-center gap-1.5">
                    {acct.entitlement.is_pro ? <Pill tone="green">Pro</Pill> : <Pill>{acct.entitlement.plan}</Pill>}
                    {acct.entitlement.comp && <Pill tone="amber">Comp</Pill>}
                  </span>
                : 'No entitlement'
            } />
            <Field label="Sign-in" value={
              acct.firebase
                ? (acct.firebase.disabled ? <Pill tone="red">Disabled</Pill> : <Pill tone="green">Active</Pill>)
                : <span className="text-text-muted">{acct.firebase_error ? 'Firebase unavailable' : 'No Firebase user'}</span>
            } />
            <Field label="Providers" value={acct.firebase?.providers?.join(', ') || '—'} />
            <Field label="Created" value={fmtDateTime(acct.firebase?.created_at)} />
            <Field label="Last sign-in" value={fmtDateTime(acct.firebase?.last_sign_in_at)} />
            <Field label="Watchlist" value={`${acct.watchlist_count} bill(s)`} />
            <Field label="Subscriptions" value={`${acct.subscriptions.length} · settings ${acct.settings_present ? 'saved' : 'none'}`} />
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            {acct.firebase && (
              <button
                onClick={toggleDisabled}
                disabled={busy || (!acct.firebase.disabled && isSelf)}
                className="rounded-lg border border-border-default bg-bg-primary px-4 py-2 text-sm text-text-secondary hover:text-text-primary transition-colors disabled:opacity-40"
                title={!acct.firebase.disabled && isSelf ? 'You cannot disable your own account' : undefined}
              >
                {busy ? '…' : acct.firebase.disabled ? 'Re-enable sign-in' : 'Disable sign-in'}
              </button>
            )}
          </div>

          {/* Delete — type-to-confirm */}
          {!isSelf ? (
            <div className="rounded-lg border border-red-500/40 bg-red-500/5 p-4 space-y-2">
              <p className="text-red-400 text-sm font-medium">Delete account</p>
              <p className="text-text-secondary text-xs leading-relaxed">
                Cancels Stripe, erases watchlist/settings/subscriptions/entitlement, and removes the Firebase sign-in. Cannot be undone.
              </p>
              <label className="block text-text-muted text-xs">
                Type <span className="text-text-primary">{acct.email}</span> to confirm:
              </label>
              <input
                type="email"
                autoComplete="off"
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                placeholder={acct.email}
                className="w-full max-w-sm rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-red-500/60 focus:outline-none"
              />
              <button
                onClick={remove}
                disabled={!armed || busy}
                className="inline-flex items-center gap-2 rounded-lg bg-red-600 text-white px-4 py-2 text-sm font-medium hover:bg-red-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {busy ? 'Deleting…' : 'Delete account'}
              </button>
            </div>
          ) : (
            <p className="text-text-muted text-xs">This is your own admin account — manage it from the Account page.</p>
          )}
        </div>
      )}
    </Section>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary px-3 py-2">
      <p className="text-text-muted text-meta uppercase tracking-wider">{label}</p>
      <p className="text-text-primary text-sm">{value}</p>
    </div>
  );
}

// ── Entitlements ──────────────────────────────────────────────────────────────

function EntitlementsPanel({ getToken, reloadKey, onChange }: { getToken: GetToken; reloadKey: number; onChange: () => void }) {
  const [rows, setRows] = useState<EntitlementRow[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busyEmail, setBusyEmail] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchEntitlements(getToken, { search: search || undefined });
      setRows(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load entitlements.');
    }
  }, [getToken, search]);

  useEffect(() => { load(); }, [load, reloadKey]);

  async function revoke(email: string) {
    if (busyEmail) return;
    setBusyEmail(email);
    try {
      await revokePro(getToken, email);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not revoke.');
    } finally {
      setBusyEmail(null);
    }
  }

  return (
    <Section title={`Entitlements (${total})`} action={<SearchBar placeholder="Search email…" onSearch={setSearch} />}>
      {error && <p className="text-red-400 text-xs">{error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead><tr className="border-b border-border-default">
            <Th>Email</Th><Th>Plan</Th><Th>Source</Th><Th>Renews / expires</Th><Th>Comp note</Th><Th></Th>
          </tr></thead>
          <tbody>
            {rows.map(e => (
              <tr key={e.email} className="border-b border-border-default/50">
                <Td className="text-text-primary">{e.email}</Td>
                <Td>
                  <span className="inline-flex items-center gap-1.5">
                    {e.is_pro ? <Pill tone="green">Pro</Pill> : <Pill>{e.plan}</Pill>}
                    {e.status && e.status !== 'active' && <Pill tone="amber">{e.status}</Pill>}
                  </span>
                </Td>
                <Td>{e.comp ? <Pill tone="amber">Comp</Pill> : e.has_stripe ? <Pill tone="green">Stripe</Pill> : <Pill>—</Pill>}</Td>
                <Td className="text-text-secondary whitespace-nowrap">{e.current_period_end ? fmtDate(e.current_period_end) : e.comp ? 'Indefinite' : '—'}</Td>
                <Td className="text-text-muted max-w-[16rem]">
                  {e.comp_note || '—'}
                  {e.comp_granted_by && <span className="block text-meta text-text-muted/70">by {e.comp_granted_by}</span>}
                </Td>
                <Td>
                  {e.comp && e.plan === 'pro' && (
                    <button
                      onClick={() => revoke(e.email)}
                      disabled={busyEmail === e.email}
                      className="text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
                    >
                      {busyEmail === e.email ? '…' : 'Revoke'}
                    </button>
                  )}
                </Td>
              </tr>
            ))}
            {rows.length === 0 && !error && (
              <tr><Td className="text-text-muted">No entitlements.</Td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

// ── Subscribers ───────────────────────────────────────────────────────────────

function SubscribersPanel({ getToken, reloadKey }: { getToken: GetToken; reloadKey: number }) {
  const [rows, setRows] = useState<Subscriber[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchSubscribers(getToken, { search: search || undefined });
      setRows(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load subscribers.');
    }
  }, [getToken, search]);

  useEffect(() => { load(); }, [load, reloadKey]);

  async function toggle(s: Subscriber) {
    if (busyId) return;
    setBusyId(s.id);
    try {
      await setSubscriberActive(getToken, s.id, !s.active);
      setRows(rs => rs.map(r => (r.id === s.id ? { ...r, active: !r.active } : r)));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update.');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Section title={`Free sign-ups (${total})`} action={<SearchBar placeholder="Search email / org…" onSearch={setSearch} />}>
      {error && <p className="text-red-400 text-xs">{error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead><tr className="border-b border-border-default">
            <Th>Email</Th><Th>Org</Th><Th>Topics</Th><Th>States</Th><Th>Joined</Th><Th>Status</Th><Th></Th>
          </tr></thead>
          <tbody>
            {rows.map(s => (
              <tr key={s.id} className="border-b border-border-default/50">
                <Td className="text-text-primary">{s.email || '—'}</Td>
                <Td className="text-text-secondary">{s.organization || '—'}</Td>
                <Td className="text-text-muted max-w-[12rem]">{(s.instrument_types || []).join(', ') || '—'}</Td>
                <Td className="text-text-muted">{(s.states || []).join(', ') || '—'}</Td>
                <Td className="text-text-secondary whitespace-nowrap">{fmtDate(s.created_at)}</Td>
                <Td>{s.active ? <Pill tone="green">Active</Pill> : <Pill tone="red">Muted</Pill>}</Td>
                <Td>
                  <button
                    onClick={() => toggle(s)}
                    disabled={busyId === s.id}
                    className="text-xs text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50"
                  >
                    {busyId === s.id ? '…' : s.active ? 'Mute' : 'Unmute'}
                  </button>
                </Td>
              </tr>
            ))}
            {rows.length === 0 && !error && (
              <tr><Td className="text-text-muted">No subscribers.</Td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

// ── Access requests (leads) ────────────────────────────────────────────────────

function AccessRequestsPanel({ getToken, reloadKey }: { getToken: GetToken; reloadKey: number }) {
  const [rows, setRows] = useState<AccessRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchAccessRequests(getToken);
      setRows(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load leads.');
    }
  }, [getToken]);

  useEffect(() => { load(); }, [load, reloadKey]);

  return (
    <Section title={`Access-request leads (${total})`}>
      {error && <p className="text-red-400 text-xs">{error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead><tr className="border-b border-border-default">
            <Th>Email</Th><Th>Name</Th><Th>Org</Th><Th>Interest</Th><Th>Source</Th><Th>Message</Th><Th>When</Th>
          </tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} className="border-b border-border-default/50">
                <Td className="text-text-primary">{r.email}</Td>
                <Td className="text-text-secondary">{r.name || '—'}</Td>
                <Td className="text-text-secondary">{r.organization || '—'}</Td>
                <Td><Pill tone="green">{r.plan_interest}</Pill></Td>
                <Td className="text-text-muted">{r.source || '—'}</Td>
                <Td className="text-text-muted max-w-[16rem]">{r.message || '—'}</Td>
                <Td className="text-text-secondary whitespace-nowrap">{fmtDate(r.created_at)}</Td>
              </tr>
            ))}
            {rows.length === 0 && !error && (
              <tr><Td className="text-text-muted">No leads yet.</Td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

// ── Real-world-outcome review ──────────────────────────────────────────────────
// The review queue for machine-researched documented outcomes (scripts/propose_bill_outcomes.py).
// Each lands as reviewed=false and is invisible on the public Insights page until approved here.

const DIRECTION_TONE: Record<string, 'green' | 'red' | 'amber'> = {
  positive: 'green',
  negative: 'red',
  mixed: 'amber',
};

function figureText(o: AdminOutcome | OutcomeEdit): string {
  if (o.metric_display) return o.metric_display;
  if (o.metric_value !== null && o.metric_value !== undefined) {
    return `${o.metric_value}${o.metric_unit ? ` ${o.metric_unit}` : ''}`;
  }
  return '—';
}

function OutcomesPanel({ getToken, reloadKey }: { getToken: GetToken; reloadKey: number }) {
  const [items, setItems] = useState<AdminOutcome[]>([]);
  const [unreviewed, setUnreviewed] = useState(0);
  const [total, setTotal] = useState(0);
  const [pendingOnly, setPendingOnly] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [editId, setEditId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchOutcomes(getToken, pendingOnly ? { reviewed: false } : {});
      setItems(res.items);
      setUnreviewed(res.unreviewed);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load outcomes.');
    }
  }, [getToken, pendingOnly]);

  useEffect(() => { load(); }, [load, reloadKey]);

  async function approve(id: number) {
    if (busyId) return;
    setBusyId(id);
    setError(null);
    try {
      await approveOutcome(getToken, id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not approve.');
    } finally {
      setBusyId(null);
    }
  }

  async function unapprove(id: number) {
    if (busyId) return;
    setBusyId(id);
    setError(null);
    try {
      await updateOutcome(getToken, id, { reviewed: false });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not unpublish.');
    } finally {
      setBusyId(null);
    }
  }

  async function reject(id: number) {
    if (busyId) return;
    setBusyId(id);
    setError(null);
    try {
      await deleteOutcome(getToken, id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reject.');
    } finally {
      setBusyId(null);
    }
  }

  async function save(id: number, draft: OutcomeEdit) {
    if (busyId) return;
    setBusyId(id);
    setError(null);
    try {
      await updateOutcome(getToken, id, draft);
      setEditId(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save.');
    } finally {
      setBusyId(null);
    }
  }

  const action = (
    <button
      onClick={() => setPendingOnly(p => !p)}
      className="rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary transition-colors"
    >
      {pendingOnly ? 'Show all' : 'Pending only'}
    </button>
  );

  return (
    <Section title={`Real-world outcomes — ${unreviewed} pending review`} action={action}>
      <p className="text-text-secondary text-sm leading-relaxed">
        Machine-researched documented outcomes from <span className="text-text-primary">propose_bill_outcomes.py</span>,
        awaiting a human. Each is invisible on the public Insights page until you{' '}
        <span className="text-green-accent">approve</span> it. Verify the figure against its source, fix anything
        wrong, or reject it. {pendingOnly ? `${unreviewed} pending` : `${total} total`}.
      </p>
      {error && <p className="text-red-400 text-xs">{error}</p>}
      <div className="space-y-3">
        {items.map(o =>
          editId === o.id ? (
            <OutcomeEditor
              key={o.id}
              outcome={o}
              busy={busyId === o.id}
              onCancel={() => setEditId(null)}
              onSave={draft => save(o.id, draft)}
            />
          ) : (
            <OutcomeCard
              key={o.id}
              outcome={o}
              busy={busyId === o.id}
              onApprove={() => approve(o.id)}
              onUnapprove={() => unapprove(o.id)}
              onEdit={() => setEditId(o.id)}
              onReject={() => reject(o.id)}
            />
          ),
        )}
        {items.length === 0 && !error && (
          <p className="text-text-muted text-sm">
            {pendingOnly ? 'Nothing pending — the queue is clear.' : 'No outcomes yet.'}
          </p>
        )}
      </div>
    </Section>
  );
}

function OutcomeCard({
  outcome: o, busy, onApprove, onUnapprove, onEdit, onReject,
}: {
  outcome: AdminOutcome;
  busy: boolean;
  onApprove: () => void;
  onUnapprove: () => void;
  onEdit: () => void;
  onReject: () => void;
}) {
  const [confirmReject, setConfirmReject] = useState(false);
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-4 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={DIRECTION_TONE[o.direction] ?? 'muted'}>{o.direction}</Pill>
        {o.reviewed ? <Pill tone="green">Live</Pill> : <Pill tone="amber">Pending</Pill>}
        {o.attribution && <Pill>{o.attribution}</Pill>}
        <span className="text-text-muted text-meta">
          {o.state} {o.bill_number} · conf {o.confidence ?? '—'}
        </span>
      </div>
      <p className="text-text-primary text-sm font-medium">{o.law_title || `${o.state} ${o.bill_number}`}</p>
      <p className="text-text-primary text-sm">
        <span className="font-serif text-lg">{figureText(o)}</span>
        {o.metric_label && <span className="text-text-secondary"> {o.metric_label}</span>}
      </p>
      <p className="text-text-secondary text-sm leading-relaxed">{o.summary}</p>
      <p className="text-text-muted text-xs">
        {o.source_name || 'source'}
        {o.source_url && (
          <>
            {' · '}
            <a href={o.source_url} target="_blank" rel="noopener noreferrer" className="text-green-accent hover:underline break-all">
              {o.source_url}
            </a>
          </>
        )}
        {o.as_of_date && <span> · as of {fmtDate(o.as_of_date)}</span>}
      </p>
      {o.direction !== 'positive' && o.remediation_note && (
        <p className="text-xs text-green-accent">
          → Fixed by {o.remediation_bill_number || 'a later law'}
          {o.remediated_by_bill_id && <Pill tone="green">linked</Pill>}{' '}
          <span className="text-text-secondary">{o.remediation_note}</span>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        {o.reviewed ? (
          <button onClick={onUnapprove} disabled={busy} className="text-xs text-amber-400 hover:text-amber-300 transition-colors disabled:opacity-50">
            {busy ? '…' : 'Unpublish'}
          </button>
        ) : (
          <button onClick={onApprove} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-green-accent text-bg-primary px-3 py-1.5 text-xs font-medium hover:opacity-90 transition-opacity disabled:opacity-50">
            {busy ? 'Approving…' : 'Approve → publish'}
          </button>
        )}
        <button onClick={onEdit} disabled={busy} className="text-xs text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50">
          Edit
        </button>
        {confirmReject ? (
          <span className="inline-flex items-center gap-2">
            <span className="text-text-muted text-xs">Delete?</span>
            <button onClick={onReject} disabled={busy} className="text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50">
              {busy ? '…' : 'Yes, reject'}
            </button>
            <button onClick={() => setConfirmReject(false)} className="text-xs text-text-muted hover:text-text-secondary transition-colors">
              Cancel
            </button>
          </span>
        ) : (
          <button onClick={() => setConfirmReject(true)} disabled={busy} className="text-xs text-red-400/80 hover:text-red-300 transition-colors disabled:opacity-50">
            Reject
          </button>
        )}
      </div>
    </div>
  );
}

// All-string draft so numeric inputs edit cleanly; coerced to OutcomeEdit on save.
interface OutcomeDraft {
  direction: string;
  attribution: string;
  metric_label: string;
  metric_value: string;
  metric_unit: string;
  metric_display: string;
  summary: string;
  as_of_date: string;
  source_name: string;
  source_url: string;
  law_title: string;
  confidence: string;
  remediation_note: string;
  remediation_bill_number: string;
}

function OutcomeEditor({
  outcome: o, busy, onCancel, onSave,
}: {
  outcome: AdminOutcome;
  busy: boolean;
  onCancel: () => void;
  onSave: (draft: OutcomeEdit) => void;
}) {
  const [d, setD] = useState<OutcomeDraft>({
    direction: o.direction,
    attribution: o.attribution ?? '',
    metric_label: o.metric_label ?? '',
    metric_value: o.metric_value?.toString() ?? '',
    metric_unit: o.metric_unit ?? '',
    metric_display: o.metric_display ?? '',
    summary: o.summary,
    as_of_date: o.as_of_date ?? '',
    source_name: o.source_name ?? '',
    source_url: o.source_url ?? '',
    law_title: o.law_title ?? '',
    confidence: o.confidence?.toString() ?? '',
    remediation_note: o.remediation_note ?? '',
    remediation_bill_number: o.remediation_bill_number ?? '',
  });
  const set = (patch: Partial<OutcomeDraft>) => setD(prev => ({ ...prev, ...patch }));

  function submit() {
    // Normalise blanks → null; numbers parsed; build a clean OutcomeEdit.
    const num = (v: string) => {
      if (v.trim() === '') return null;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    };
    const str = (v: string) => v.trim() || null;
    onSave({
      direction: d.direction,
      attribution: str(d.attribution) ?? undefined,
      summary: d.summary,
      metric_value: num(d.metric_value),
      confidence: num(d.confidence),
      metric_label: str(d.metric_label),
      metric_unit: str(d.metric_unit),
      metric_display: str(d.metric_display),
      as_of_date: str(d.as_of_date),
      source_name: str(d.source_name),
      source_url: str(d.source_url),
      law_title: str(d.law_title),
      remediation_note: str(d.remediation_note),
      remediation_bill_number: str(d.remediation_bill_number),
    });
  }

  return (
    <div className="rounded-lg border border-green-accent/40 bg-green-dark/10 p-4 space-y-3">
      <p className="text-text-muted text-meta uppercase tracking-wider">
        Editing · {o.state} {o.bill_number}
      </p>
      <EditField label="Law title">
        <TextInput value={d.law_title ?? ''} onChange={v => set({ law_title: v })} />
      </EditField>
      <div className="grid sm:grid-cols-2 gap-3">
        <EditField label="Direction">
          <Select value={d.direction ?? ''} onChange={v => set({ direction: v })} options={['positive', 'negative', 'mixed']} />
        </EditField>
        <EditField label="Attribution">
          <Select value={d.attribution ?? ''} onChange={v => set({ attribution: v })} options={['direct', 'program', 'associated']} />
        </EditField>
        <EditField label="Metric value">
          <TextInput value={d.metric_value ?? ''} onChange={v => set({ metric_value: v })} placeholder="e.g. 45" />
        </EditField>
        <EditField label="Metric unit">
          <TextInput value={d.metric_unit ?? ''} onChange={v => set({ metric_unit: v })} placeholder="acres" />
        </EditField>
        <EditField label="Metric label">
          <TextInput value={d.metric_label ?? ''} onChange={v => set({ metric_label: v })} placeholder="of oyster reef restored" />
        </EditField>
        <EditField label="Metric display (override)">
          <TextInput value={d.metric_display ?? ''} onChange={v => set({ metric_display: v })} placeholder="157k → 231k tons (+47%)" />
        </EditField>
        <EditField label="As-of date (YYYY-MM-DD)">
          <TextInput value={d.as_of_date ?? ''} onChange={v => set({ as_of_date: v })} placeholder="2025-10-01" />
        </EditField>
        <EditField label="Confidence (0–1)">
          <TextInput value={d.confidence ?? ''} onChange={v => set({ confidence: v })} placeholder="0.7" />
        </EditField>
        <EditField label="Source name">
          <TextInput value={d.source_name ?? ''} onChange={v => set({ source_name: v })} />
        </EditField>
        <EditField label="Source URL">
          <TextInput value={d.source_url ?? ''} onChange={v => set({ source_url: v })} />
        </EditField>
      </div>
      <EditField label="Summary">
        <textarea
          value={d.summary ?? ''}
          onChange={e => set({ summary: e.target.value })}
          rows={4}
          className="w-full rounded-lg border border-border-default bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-green-accent focus:outline-none"
        />
      </EditField>
      {d.direction !== 'positive' && (
        <div className="grid sm:grid-cols-[2fr_1fr] gap-3">
          <EditField label="Remediation — how a later law fixed it">
            <TextInput value={d.remediation_note ?? ''} onChange={v => set({ remediation_note: v })}
              placeholder="Closed the loophole via SB 1053 (2024)…" />
          </EditField>
          <EditField label="Fixing bill # (links if tracked)">
            <TextInput value={d.remediation_bill_number ?? ''} onChange={v => set({ remediation_bill_number: v })}
              placeholder="SB1053" />
          </EditField>
        </div>
      )}
      <div className="flex items-center gap-3">
        <button onClick={submit} disabled={busy} className="rounded-lg bg-green-accent text-bg-primary px-4 py-1.5 text-xs font-medium hover:opacity-90 transition-opacity disabled:opacity-50">
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button onClick={onCancel} disabled={busy} className="text-xs text-text-muted hover:text-text-secondary transition-colors disabled:opacity-50">
          Cancel
        </button>
        <span className="text-text-muted text-meta">Saving does not publish — approve separately.</span>
      </div>
    </div>
  );
}

function EditField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-text-muted text-meta uppercase tracking-wider">{label}</span>
      {children}
    </label>
  );
}

function TextInput({
  value, onChange, placeholder,
}: {
  value: string | number;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-green-accent focus:outline-none"
    />
  );
}

function Select({
  value, onChange, options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full rounded-lg border border-border-default bg-bg-primary px-3 py-1.5 text-sm text-text-primary focus:border-green-accent focus:outline-none"
    >
      {options.map(opt => (
        <option key={opt} value={opt}>{opt}</option>
      ))}
    </select>
  );
}
