'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/**
 * "Ask the Atlas" folded into the unified Explore surface (the home page). This route now redirects
 * to `/`, preserving `?session=` so saved-thread deep links (from My Library) still reopen the
 * conversation there. Kept as a route (not deleted) so old links and bookmarks don't 404.
 */
export default function AskRedirect() {
  const router = useRouter();
  useEffect(() => {
    const qs = typeof window !== 'undefined' ? window.location.search : '';
    router.replace(`/${qs}`);
  }, [router]);
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <p className="text-text-muted text-sm">Taking you to Explore…</p>
    </div>
  );
}
