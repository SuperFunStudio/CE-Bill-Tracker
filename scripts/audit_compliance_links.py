"""Audit every "how to comply" link for rot, rebrands, and dead ends.

The state-page action layer (see app/api/compliance.py + scripts/build_compliance_pathways.py)
sends producers to a curated set of URLs: each compliance_entity's homepage / registration_url
and each compliance_pathway's snapshotted registration_url. Those rot — orgs rebrand
(Call2Recycle -> Battery Network), agencies reorganize, program pages move.

This script PINGS each distinct URL once (it does not crawl) and sorts it into four buckets:

  alive       2xx, lands where expected
  redirected  3xx to a different host/path  -> often a rebrand; capture the new URL to relink
  dead        404/410, DNS failure, refused -> the only bucket that means "fix the link"
  blocked     403/429/503 or a WAF challenge -> we could NOT verify; NEVER auto-treated as dead

The blocked bucket is the whole point of the design: a government WAF throwing 403 at a bot is a
verification failure, not a broken link. Relinking on those would replace good links with worse
ones. We surface them for a human, and optionally retry them through a real browser engine
(--playwright) which clears most WAFs. Anything still blocked stays "inconclusive, check manually".

Usage:
  venv/Scripts/python scripts/audit_compliance_links.py                 # httpx pass, print report
  venv/Scripts/python scripts/audit_compliance_links.py --playwright    # + browser retry on blocked
  venv/Scripts/python scripts/audit_compliance_links.py --prod-dsn "..."
  venv/Scripts/python scripts/audit_compliance_links.py --json out.json
"""
import argparse
import json
import time

import httpx
from sqlalchemy import create_engine, text

from app.config import settings

# A real Chrome UA + headers clear most state-.gov user-agent filters without a browser engine.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
}

# Body markers that mean "a WAF/anti-bot interstitial answered", not the real page — even on 200.
CHALLENGE_MARKERS = (
    "just a moment",            # Cloudflare
    "attention required",       # Cloudflare block
    "cf-browser-verification",
    "checking your browser",
    "incapsula incident",       # Imperva/Incapsula
    "request unsuccessful",     # Incapsula
    "pardon our interruption",  # PerimeterX
    "access denied",
    "you have been blocked",
)


def normalize(url: str) -> str:
    """Host+path, scheme-insensitive, trailing slash stripped — to tell a real redirect
    (rebrand / moved page) from a cosmetic http->https or '/' normalization."""
    u = (url or "").strip().lower()
    for pre in ("https://", "http://"):
        if u.startswith(pre):
            u = u[len(pre):]
            break
    if u.startswith("www."):
        u = u[4:]
    return u.split("#")[0].rstrip("/")


def collect_urls(engine):
    """url -> sorted list of referrer labels, so a dead/redirected link is actionable."""
    refs: dict[str, set] = {}

    def add(url, label):
        if url and url.strip():
            refs.setdefault(url.strip(), set()).add(label)

    with engine.connect() as c:
        for slug, name, url, reg in c.execute(text(
                "select slug, name, url, registration_url from compliance_entity")):
            add(url, f"entity:{slug} (url)")
            add(reg, f"entity:{slug} (registration_url)")
        for state, bn, reg in c.execute(text(
                "select b.state, b.bill_number, p.registration_url "
                "from compliance_pathway p join bills b on b.id = p.bill_id")):
            add(reg, f"pathway:{state} {bn}")
    return {u: sorted(v) for u, v in refs.items()}


def classify(url, client):
    """Return (bucket, status, final_url, note) for one URL via a single httpx GET."""
    try:
        r = client.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=15.0)
    except httpx.ConnectError as e:
        msg = str(e)
        # A client-side TLS trust failure (local CA bundle missing an intermediate) is NOT a dead
        # site — only DNS/refused is. Don't relink on an SSL verify error.
        if "ssl" in msg.lower() or "certificate" in msg.lower():
            return "blocked", None, None, f"TLS verify failed (client trust store): {msg[:60]}"
        return "dead", None, None, f"connect error: {msg[:80]}"
    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout):
        # Slow/hung is ambiguous — never call it dead.
        return "blocked", None, None, "timeout"
    except httpx.HTTPError as e:
        return "blocked", None, None, f"{type(e).__name__}: {str(e)[:80]}"

    code = r.status_code
    final = str(r.url)
    body_head = (r.text[:4000] if r.headers.get("content-type", "").startswith("text") else "").lower()

    if code in (404, 410):
        return "dead", code, final, "not found"
    if code in (401, 403, 429, 451, 503) or code in (500, 502, 504):
        return "blocked", code, final, "server refused / unavailable"
    if 200 <= code < 300:
        if any(m in body_head for m in CHALLENGE_MARKERS):
            return "blocked", code, final, "WAF challenge body"
        if normalize(final) != normalize(url):
            return "redirected", code, final, "redirected to a different location"
        return "alive", code, final, "ok"
    # Anything else (3xx that didn't resolve, odd 4xx) -> inconclusive, not dead.
    return "blocked", code, final, "unexpected status"


