'use client';
/**
 * Saved studio packages — a signed-in user's packages, persisted in the account prefs
 * (/me/settings, free tier) so they follow the user across devices like the scope does.
 *
 * Each entry stores the spec as the same hash fragment the share link uses, so save/load
 * reuses the studio's codec verbatim (encodeSpecToHash / decodeSpecFromHash) and old
 * entries keep working as long as share links do. Writes go through PATCH /me/settings,
 * which merges server-side — only the studioPackages key is touched.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/auth/AuthContext';
import { fetchSettings, patchSettings } from '@/lib/userSettings';
import { decodeSpecFromHash, encodeSpecToHash, type StudioSpec } from '@/lib/studio';
import { track } from '@/lib/analytics';
import { formatDate } from '@/lib/utils';
import { SectionHeader } from '@/components/ui/SectionHeader';

export interface SavedPackage {
  id: string;
  name: string;
  /** The spec, encoded exactly like the share-link hash (no leading '#'). */
  hash: string;
  savedAt: string;
}

const PREFS_KEY = 'studioPackages';
const MAX_SAVED = 50;

function parseSaved(raw: unknown): SavedPackage[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (p): p is SavedPackage =>
      !!p &&
      typeof p.id === 'string' &&
      typeof p.name === 'string' &&
      typeof p.hash === 'string' &&
      typeof p.savedAt === 'string',
  );
}

