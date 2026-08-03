'use client';
import { useState } from 'react';
import { billHref } from '@/lib/utils';
import { track } from '@/lib/analytics';
import { CheckIcon } from '@/components/ui/icons';

// The canonical origin for a shareable bill link — always the pretty, indexable /bill/[id]/[slug]
// page, never the ?bill= modal URL. Matches metadataBase in app/layout.tsx.
const SITE_URL = 'https://www.atlascircular.com';

interface ShareBill {
  id: number;
  bill_number?: string | null;
  title?: string | null;
}

/**
 * "Share" a bill: on mobile it opens the native share sheet; elsewhere it copies the canonical
 * /bill/[id]/[slug] URL to the clipboard (with a brief "Link copied" confirmation). So a user in the
 * quick-look modal can grab the same clean, indexable link Google sees — not the ?bill= modal URL.
 */
export function ShareBillButton({ bill, className = '' }: { bill: ShareBill; className?: string }) {
  const [copied, setCopied] = useState(false);
  const url = `${SITE_URL}${billHref(bill)}`;

  async function onShare() {
    const isMobile =
      typeof navigator !== 'undefined' && /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);
    if (isMobile && typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({ title: bill.title ?? 'Bill', url });
        track('bill_share', { bill_id: bill.id, method: 'native' });
        return;
      } catch {
        /* user dismissed the sheet or it's unsupported — fall through to copy */
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      track('bill_share', { bill_id: bill.id, method: 'copy' });
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard blocked (insecure context / permissions) — last-resort manual copy.
      window.prompt('Copy this link to the bill:', url);
    }
  }

  return (
    <button
      type="button"
      onClick={onShare}
      aria-label="Copy a shareable link to this bill"
      className={`inline-flex items-center gap-1.5 text-sm transition-colors ${
        copied ? 'text-green-accent' : 'text-text-muted hover:text-text-primary'
      } ${className}`}
    >
      {copied ? <CheckIcon /> : <LinkGlyph />}
      {copied ? 'Link copied' : 'Share'}
    </button>
  );
}

function LinkGlyph() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}
