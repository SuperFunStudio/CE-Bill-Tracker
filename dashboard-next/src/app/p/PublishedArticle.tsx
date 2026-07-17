'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchPublishedArticle, type PublishedArticle as Article } from '@/lib/research-admin';
import { MarkdownLite } from '@/components/ui/MarkdownLite';

// Reads ?token=… and renders the published article. Kept out of page.tsx so that stays a server
// component for the noindex metadata while this half runs on the client.

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

export function PublishedArticle() {
  const [state, setState] = useState<'loading' | 'ok' | 'error'>('loading');
  const [article, setArticle] = useState<Article | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token') ?? '';
    if (!token) {
      setState('error');
      setError('No article token.');
      return;
    }
    fetchPublishedArticle(token)
      .then(a => { setArticle(a); setState('ok'); })
      .catch(e => { setError(e instanceof Error ? e.message : 'Could not load this article.'); setState('error'); });
  }, []);

  if (state === 'loading') {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <div className="h-24 w-full animate-pulse rounded-lg bg-bg-tertiary" />
      </div>
    );
  }

  if (state === 'error' || !article) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center space-y-3">
        <p className="text-text-secondary">{error}</p>
        <Link href="/" className="text-green-accent hover:underline text-sm">Go to Battle of the Bills →</Link>
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-3xl px-6 py-10 space-y-6">
      <header className="space-y-2">
        <p className="text-[rgb(var(--green-accent))] text-xs font-semibold uppercase tracking-wider">
          Battle of the Bills
        </p>
        <h1 className="font-serif text-3xl text-text-primary leading-tight">{article.title}</h1>
        {article.dek && <p className="text-text-secondary text-lg leading-relaxed">{article.dek}</p>}
        {article.published_at && <p className="text-text-muted text-xs">{fmtDate(article.published_at)}</p>}
      </header>

      <div className="border-t border-border-default pt-6">
        <MarkdownLite text={article.body_markdown} />
      </div>

      <footer className="border-t border-border-default pt-6 text-center">
        <p className="text-text-secondary text-sm">
          Grounded in the circular-economy legislation corpus at{' '}
          <Link href="/" className="text-green-accent hover:underline">Battle of the Bills</Link>.
        </p>
      </footer>
    </article>
  );
}
