"""Shared link-health classification — the single source of truth for "is this URL healthy?".

Both auditors use this:
  - scripts/audit_compliance_links.py  — the "how to comply" links (entity/pathway URLs)
  - scripts/audit_bill_source_links.py — the per-bill "View Source" links (bills.source_url)

Every distinct URL is PINGED once (no crawl) and sorted into four buckets:

  alive       2xx, lands where expected
  redirected  3xx to a different host/path  -> often a rebrand/move; capture the new URL to relink
  dead        404/410, DNS failure, refused -> the only bucket that means "the link is broken"
  blocked     403/429/503, WAF challenge, timeout, TLS-trust error -> we could NOT verify; never
              auto-treated as dead. Relinking on these would replace good links with worse ones.

The blocked bucket is deliberate: a government WAF throwing 403/timeout at a bot is a *verification
failure*, not a broken link. Surface it for a human, and optionally retry through a real browser
engine (playwright_recheck), which clears most WAFs.
"""
from __future__ import annotations

from typing import NamedTuple

import httpx

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

# Buckets, ordered most-actionable first (used by report sorting and the migration's allowed values).
BUCKETS = ("dead", "redirected", "blocked", "alive")


class LinkResult(NamedTuple):
    bucket: str
    status: int | None
    final_url: str | None
    note: str


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


def _exception_verdict(e: httpx.HTTPError) -> LinkResult:
    """Map an httpx request failure to a bucket. Only DNS/refused is 'dead'; everything ambiguous
    (timeout, TLS-trust, odd transport error) is 'blocked' — we never call a link dead unless we
    actually proved it gone."""
    if isinstance(e, httpx.ConnectError):
        msg = str(e)
        # A client-side TLS trust failure (local CA bundle missing an intermediate) is NOT a dead
        # site — only DNS/refused is. Don't relink on an SSL verify error.
        if "ssl" in msg.lower() or "certificate" in msg.lower():
            return LinkResult("blocked", None, None, f"TLS verify failed (client trust store): {msg[:60]}")
        return LinkResult("dead", None, None, f"connect error: {msg[:80]}")
    if isinstance(e, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout)):
        # Slow/hung is ambiguous — never call it dead.
        return LinkResult("blocked", None, None, "timeout")
    return LinkResult("blocked", None, None, f"{type(e).__name__}: {str(e)[:80]}")


def _response_verdict(url: str, r: httpx.Response) -> LinkResult:
    """Bucket a completed response. Shared by the sync and async classifiers — the body is fully
    read for both (non-streaming GET), so r.text/r.url are available synchronously here."""
    code = r.status_code
    final = str(r.url)
    body_head = (r.text[:4000] if r.headers.get("content-type", "").startswith("text") else "").lower()

    if code in (404, 410):
        return LinkResult("dead", code, final, "not found")
    if code in (401, 403, 429, 451, 503) or code in (500, 502, 504):
        return LinkResult("blocked", code, final, "server refused / unavailable")
    if 200 <= code < 300:
        if any(m in body_head for m in CHALLENGE_MARKERS):
            return LinkResult("blocked", code, final, "WAF challenge body")
        if normalize(final) != normalize(url):
            return LinkResult("redirected", code, final, "redirected to a different location")
        return LinkResult("alive", code, final, "ok")
    # Anything else (3xx that didn't resolve, odd 4xx) -> inconclusive, not dead.
    return LinkResult("blocked", code, final, "unexpected status")


def classify(url: str, client: httpx.Client) -> LinkResult:
    """Classify one URL via a single httpx GET. Never raises — failures map to a bucket."""
    try:
        r = client.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=15.0)
    except httpx.HTTPError as e:
        return _exception_verdict(e)
    return _response_verdict(url, r)


async def classify_async(url: str, client: httpx.AsyncClient) -> LinkResult:
    """Async twin of classify(), for the scheduler job (which runs in the asyncpg event loop)."""
    try:
        r = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=15.0)
    except httpx.HTTPError as e:
        return _exception_verdict(e)
    return _response_verdict(url, r)


def playwright_recheck(urls: list[str]) -> dict[str, LinkResult]:
    """Retry blocked URLs through a real Chromium engine, which clears most WAFs.
    Returns {url: LinkResult}; empty if Playwright isn't installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n[playwright] not installed — skipping browser fallback.")
        print("            enable with:  venv/Scripts/pip install playwright && "
              "venv/Scripts/playwright install chromium")
        return {}

    out: dict[str, LinkResult] = {}
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
                    out[url] = LinkResult("dead", code, final, "not found (browser)")
                elif code and code >= 400:
                    out[url] = LinkResult("blocked", code, final, "still blocked (browser)")
                elif any(m in body[:4000] for m in CHALLENGE_MARKERS):
                    out[url] = LinkResult("blocked", code, final, "WAF challenge (browser)")
                elif normalize(final) != normalize(url):
                    out[url] = LinkResult("redirected", code, final, "redirected (browser)")
                else:
                    out[url] = LinkResult("alive", code, final, "ok (browser)")
            except Exception as e:  # noqa: BLE001 — a browser nav failure is just inconclusive
                out[url] = LinkResult("blocked", None, None, f"browser error: {str(e)[:60]}")
        browser.close()
    return out
