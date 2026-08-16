/**
 * Formatting for a documented outcome's headline figure — one implementation, four surfaces (the
 * homepage ticker, the Insights impact table, the bill page's impact block, the farewell modal).
 *
 * It lived as four copies of the same six lines, which is how every one of them printed a money
 * figure back-to-front: `metric_unit` on a currency row is "$ million/year", and value-then-unit
 * renders that as "16 $ million/year". A currency belongs in FRONT of its number in every locale
 * this site serves, so the symbol is split off the unit and moved there.
 */

/** The fields a figure is built from — structural, so the admin console's edit shape fits too. */
export interface OutcomeFigure {
  metric_display?: string | null;
  metric_value?: number | null;
  metric_unit?: string | null;
}

/** Currency at the head of a unit string, as either a symbol ("$ million/year") or a code
 *  ("USD million"). Only the leading position is matched: "cents per litre" is not a currency unit,
 *  it's a rate, and it reads correctly as-is. */
const CURRENCY_PREFIX = /^\s*(\$|€|£|¥|USD|EUR|GBP|AUD|CAD|NZD|JPY)\s*/i;

const CURRENCY_SYMBOL: Record<string, string> = {
  usd: '$', aud: '$', cad: '$', nzd: '$', eur: '€', gbp: '£', jpy: '¥',
};

/**
 * The figure as it should read: "$16 million/year", "100 million containers", "76%".
 *
 * `metric_display` is a curated override and is returned verbatim — it exists precisely for figures
 * whose shape this function shouldn't be guessing at ("157k → 231k tons (+47%)"). Returns null when
 * the row carries no figure at all, which is the signal for a surface to skip the row entirely.
 */
export function outcomeMetricText(o: OutcomeFigure): string | null {
  if (o.metric_display) return o.metric_display;
  if (o.metric_value == null) return null;

  const value = o.metric_value.toLocaleString();
  const unit = o.metric_unit?.trim();
  if (!unit) return value;

  const match = unit.match(CURRENCY_PREFIX);
  if (match) {
    const symbol = CURRENCY_SYMBOL[match[1].toLowerCase()] ?? match[1];
    const rest = unit.slice(match[0].length).trim(); // "million/year"
    return rest ? `${symbol}${value} ${rest}` : `${symbol}${value}`;
  }
  // "%" binds to the number with no space — "76 %" is a typo everywhere but France. A cadence glued
  // on with a slash ("%/year") stays glued; anything else that follows is a phrase and takes a space.
  const percent = unit.match(/^\s*(?:%|percentage|percent)\s*/i);
  if (percent) {
    const rest = unit.slice(percent[0].length).trim();
    if (!rest) return `${value}%`;
    return rest.startsWith('/') ? `${value}%${rest}` : `${value}% ${rest}`;
  }
  return `${value} ${unit}`;
}

/** How tightly the figure ties to the statute. Spelled out wherever a figure is shown next to a law,
 *  because "the law caused this" and "a program the law funds reports this" are different claims. */
export const ATTRIBUTION_NOTE: Record<string, string> = {
  direct: 'Directly produced by the law',
  program: 'Produced by a program the law funds or incentivizes',
  associated: 'Associated with the law (correlation)',
};
