// Marketing attribution capture. On landing we read UTM params (?utm_source=linkedin&utm_campaign=…)
// and the external referrer, and stash them in localStorage so a conversion that happens later in the
// session (sign_up, request_access) can be credited to the campaign that brought the visitor.
//
// Semantics: LAST-campaign-touch. A URL carrying any utm_* param overwrites the stored value — so the
// most recent post/ad a visitor clicked gets the credit, which is what "which LinkedIn post drove this
// demo?" needs. A bare navigation (no utm_*) never wipes an existing value; if there's nothing stored
// yet and the visit came from an external site, we keep the referrer as a weak fallback signal.
//
// PII rule (see lib/analytics): utm_* values are marketing tags, safe for GA. The referrer/landing_page
// go to our own backend lead email only, never to GA.

const ATTR_KEY = 'atlas_attr_v1';
const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'] as const;
type UtmKey = (typeof UTM_KEYS)[number];

export type Attribution = Partial<Record<UtmKey, string>> & {
  referrer?: string;
  landing_page?: string;
  captured_at?: string;
};

/** Read + persist attribution from the current URL. Call once on first landing. Safe on the server. */
export function captureAttribution(): void {
  if (typeof window === 'undefined') return;
  try {
    const params = new URLSearchParams(window.location.search);
    const attr: Attribution = {};
    let hasUtm = false;
    for (const k of UTM_KEYS) {
      const v = params.get(k);
      if (v) {
        attr[k] = v.trim().slice(0, 200);
        hasUtm = true;
      }
    }

    if (hasUtm) {
      // A fresh campaign click — record it (last-touch overwrite) with context.
      attr.landing_page = window.location.pathname;
      const ref = document.referrer;
      if (ref && !ref.includes(window.location.host)) attr.referrer = ref.slice(0, 300);
      attr.captured_at = new Date().toISOString();
      localStorage.setItem(ATTR_KEY, JSON.stringify(attr));
      return;
    }

    // No utm_* on this URL. Don't clobber an existing value; but if nothing's stored and the visit came
    // from an external site, keep the referrer as a fallback ("came from linkedin.com" even untagged).
    if (localStorage.getItem(ATTR_KEY)) return;
    const ref = document.referrer;
    if (ref && !ref.includes(window.location.host)) {
      localStorage.setItem(
        ATTR_KEY,
        JSON.stringify({
          referrer: ref.slice(0, 300),
          landing_page: window.location.pathname,
          captured_at: new Date().toISOString(),
        } satisfies Attribution),
      );
    }
  } catch {
    /* private mode / storage disabled — attribution just won't persist */
  }
}

/** The full stored attribution (utm + referrer + landing). For our own backend, not GA. */
export function getAttribution(): Attribution {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(ATTR_KEY);
    return raw ? (JSON.parse(raw) as Attribution) : {};
  } catch {
    return {};
  }
}

/** GA-safe subset (utm_* enums only) to spread into a track() call. Omits keys that aren't set. */
export function attributionParams(): Partial<Record<UtmKey, string>> {
  const a = getAttribution();
  const out: Partial<Record<UtmKey, string>> = {};
  for (const k of UTM_KEYS) {
    if (a[k]) out[k] = a[k];
  }
  return out;
}
