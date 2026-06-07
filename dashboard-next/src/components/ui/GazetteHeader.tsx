import type { ReactNode } from 'react';

/**
 * Shared "Gazette" masthead-style page header — centered serif title between
 * newspaper rules with an italic tagline. Mirrors the home/State Standings look
 * so every page reads as part of the same publication.
 */
export function GazetteHeader({ title, subtitle }: { title: ReactNode; subtitle?: string }) {
  return (
    <header className="text-center pt-1 pb-4 border-b-2 border-text-primary/80">
      <div className="border-t border-b border-text-primary/30 py-3">
        <h1 className="font-serif uppercase tracking-[0.06em] text-2xl sm:text-3xl text-text-primary">
          {title}
        </h1>
      </div>
      {subtitle && (
        <p className="mt-2 font-serif italic text-text-secondary text-sm">{subtitle}</p>
      )}
    </header>
  );
}
