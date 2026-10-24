'use client';

import Link from 'next/link';
import { useBills } from '@/hooks/useBills';
import { ButterflyExplorer } from './ButterflyExplorer';

/**
 * The methodology page's opening figure: the whole tracked corpus on the circular-economy butterfly,
 * zoomable into the bills behind each step. It answers "what counts as a circular economy law?" by
 * showing where the law we track sits, and where it doesn't (hatched steps). Every bill, every status,
 * every region; the country view and the two-country comparison live on Insights.
 *
 * Reads the same snapshot-backed bill list as the page's headline counts, so the figure and the
 * numbers above it can't disagree.
 */
export function MethodologyButterfly() {
  const { data: bills } = useBills({ ce_relevant: true, limit: 5000, regions: 'all' });

  return (
    // Breaks out of the 3xl text column on wide screens: at 768px the full diagram's labels would
    // render around 7px.
    <figure className="space-y-3 rounded-lg border border-border-default bg-bg-secondary p-4 sm:p-5 lg:-mx-24 xl:-mx-40">
      <ButterflyExplorer bills={bills ?? null} haloColor="var(--bg-secondary)" />
      <figcaption className="text-xs text-text-muted leading-relaxed">
        {bills?.length ? `All ${bills.length.toLocaleString()} tracked laws and bills` : 'Every tracked law and bill'} on the{' '}
        <a href="https://www.ellenmacarthurfoundation.org/circular-economy-diagram" target="_blank" rel="noopener noreferrer"
          className="text-green-accent hover:underline">Ellen MacArthur Foundation butterfly</a>: the technical cycle on the
        right, the biological on the left, meeting at the user. Each step counts the bills whose instrument, materials or
        extracted provisions place them there; a bill can sit at several steps. Darker means more law. Hatched marks a gap:
        we found no law for that step. See how any country fills it in, or compare two, on{' '}
        <Link href="/insights/" className="text-green-accent hover:underline">Insights</Link>.
      </figcaption>
    </figure>
  );
}
