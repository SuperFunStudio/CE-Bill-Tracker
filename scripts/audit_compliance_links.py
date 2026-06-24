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
from app.links.health import classify, normalize, playwright_recheck


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
