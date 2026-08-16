import { scaleComparison } from '@/lib/outcomeScale';
import { ATTRIBUTION_NOTE, outcomeMetricText } from '@/lib/outcomeMetric';
import { formatDate } from '@/lib/utils';
import type { BillOutcome } from '@/lib/types';

/**
 * "What this law has produced" — the documented, cited outcome of an enacted law, on that law's own
 * page, above everything the law REQUIRES.
 *
 * It exists because of where the traffic comes from. The homepage ticker's share links land here
 * (#impact), and the thing the reader tapped was the figure — "$16 million/year", "100 million
 * containers returned". Before this block the page they arrived at never mentioned it: identity,
 * metadata, obligations, statute text. The share made a promise the destination didn't keep.
 *
 * So it leads. It sits above "What you must do" because a reader who arrived from a figure is not
 * yet asking what they must do — and a reader who came for obligations loses four lines to a result
 * that is, on this site, the whole argument for reading the obligations at all.
 *
 * ATTRIBUTION IS NOT OPTIONAL HERE. "direct" and "program" are different claims, and a figure printed
 * large next to a statute reads as caused-by-the-statute unless it says otherwise. Same note strings
 * as the Insights table, from lib/outcomeMetric, so the caveat can't drift between surfaces.
 *
 * Server-rendered — it's in the HTML for crawlers, which is most of the point of these pages.
 */
export function BillImpact({ outcomes }: { outcomes: BillOutcome[] }) {
  const rows = outcomes.filter(o => outcomeMetricText(o) || o.summary);
  if (!rows.length) return null;

  return (
    <section
      id="impact"
      // scroll-mt: the anchor lands the shared link here, and without the offset the heading sits
      // flush against the top edge of the viewport.
      className="scroll-mt-4 rounded-lg border border-green-accent/40 bg-green-dark/20 p-4 space-y-4"
      aria-labelledby="impact-heading"
    >
      <h2 id="impact-heading" className="font-serif text-base text-text-primary">
        What this law has produced
      </h2>
      {rows.map(o => (
        <OutcomeFigure key={o.id} outcome={o} />
      ))}
    </section>
  );
}

function OutcomeFigure({ outcome: o }: { outcome: BillOutcome }) {
  const metric = outcomeMetricText(o);
  // The same unit arithmetic the ticker shows, for the same reason: "320 megalitres" is not a
  // quantity anyone pictures. Returns null for money and bare rates — see lib/outcomeScale.
  const scale = scaleComparison(o.metric_value, o.metric_unit);
  const note = o.attribution ? ATTRIBUTION_NOTE[o.attribution] : null;

  return (
    <div className="space-y-1.5">
      {metric && (
        <p className="font-serif text-2xl leading-tight text-green-accent tabular-nums sm:text-3xl">
          {metric}
        </p>
      )}
      {o.metric_label && (
        <p className="text-sm leading-snug text-text-secondary">{o.metric_label}</p>
      )}
      {scale && (
        <p className="text-xs leading-snug text-text-primary/80" title={scale.basis}>
          <span className="text-text-muted">That&apos;s </span>
          <span className="border-b border-dotted border-text-muted/50">{scale.text}</span>
        </p>
      )}
      {/* The full summary, which the ticker deliberately withholds — this is the page where a reader
          who wants to check the figure has arrived, so the caveats travel with it. */}
      <p className="pt-1 text-body leading-relaxed text-text-secondary">{o.summary}</p>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5 text-xs text-text-muted">
        {note && <span title="How tightly the figure ties to the statute">{note}</span>}
        {o.as_of_date && <span>As of {formatDate(o.as_of_date)}</span>}
        {o.source_url && (
          <a
            href={o.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-accent hover:underline"
          >
            Source{o.source_name ? `: ${o.source_name}` : ''} ↗
          </a>
        )}
      </p>
    </div>
  );
}
