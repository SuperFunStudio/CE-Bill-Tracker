"""Query GA4 (property 529411970) via the Data API and print a report to the terminal.

GA4's own UI is slow to answer the questions we actually ask ("did anyone hit the pro gate
last week", "which events fired at all"), and its exploration reports can't be diffed or
committed. This pulls the same numbers over the Data API so they can be piped, grepped and
pasted into a doc.

Auth: a service account key JSON. The account (ga4-reader@ce-bill-tracker.iam.gserviceaccount.com)
must be added as a Viewer under GA4 Admin -> Property access management -- GCP IAM roles grant
nothing here, GA4 keeps its own access list. Key path defaults to ~/.gcp/ga4-reader.json and can
be overridden with --key or GA4_KEY_FILE.

Reports:
  events    event_name x eventCount/totalUsers      (default -- what fired, how much)
  pages     pageTitle/pagePath x screenPageViews
  funnel    the gate_shown -> gate_hit -> pricing_cta -> purchase conversion spine. The gate_hit
            step counts WALLS ONLY (outcome != 'allowed'); see GATE_HIT_WALLED_FILTER.
  raw       whatever you pass to --dimensions/--metrics

Usage:
  venv/Scripts/python scripts/ga4_report.py                            # events, last 28 days
  venv/Scripts/python scripts/ga4_report.py --days 7
  venv/Scripts/python scripts/ga4_report.py --report pages --limit 30
  venv/Scripts/python scripts/ga4_report.py --report funnel --days 90
  venv/Scripts/python scripts/ga4_report.py --report events --filter atlas_    # prefix match
  venv/Scripts/python scripts/ga4_report.py --report raw \
      --dimensions eventName,country --metrics eventCount --days 30
  venv/Scripts/python scripts/ga4_report.py --report raw --event gate_hit \
      --dimensions customEvent:gate,customEvent:outcome,customEvent:feature --metrics eventCount
  venv/Scripts/python scripts/ga4_report.py --start 2026-06-01 --end 2026-06-30
  venv/Scripts/python scripts/ga4_report.py --json                     # machine-readable
  venv/Scripts/python scripts/ga4_report.py --exclude-bots --days 7    # drop datacenter traffic
  venv/Scripts/python scripts/ga4_report.py --bots-only --days 7       # audit what that drops

Bot traffic: GA4's built-in known-bot list is UA-based and misses headless Chrome, which shows up here
as real sessions with ~0 engagement. --exclude-bots applies a read-time segment (see BOT_FILTER) rather
than a GA4 Data Filter, because data filters can only test debug_mode or IP-derived traffic_type -- not
screen resolution -- and an Active one would drop rows permanently and only going forward. Any rate you
quote (engagement, see-to-act, conversion) is wrong during a crawl unless you pass --exclude-bots.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

PROPERTY_ID = "529411970"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
API = "https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport"
DEFAULT_KEY = Path.home() / ".gcp" / "ga4-reader.json"

# The funnel spine. Each step is an event name; ordering is ours, not GA4's -- the Data API
# funnel endpoint needs a paid property, so we just pull counts per step and let the reader
# eyeball the dropoff.
FUNNEL_STEPS = [
    "page_view",
    "bill_open",
    "gate_shown",  # paywall IMPRESSION, every wall app-wide. The only passive step; the rest are clicks.
    "gate_hit",    # paywall INTENT -- someone acted at a gate. gate_shown->gate_hit is the see-to-act rate.
    "pricing_cta",
    "purchase",
]

# gate_hit does NOT mean "hit a wall". useProGate/useCapabilityGate also fire it with outcome='allowed'
# when an ENTITLED user sails through a gate (AuthContext.tsx) -- that's a feature-usage event, not a
# conversion step, and counting it here would inflate intent with people who were never walled. Harmless
# while there are no subscribers; wrong the moment there are. So the funnel re-queries gate_hit with
# 'allowed' filtered out server-side rather than summing a breakdown: totalUsers can't be added across
# rows (the same person appears under several outcomes), so only the API can dedupe it.
#
# NOT-filters keep `(not set)` rows, which is what we want -- gate_hit events that predate the Aug 2026
# registration of the `outcome` custom dimension have no value to test and are almost all real walls.
# GA4 dimensions are not retroactive, so those stay `(not set)` forever.
GATE_HIT_STEP = "gate_hit"
GATE_HIT_LABEL = "gate_hit (walled)"


def eq(field, value):
    """A FilterExpression matching one exact dimension value."""
    return {"filter": {"fieldName": field,
                       "stringFilter": {"matchType": "EXACT", "value": value}}}


def not_(expr):
    return {"notExpression": expr}


def and_(*exprs):
    """AND non-empty FilterExpressions together. Filters must COMPOSE, not overwrite -- the request
    carries a single `dimensionFilter`, so --event, the gate_hit walls-only rule and --exclude-bots
    would silently clobber each other if each just assigned it."""
    exprs = [e for e in exprs if e]
    if not exprs:
        return None
    if len(exprs) == 1:
        return exprs[0]
    return {"andGroup": {"expressions": exprs}}


GATE_HIT_WALLED_FILTER = and_(eq("eventName", GATE_HIT_STEP),
                              not_(eq("customEvent:outcome", "allowed")))

# --- The datacenter/bot segment -------------------------------------------------------------------
#
# Automated traffic that GA4's built-in known-bot exclusion does NOT catch (that list is UA-based and
# headless Chrome isn't on it). The discriminator is the viewport: 800x600 is headless Chrome's default
# window size, and almost nothing else lands there.
#
# Measured over 90 days before adopting it: ~294 sessions at 800x600 with 6 engaged (2%), against a
# site-wide engagement rate near 50%. It is bot-dominated across EVERY browser version present, not just
# the Chrome 125.0.0.0 / "Intel 10.15" cluster that spiked 2026-08-19..22, so filtering the resolution
# alone beats pinning the fingerprint -- one dimension, and it survives the next crawler's UA.
#
# Cost of being wrong: it discards ~6 real-looking sessions per quarter. Re-validate with --bots-only,
# which is the same segment inverted; if its engagement rate ever climbs toward the site average, the
# signature has drifted and this needs revisiting.
#
# Why this is read-time and not a GA4 Data Filter: GA4 data filters only come in two flavors, Developer
# traffic (debug_mode) and Internal traffic (a `traffic_type` param populated from IP ranges you declare
# on the stream). Neither can test screen resolution, and GA4 never exposes visitor IP, so the bot ranges
# can't be derived from our own data. A read-time segment is also strictly better here: an Active data
# filter is forward-only and permanently drops the rows, whereas this applies retroactively to the whole
# corpus and can be turned off.
BOT_SCREEN_RESOLUTION = "800x600"
BOT_FILTER = eq("screenResolution", BOT_SCREEN_RESOLUTION)
NOT_BOT_FILTER = not_(BOT_FILTER)

REPORTS = {
    "events": (["eventName"], ["eventCount", "totalUsers"]),
    "pages": (["pageTitle", "pagePath"], ["screenPageViews", "totalUsers"]),
    "funnel": (["eventName"], ["eventCount", "totalUsers"]),
}


def credentials(key_path: Path):
    if not key_path.exists():
        sys.exit(
            f"No service account key at {key_path}\n"
            "Create one with:\n"
            "  gcloud iam service-accounts keys create ~/.gcp/ga4-reader.json \\\n"
            "    --iam-account=ga4-reader@ce-bill-tracker.iam.gserviceaccount.com"
        )
    creds = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=[SCOPE]
    )
    creds.refresh(AuthRequest())
    return creds


def run_report(creds, dimensions, metrics, start, end, limit, event=None, dim_filter=None):
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
    }
    # Server-side filters, not post-filters -- custom dimension breakdowns explode the row count fast,
    # and the API's `limit` applies before we'd ever see the rows we wanted. dim_filter (a composed
    # FilterExpression) and the plain --event match are ANDed, never substituted for one another.
    combined = and_(eq("eventName", event) if event else None, dim_filter)
    if combined:
        body["dimensionFilter"] = combined
    resp = requests.post(
        API.format(prop=PROPERTY_ID),
        headers={"Authorization": f"Bearer {creds.token}"},
        json=body,
        timeout=60,
    )
    if resp.status_code == 403:
        sys.exit(
            "403 from the Data API. The service account almost certainly isn't a GA4 Viewer yet:\n"
            "  GA4 Admin -> Property access management -> + -> add\n"
            "  ga4-reader@ce-bill-tracker.iam.gserviceaccount.com as Viewer\n"
            f"\nGA4 said: {resp.text[:400]}"
        )
    if resp.status_code != 200:
        sys.exit(f"HTTP {resp.status_code} from the Data API:\n{resp.text[:800]}")
    return resp.json()


def to_rows(payload):
    """Flatten the API's dimensionValues/metricValues shape into plain lists of strings."""
    rows = []
    for row in payload.get("rows", []):
        dims = [d.get("value", "") for d in row.get("dimensionValues", [])]
        mets = [m.get("value", "0") for m in row.get("metricValues", [])]
        rows.append(dims + mets)
    return rows


