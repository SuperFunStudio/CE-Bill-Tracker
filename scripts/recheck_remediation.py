"""Re-check whether negative/mixed law outcomes have since been REMEDIATED by a later law.

The hard part of "did anyone fix this?" is knowing where to look — you can't research all ~960 laws.
But remediation only matters for outcomes that went WRONG, and we already classify every outcome's
direction. So the negative/mixed flag IS the trigger: this job scans ONLY rows with
direction in ('negative','mixed'), and only those never checked or gone stale (remediation_checked_at
older than --stale-days). That keeps the work bounded to a dozen rows, runnable on a slow cadence for
pennies — e.g. monthly from the scheduler — instead of an impossible full-corpus sweep.

For each, it asks Claude (web_search/web_fetch) whether a later amendment/follow-on/replacement has
addressed the problem, names that law, and (best-effort) links it to a tracked bills row so the UI can
render "→ Fixed by SB 1053". It writes the remediation_* columns and stamps remediation_checked_at; it
never touches the core figure or the reviewed flag. Surfaced for the admin to confirm in /admin.

Usage:
  venv/Scripts/python scripts/recheck_remediation.py --dry-run          # list what's due, no API
  venv/Scripts/python scripts/recheck_remediation.py --preview          # research, print, no write
  venv/Scripts/python scripts/recheck_remediation.py                    # research + write remediation
  venv/Scripts/python scripts/recheck_remediation.py --stale-days 30    # also re-check rows checked >30d ago
  venv/Scripts/python scripts/recheck_remediation.py --prod-dsn "..."
"""
import argparse
import sys

import anthropic
from sqlalchemy import create_engine, text

from app.config import settings
from scripts.propose_bill_outcomes import MODEL, research_one, resolve_bill_id

RECHECK_SCHEMA = """Return ONLY a JSON object (no prose, no code fence):
{
  "remediated": true | false,
  "remediation_note": "<one sentence naming the later law (and year) that fixed/addressed the problem, or null>",
  "remediation_bill_number": "<that law's bill number if identifiable, e.g. 'SB1053', else null>",
  "confidence": <0.0-1.0>
}
remediated=true ONLY if you can identify a SPECIFIC later statute (amendment, follow-on, or replacement)
that addresses the documented problem below. A vague "the state is considering changes" is remediated=false.
Prefer the actual enacted fix; name its bill number and year if you can find them."""


def due_rows(engine, stale_days, limit):
    """Negative/mixed outcomes that have never been remediation-checked, or whose check is stale."""
    sql = text("""
        select id, state, bill_number, law_title, direction, summary,
               metric_display, metric_value, metric_unit, metric_label
        from bill_outcome
        where direction in ('negative','mixed')
          and (remediation_checked_at is null
               or (:stale_days is not null
                   and remediation_checked_at < now() - make_interval(days => :stale_days)))
        order by remediation_checked_at asc nulls first, id
        limit :limit
    """)
    with engine.connect() as c:
        return list(c.execute(sql, {"stale_days": stale_days, "limit": limit}))


def build_prompt(r):
    fig = r.metric_display or (
        f"{r.metric_value} {r.metric_unit or ''}".strip() if r.metric_value is not None else "")
    return (
        "A documented real-world outcome of an enacted U.S. circular-economy / EPR law was "
        f"{r.direction.upper()} — a problem or shortfall. Determine whether a LATER law has since "
        "fixed or materially addressed it.\n\n"
        f"State: {r.state}\nLaw: {r.bill_number} — {r.law_title}\n"
        f"The problem (recorded outcome): {fig} {r.metric_label or ''}\n{r.summary}\n\n"
        "Search the web for a later amendment, follow-on, or replacement law in the SAME state that "
        "addresses this. (E.g. California's SB 270 bag-ban loophole was closed by a 2024 follow-on law.)\n\n"
        + RECHECK_SCHEMA
    )


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    ap = argparse.ArgumentParser()
    ap.add_argument("--prod-dsn", default=None)
    ap.add_argument("--stale-days", type=int, default=None,
                    help="also re-check rows whose last check is older than this (default: only "
                         "never-checked rows)")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--min-confidence", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true", help="list due rows, no API calls")
    ap.add_argument("--preview", action="store_true", help="research + print, do not write")
    args = ap.parse_args()

    engine = create_engine(args.prod_dsn or settings.database_url)
    rows = due_rows(engine, args.stale_days, args.limit)
    print(f"Negative/mixed outcomes due for a remediation check: {len(rows)}"
          f"{' (PROD)' if args.prod_dsn else ''}\n")
    for r in rows:
        print(f"  [{r.direction:>8}] {r.state} {r.bill_number or '?':16} {(r.law_title or '')[:54]}")
    if args.dry_run:
        print("\n--dry-run: no API calls made.")
        return
    if not rows:
        return
    if not settings.anthropic_api_key:
        sys.exit("\nERROR: anthropic_api_key not set. Use --dry-run to scope work without the API.")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=600.0, max_retries=4)
    web_tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    found, checked = 0, 0
    for i, r in enumerate(rows, 1):
        print(f"\n[{i}/{len(rows)}] {r.state} {r.bill_number} — checking for a fix...")
        try:
            res = research_one(client, build_prompt(r), args.model, web_tools, max_tokens=2500)
        except anthropic.BadRequestError as e:
            sys.exit(f"\nAPI rejected the request (web tools may not be enabled on this key): {e.message}")
        except (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.APIStatusError) as e:
            print(f"    -> API error, skipping: {type(e).__name__}")
            continue

        checked += 1
        remediated = bool(res.get("remediated")) and (res.get("confidence") or 0) >= args.min_confidence
        note = (res.get("remediation_note") or "").strip() or None
        rem_bn = (res.get("remediation_bill_number") or "").strip() or None
        if not remediated or not note:
            print(f"    -> no remediation found (conf={res.get('confidence')})")
            note, rem_bn = None, None
        else:
            print(f"    [FIX] {note}  [{rem_bn or 'bill # unknown'}]  conf={res.get('confidence')}")

        rem_bill_id = resolve_bill_id(engine, r.state, rem_bn) if rem_bn else None
        if rem_bill_id:
            print(f"          linked to tracked bill_id={rem_bill_id}")
        if args.preview:
            continue
        # Always stamp checked_at (so a "no fix yet" answer isn't re-checked until it goes stale);
        # write the remediation fields only when found. Never touches the figure or reviewed flag.
        with engine.begin() as c:
            c.execute(text("""
                update bill_outcome set
                  remediation_note = :note,
                  remediation_bill_number = :rem_bn,
                  remediated_by_bill_id = :rem_bill_id,
                  remediation_checked_at = now()
                where id = :id
            """), {"id": r.id, "note": note, "rem_bn": rem_bn, "rem_bill_id": rem_bill_id})
        if note:
            found += 1

    print("\n" + "=" * 64)
    verb = "would write" if args.preview else "wrote"
    print(f"Checked {checked} of {len(rows)}; {verb} {found} remediation(s).")
    if found and not args.preview:
        print("Confirm/correct them in /admin (Outcomes) — they show on negative cards as '→ Fixed by …'.")
    print("=" * 64)


if __name__ == "__main__":
    main()