const newId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `p${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;

export type SaveState = 'idle' | 'saving' | 'saved';

export function useSavedPackages() {
  const { user, getToken, openAuth, showToast } = useAuth();
  const [packages, setPackages] = useState<SavedPackage[]>([]);
  const [ready, setReady] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>('idle');

  // On sign-in adopt the account's saved packages; on sign-out drop them.
  useEffect(() => {
    if (!user) {
      setPackages([]);
      setReady(true);
      return;
    }
    let cancelled = false;
    (async () => {
      const prefs = await fetchSettings(await getToken());
      if (cancelled) return;
      setPackages(parseSaved(prefs[PREFS_KEY]));
      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [user, getToken]);

  // Optimistic update, reconcile on failure (the watch list's pattern).
  const persist = useCallback(
    async (next: SavedPackage[], prev: SavedPackage[]): Promise<boolean> => {
      setPackages(next);
      try {
        await patchSettings(await getToken(), { [PREFS_KEY]: next });
        return true;
      } catch {
        setPackages(prev);
        showToast("Couldn't sync your saved packages — try again.");
        return false;
      }
    },
    [getToken, showToast],
  );

  /** Save the current spec under its product name; a same-named entry is updated in place.
   *  Anonymous users are routed to sign-in (a free account is enough — prefs aren't Pro-gated). */
  const save = useCallback(
    async (spec: StudioSpec) => {
      if (!user) {
        openAuth();
        return;
      }
      const name = spec.product?.trim() || 'Untitled package';
      const existing = packages.find((p) => p.name.toLowerCase() === name.toLowerCase());
      if (!existing && packages.length >= MAX_SAVED) {
        showToast(`You can keep up to ${MAX_SAVED} saved packages — delete one first.`);
        return;
      }
      const entry: SavedPackage = {
        id: existing?.id ?? newId(),
        name,
        hash: encodeSpecToHash(spec),
        savedAt: new Date().toISOString(),
      };
      setSaveState('saving');
      const next = existing
        ? packages.map((p) => (p.id === entry.id ? entry : p))
        : [entry, ...packages];
      const ok = await persist(next, packages);
      setSaveState(ok ? 'saved' : 'idle');
      if (ok) {
        track('studio_package_save', { updated: Boolean(existing) });
        showToast(
          <>
            {existing ? 'Updated' : 'Saved'} “{name}” {existing ? 'in' : 'to'}{' '}
            <Link href="/company" className="text-green-accent underline hover:opacity-80">
              your portfolio
            </Link>
            .
          </>,
        );
        setTimeout(() => setSaveState('idle'), 1600);
      }
    },
    [user, packages, openAuth, persist, showToast],
  );

  const remove = useCallback(
    async (id: string) => {
      const ok = await persist(
        packages.filter((p) => p.id !== id),
        packages,
      );
      if (ok) track('studio_package_delete');
    },
    [packages, persist],
  );

  return { signedIn: Boolean(user), ready, packages, saveState, save, remove, openAuth };
}

/** The bench panel: the account's saved packages — load one back into the studio, or delete. */
export function SavedPackagesPanel({
  signedIn,
  ready,
  packages,
  onLoad,
  onDelete,
  onSignIn,
}: {
  signedIn: boolean;
  ready: boolean;
  packages: SavedPackage[];
  onLoad: (pkg: SavedPackage) => void;
  onDelete: (id: string) => void;
  onSignIn: () => void;
}) {
  return (
    <section className="rounded-panel border border-border-default bg-bg-secondary p-4">
      <p className="text-meta uppercase tracking-wider text-text-muted mb-1">Saved packages</p>
      {!signedIn ? (
        <p className="text-xs text-text-secondary leading-relaxed">
          <button
            type="button"
            onClick={onSignIn}
            className="text-green-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 rounded"
          >
            Sign in
          </button>{' '}
          to save this package to your account — it syncs with your watch list and settings across
          devices. A free account is enough.
        </p>
      ) : !ready ? (
        <p className="text-xs italic text-text-muted">Loading your saved packages…</p>
      ) : packages.length === 0 ? (
        <p className="text-xs text-text-secondary leading-relaxed">
          Nothing saved yet — <b className="text-text-primary">Save</b> in the bar at the top of the
          page stores this package to your account.
        </p>
      ) : (
        <>
          <ul className="space-y-1.5">
            {packages.map((p) => (
              <li
                key={p.id}
                className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-border-default bg-bg-tertiary px-3 py-2"
              >
                <button
                  type="button"
                  onClick={() => onLoad(p)}
                  title={`Load “${p.name}” into the studio`}
                  className="min-w-0 flex-1 truncate text-left text-xs font-semibold text-text-primary hover:text-green-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60 rounded"
                >
                  {p.name}
                </button>
                <span className="shrink-0 font-mono text-meta text-text-muted">
                  {formatDate(p.savedAt)}
                </span>
                <button
                  type="button"
                  onClick={() => onDelete(p.id)}
                  aria-label={`Delete ${p.name}`}
                  title={`Delete ${p.name}`}
                  className="shrink-0 rounded-full px-1.5 py-0.5 leading-none text-text-muted hover:text-urgency-high transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-2.5 text-meta text-text-muted">
            Also in{' '}
            <Link href="/company" className="text-green-accent hover:underline">
              My Portfolio →
            </Link>
          </p>
        </>
      )}
    </section>
  );
}

/** "My Portfolio" (/company) section: every package saved from the studio, with a one-line
 *  summary decoded from its spec. Opening one deep-links into the studio via the share-link
 *  hash, so the studio restores it through the exact same path as a shared URL. */
export function SavedPackagesSection() {
  const { signedIn, ready, packages, remove, openAuth } = useSavedPackages();

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Saved Packages"
        subtitle="Packages you built in the Packaging Studio — saved to your account, synced across devices."
      />
      {!signedIn ? (
        <div className="rounded-xl border border-border-default bg-bg-secondary p-8 text-center space-y-2">
          <p className="text-text-primary font-medium">Sign in to see your saved packages</p>
          <p className="text-text-secondary text-sm">
            Build a package in the{' '}
            <Link href="/studio" className="text-green-accent hover:underline">
              Packaging Studio
            </Link>{' '}
            and hit Save — it&rsquo;ll show up here. A free account is enough.
          </p>
          <button
            type="button"
            onClick={openAuth}
            className="mt-1 rounded-lg bg-green-accent px-4 py-2 text-sm font-semibold text-bg-primary hover:opacity-90 transition-opacity"
          >
            Sign in
          </button>
        </div>
      ) : !ready ? (
        <p className="text-text-muted text-sm">Loading your saved packages…</p>
      ) : packages.length === 0 ? (
        <div className="rounded-xl border border-border-default bg-bg-secondary p-8 text-center space-y-2">
          <p className="text-text-primary font-medium">No packages yet</p>
          <p className="text-text-secondary text-sm">
            Build one in the{' '}
            <Link href="/studio" className="text-green-accent hover:underline">
              Packaging Studio
            </Link>{' '}
            and hit <b className="text-text-primary">Save</b> — it&rsquo;ll show up here.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {packages.map((p) => {
            const spec = decodeSpecFromHash(p.hash);
            const summary = spec
              ? `${spec.components.length} component${spec.components.length === 1 ? '' : 's'} · ${
                  spec.markets.length ? spec.markets.join(', ') : 'no markets picked'
                }`
              : null;
            return (
              <div
                key={p.id}
                className="surface-card flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-text-primary">{p.name}</p>
                  <p className="text-xs text-text-muted">
                    {summary && <>{summary} · </>}saved {formatDate(p.savedAt)}
                  </p>
                </div>
                <Link
                  href={`/studio#${p.hash}`}
                  className="shrink-0 rounded-md border border-border-default bg-bg-tertiary px-3 py-1.5 text-xs text-text-secondary hover:border-green-accent hover:text-text-primary transition-colors"
                >
                  Open in Studio →
                </Link>
                <button
                  type="button"
                  onClick={() => remove(p.id)}
                  aria-label={`Delete ${p.name}`}
                  title={`Delete ${p.name}`}
                  className="shrink-0 rounded-full px-1.5 py-0.5 text-base leading-none text-text-muted hover:text-urgency-high transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent/60"
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