def print_table(headers, rows, totals=None):
    if not rows:
        print("(no rows -- either no traffic in this window, or the events never fired)")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))
    if totals:
        print("  ".join("-" * w for w in widths))
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(totals)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="events", choices=[*REPORTS, "raw"])
    ap.add_argument("--days", type=int, default=28, help="lookback window (ignored if --start given)")
    ap.add_argument("--start", help="YYYY-MM-DD or a GA4 relative date like 28daysAgo")
    ap.add_argument("--end", default="today")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--filter", help="keep only rows whose first dimension contains this substring")
    ap.add_argument("--event", help="restrict to a single eventName (server-side filter)")
    ap.add_argument("--dimensions", help="comma-separated, for --report raw")
    ap.add_argument("--metrics", help="comma-separated, for --report raw")
    ap.add_argument("--key", type=Path, default=Path(os.environ.get("GA4_KEY_FILE", DEFAULT_KEY)))
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--exclude-bots", action="store_true",
                    help=f"drop the datacenter/headless segment (screenResolution={BOT_SCREEN_RESOLUTION})")
    ap.add_argument("--bots-only", action="store_true",
                    help="the inverse -- inspect what --exclude-bots would drop, to re-validate the signature")
    args = ap.parse_args()

    if args.exclude_bots and args.bots_only:
        sys.exit("--exclude-bots and --bots-only are opposites; pass at most one")
    segment = BOT_FILTER if args.bots_only else NOT_BOT_FILTER if args.exclude_bots else None

    start = args.start or f"{args.days}daysAgo"

    if args.report == "raw":
        if not args.dimensions or not args.metrics:
            sys.exit("--report raw needs both --dimensions and --metrics")
        dimensions = args.dimensions.split(",")
        metrics = args.metrics.split(",")
    else:
        dimensions, metrics = REPORTS[args.report]

    creds = credentials(args.key)
    payload = run_report(creds, dimensions, metrics, start, args.end, args.limit, args.event,
                         dim_filter=segment)
    rows = to_rows(payload)

    if args.report == "funnel":
        # Reorder into funnel order and surface the steps that never fired at all, which is the
        # interesting case -- a missing step reads as "instrumented but dead", not "no data".
        counts = {r[0]: r[1:] for r in rows}
        # Replace the raw gate_hit count with walls-only -- see GATE_HIT_WALLED_FILTER.
        walled = to_rows(run_report(creds, ["eventName"], metrics, start, args.end, 10,
                                    dim_filter=and_(GATE_HIT_WALLED_FILTER, segment)))
        counts[GATE_HIT_STEP] = walled[0][1:] if walled else ["0"] * len(metrics)
        rows = [
            [GATE_HIT_LABEL if step == GATE_HIT_STEP else step,
             *counts.get(step, ["0"] * len(metrics))]
            for step in FUNNEL_STEPS
        ]
    elif args.filter:
        rows = [r for r in rows if args.filter in r[0]]

    headers = dimensions + metrics

    if args.json:
        print(json.dumps(
            {"property": PROPERTY_ID, "start": start, "end": args.end,
             "segment": "bots_only" if args.bots_only else "exclude_bots" if args.exclude_bots else "all",
             "headers": headers, "rows": rows},
            indent=2,
        ))
        return

    # Always stamp the segment: a bot-filtered number that looks unlabelled is how you end up quoting
    # two different denominators a week apart and not knowing which was which.
    seg_label = (" | SEGMENT: bots only" if args.bots_only
                 else f" | SEGMENT: excl. bots ({BOT_SCREEN_RESOLUTION})" if args.exclude_bots else "")
    print(f"GA4 property {PROPERTY_ID} | {start} to {args.end} | report={args.report}{seg_label}")
    print()
    totals = None
    for t in payload.get("totals", []):
        vals = [m.get("value", "") for m in t.get("metricValues", [])]
        totals = ["TOTAL"] + [""] * (len(dimensions) - 1) + vals
    print_table(headers, rows, totals if args.report != "funnel" else None)
    print()
    print(f"{len(rows)} rows")


if __name__ == "__main__":
    main()
