'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** The watch list moved into "My Library" (/library). This route is kept as a redirect so old
 *  deep links (the Account page link, watchlist emails) still land on the watch list. */
export default function WatchlistRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/library');
  }, [router]);

  return <p className="p-6 text-text-muted text-sm">Redirecting to My Library…</p>;
}
