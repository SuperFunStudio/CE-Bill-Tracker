"""Audit every bill's "View Source" link (bills.source_url) and persist the verdict.

The source link on a bill points at a state-legislature page that rots or flakes — it moves, 404s,
or throws an intermittent WAF/timeout. That's the random "connection error" a user hits clicking
"View Source". This script PINGS each distinct source_url once (it does not crawl), classifies it
with the shared link-health logic (app/links/health.py), and writes the verdict back onto each bill:

  source_url_status      alive | redirected | dead | blocked   (NULL = never checked)
  source_url_final       resolved URL when redirected (so the UI can link to where it moved)
  source_url_checked_at  when this row was last checked

The frontend then degrades gracefully: redirected -> link to the resolved URL; dead -> offer a
LegiScan backup; blocked/alive/unchecked -> link as normal (blocked is "could not verify", NOT
broken — we never downgrade a link we haven't proven dead).

Usage:
  venv/Scripts/python scripts/audit_bill_source_links.py                  # check all, write back
  venv/Scripts/python scripts/audit_bill_source_links.py --dry-run        # report only, no DB writes
  venv/Scripts/python scripts/audit_bill_source_links.py --only-unchecked # skip rows already checked
  venv/Scripts/python scripts/audit_bill_source_links.py --playwright     # browser retry on blocked
  venv/Scripts/python scripts/audit_bill_source_links.py --prod-dsn "..." --limit 200
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402
from app.links.health import classify, normalize, playwright_recheck  # noqa: E402


def collect_bills(engine, only_unchecked: bool, limit: int | None):
    """source_url -> list of (bill_id, label) sharing it. One ping fixes every bill on that URL."""
    where = "source_url is not null and source_url <> ''"
    if only_unchecked:
        where += " and source_url_status is null"
    sql = (f"select id, state, bill_number, source_url from bills "
           f"where {where} order by id")
    if limit:
        sql += f" limit {int(limit)}"

    by_url: dict[str, list] = {}
    with engine.connect() as c:
        for bid, state, bn, url in c.execute(text(sql)):
            label = f"{state} {bn}".strip() or f"bill {bid}"
            by_url.setdefault(url.strip(), []).append((bid, label))
    return by_url


def persist(engine, results: dict, checked_at: datetime):
    """Write status/final/checked_at onto every bill sharing each audited URL."""
    upd = text(
        "update bills set source_url_status = :status, source_url_final = :final, "
        "source_url_checked_at = :ts where id = :id"
    )
    with engine.begin() as c:
        for url, r in results.items():
            # Only store a distinct final_url for a real redirect; otherwise keep it NULL.
            final = r["final_url"] if (
                r["bucket"] == "redirected" and r["final_url"]
                and normalize(r["final_url"]) != normalize(url)
            ) else None
            for bid, _label in r["bills"]:
                c.execute(upd, {"status": r["bucket"], "final": final,
                                "ts": checked_at, "id": bid})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod-dsn", default=None)
    ap.add_argument("--dry-run", action="store_true", help="report only; do not write to the DB")
    ap.add_argument("--only-unchecked", action="store_true",
                    help="skip bills whose source_url_status is already set")
    ap.add_argument("--playwright", action="store_true",
                    help="retry blocked URLs through a headless browser")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (politeness)")
    ap.add_argument("--limit", type=int, default=None, help="cap how many distinct URLs to check")
    args = ap.parse_args()

    engine = create_engine(args.prod_dsn or settings.database_url)
    by_url = collect_bills(engine, args.only_unchecked, args.limit)
    n_bills = sum(len(v) for v in by_url.values())
    print(f"Auditing {len(by_url)} distinct source link(s) across {n_bills} bill(s)"
          f"{' on PROD' if args.prod_dsn else ''}"
          f"{' [dry-run]' if args.dry_run else ''}...\n")

    # Persist in batches as we go (not one big write at the end): a long run against flaky state
    # sites shouldn't lose everything to a crash near the finish, and it gives live progress.
    FLUSH_EVERY = 100
    checked_at = datetime.now(timezone.utc)
    results = {}  # url -> dict(bucket,status,final_url,note,bills) — kept whole for the report
    pending: dict = {}  # not-yet-persisted slice
    with httpx.Client() as client:
        for i, url in enumerate(sorted(by_url), 1):
            res = classify(url, client)
            rec = dict(bucket=res.bucket, status=res.status, final_url=res.final_url,
                       note=res.note, bills=by_url[url])
            results[url] = rec
            pending[url] = rec
            print(f"  [{i:>4}/{len(by_url)}] {res.bucket:<10} {res.status if res.status else '   '}  {url}",
                  flush=True)
            if not args.dry_run and len(pending) >= FLUSH_EVERY:
                persist(engine, pending, checked_at)
                print(f"       … persisted {i}/{len(by_url)}", flush=True)
                pending = {}
            time.sleep(args.delay)

    if not args.dry_run and pending:
        persist(engine, pending, checked_at)
        pending = {}

    if args.playwright:
        blocked = [u for u, r in results.items() if r["bucket"] == "blocked"]
        updated: dict = {}
        for url, res in playwright_recheck(blocked).items():
            results[url].update(bucket=res.bucket, status=res.status,
                                final_url=res.final_url, note=res.note)
            updated[url] = results[url]
        if not args.dry_run and updated:
            persist(engine, updated, checked_at)

    # --- Report, most-actionable buckets first. ---
    order = ["dead", "redirected", "blocked", "alive"]
    by_bucket: dict[str, list] = {b: [] for b in order}
    for url, r in results.items():
        by_bucket[r["bucket"]].append((url, r))

    print("\n" + "=" * 72)
    print("SUMMARY")
    for b in order:
        n_urls = len(by_bucket[b])
        n_b = sum(len(r["bills"]) for _u, r in by_bucket[b])
        print(f"  {n_urls:>4} url  {n_b:>4} bills  {b}")
    print("=" * 72)

    headline = {
        "dead": "DEAD — link target is gone; UI will offer a LegiScan backup",
        "redirected": "REDIRECTED — page moved; UI will link to the resolved URL",
        "blocked": "BLOCKED / INCONCLUSIVE — could not verify; left as-is"
                   + ("" if args.playwright else " (try --playwright)"),
    }
    for b in ("dead", "redirected", "blocked"):
        items = sorted(by_bucket[b], key=lambda x: x[0])
        if not items:
            continue
        print(f"\n### {headline[b]}  ({len(items)} url)")
        for url, r in items:
            print(f"\n  {url}")
            if r["final_url"] and normalize(r["final_url"]) != normalize(url):
                print(f"    -> {r['final_url']}")
            print(f"    [{r['status'] if r['status'] else '-'}] {r['note']}")
            print(f"       on: {', '.join(label for _id, label in r['bills'][:8])}"
                  + (" …" if len(r["bills"]) > 8 else ""))

    if args.dry_run:
        print("\n[dry-run] no DB writes.")
    else:
        print(f"\nWrote health verdict to {n_bills} bill(s).")


if __name__ == "__main__":
    main()
