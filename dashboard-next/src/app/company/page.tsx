'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** "My Library" moved from /company to /library. This route is kept as a redirect so old deep links
 *  (bookmarks, older emails, external links) still land in the right place. Mirrors the /watchlist
 *  stub. Both /company and /library are robots-disallowed (see app/robots.ts). */
export default function CompanyRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/library');
  }, [router]);

  return <p className="p-6 text-text-muted text-sm">Redirecting to My Library…</p>;
}