def playwright_recheck(urls):
    """Retry blocked URLs through a real Chromium engine, which clears most WAFs.
    Returns {url: (bucket, status, final_url, note)}; empty if Playwright isn't installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n[playwright] not installed — skipping browser fallback.")
        print("            enable with:  venv/Scripts/pip install playwright && "
              "venv/Scripts/playwright install chromium")
        return {}

    out = {}
    print(f"\n[playwright] re-checking {len(urls)} blocked URL(s) in a real browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=BROWSER_HEADERS["User-Agent"])
        page = ctx.new_page()
        for url in urls:
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=25000)
                code = resp.status if resp else None
                final = page.url
                body = (page.content() or "").lower()
                if code in (404, 410):
                    out[url] = ("dead", code, final, "not found (browser)")
                elif code and code >= 400:
                    out[url] = ("blocked", code, final, "still blocked (browser)")
                elif any(m in body[:4000] for m in CHALLENGE_MARKERS):
                    out[url] = ("blocked", code, final, "WAF challenge (browser)")
                elif normalize(final) != normalize(url):
                    out[url] = ("redirected", code, final, "redirected (browser)")
                else:
                    out[url] = ("alive", code, final, "ok (browser)")
            except Exception as e:  # noqa: BLE001 — a browser nav failure is just inconclusive
                out[url] = ("blocked", None, None, f"browser error: {str(e)[:60]}")
        browser.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod-dsn", default=None)
    ap.add_argument("--playwright", action="store_true",
                    help="retry blocked URLs through a headless browser")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (politeness)")
    ap.add_argument("--json", default=None, help="also write full results to this path")
    args = ap.parse_args()

    engine = create_engine(args.prod_dsn or settings.database_url)
    url_refs = collect_urls(engine)
    print(f"Auditing {len(url_refs)} distinct compliance link(s)"
          f"{' on PROD' if args.prod_dsn else ''}...\n")

    results = {}  # url -> dict
    with httpx.Client() as client:
        for i, url in enumerate(sorted(url_refs), 1):
            bucket, code, final, note = classify(url, client)
            results[url] = dict(bucket=bucket, status=code, final_url=final,
                                note=note, referrers=url_refs[url])
            print(f"  [{i:>3}/{len(url_refs)}] {bucket:<10} {code if code else '   '}  {url}")
            time.sleep(args.delay)

    if args.playwright:
        blocked = [u for u, r in results.items() if r["bucket"] == "blocked"]
        for url, (bucket, code, final, note) in playwright_recheck(blocked).items():
            results[url].update(bucket=bucket, status=code, final_url=final, note=note)

    # --- Report, grouped by bucket; the actionable buckets first. ---
    order = ["dead", "redirected", "blocked", "alive"]
    by_bucket: dict[str, list] = {b: [] for b in order}
    for url, r in results.items():
        by_bucket[r["bucket"]].append((url, r))

    print("\n" + "=" * 72)
    print("SUMMARY")
    for b in order:
        print(f"  {len(by_bucket[b]):>3}  {b}")
    print("=" * 72)

    headline = {
        "dead": "DEAD — relink these (the link target is gone)",
        "redirected": "REDIRECTED — likely rebrand/move; update to the new URL",
        "blocked": "BLOCKED / INCONCLUSIVE — could not verify; check manually"
                   + ("" if args.playwright else " (try --playwright)"),
    }
    for b in ("dead", "redirected", "blocked"):
        items = sorted(by_bucket[b], key=lambda x: x[0])
        if not items:
            continue
        print(f"\n### {headline[b]}  ({len(items)})")
        for url, r in items:
            print(f"\n  {url}")
            if r["final_url"] and normalize(r["final_url"]) != normalize(url):
                print(f"    -> {r['final_url']}")
            print(f"    [{r['status'] if r['status'] else '-'}] {r['note']}")
            for ref in r["referrers"]:
                print(f"       referenced by {ref}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nFull results written to {args.json}")


if __name__ == "__main__":
    main()
