"""Journey analysis over the GA4 BigQuery export — the questions the GA4 UI can't answer.

GA4's reports are aggregates: they can tell you 85 people came, never who they were, what order they
did things in, or which of them came back. The BigQuery export carries `user_pseudo_id` on every
event, so the same property becomes per-person and sequential. That's the difference between "62
returning users" and "here is what session #106 actually did".

Every report here is BOT-EXCLUDED BY DEFAULT, because the raw numbers are materially wrong without
it. A 28-day sample showed ~100 of 404 "new users" arriving from cloud regions (Ashburn = AWS
us-east-1, Council Bluffs = GCP us-central1, Boardman = AWS us-west-2, Dublin/Amsterdam = the EU
regions) with one session each, no return visit, and literally zero engagement time. GA4's built-in
"known bots and spiders" filter does not catch headless Chrome. Pass --include-bots to see the raw
picture, or --report bots to see exactly who was excluded and why.

A note on what the classifier deliberately does NOT use: screenPageViews. Until 2026-08-12 a race
between RouteAnalytics and the gtag script dropped the first page_view of most sessions (419
session_start users against 104 page_view users), so a zero-pageview user is evidence of a bug we
fixed, not of a bot. The signals below are independent of it.

Auth: application-default credentials — the same `gcloud auth` login the bq CLI uses. No key file.

Usage:
  venv/Scripts/python scripts/ga4_journeys.py                      # bots report, last 7 days
  venv/Scripts/python scripts/ga4_journeys.py --report journeys --days 3
  venv/Scripts/python scripts/ga4_journeys.py --report returning --days 28
  venv/Scripts/python scripts/ga4_journeys.py --report paths --start 20260813 --end 20260820
  venv/Scripts/python scripts/ga4_journeys.py --report funnel --include-bots
  venv/Scripts/python scripts/ga4_journeys.py --report journeys --json
"""
import argparse
import json
import sys
from datetime import date, timedelta

import requests
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as AuthRequest

PROJECT = "ce-bill-tracker"
DATASET = "analytics_529411970"
API = "https://bigquery.googleapis.com/bigquery/v2/projects/{p}/queries"
SCOPES = ["https://www.googleapis.com/auth/bigquery"]

# Cloud regions that show up as "cities" in IP geolocation. A visitor can legitimately appear here via
# a VPN, which is why datacenter geography alone never condemns a user — it's one signal of several in
# the score below.
DATACENTER_CITIES = (
    "'Ashburn', 'Council Bluffs', 'Boardman', 'Moses Lake', 'The Dalles', 'Quincy', "
    "'Papillion', 'Dublin', 'Amsterdam', 'Frankfurt am Main', 'Eemshaven', 'Groningen', "
    "'St Ghislain', 'Saint-Ghislain', 'Hamina', 'Flint Hill', 'Secaucus', 'Kansas City'"
)


# ---------------------------------------------------------------------------
# The classifier. One row per user_pseudo_id, with a score and a stated reason.
# ---------------------------------------------------------------------------
#
# Scored rather than boolean because no single signal is conclusive: a real person can be in Dublin,
# and a real person can have one short session. It's the COMBINATION that's damning — a brand-new
# visitor from a cloud region who never scrolls, never returns, and accrues zero engagement time.
USERS_CTE = """
users AS (
  SELECT
    user_pseudo_id AS uid,
    ANY_VALUE(geo.country) AS country,
    ANY_VALUE(geo.city) AS city,
    ANY_VALUE(device.web_info.browser) AS browser,
    ANY_VALUE(device.operating_system) AS os,
    ANY_VALUE(traffic_source.source) AS source,
    ANY_VALUE(traffic_source.medium) AS medium,
    MIN(user_first_touch_timestamp) AS first_touch,
    COUNT(*) AS events,
    COUNT(DISTINCT (SELECT value.int_value FROM UNNEST(event_params) WHERE key='ga_session_id')) AS sessions,
    MAX((SELECT value.int_value FROM UNNEST(event_params) WHERE key='ga_session_number')) AS max_session_no,
    COUNTIF(event_name='page_view') AS page_views,
    -- The load-bearing signal. gtag's engagement timer is independent of the page_view race, so a
    -- true zero here means nothing was ever on screen and interacted with.
    SUM((SELECT value.int_value FROM UNNEST(event_params) WHERE key='engagement_time_msec')) AS engagement_ms,
    COUNTIF(event_name='scroll') AS scrolls,
    COUNTIF(event_name IN ('bill_open','atlas_query_submitted','subscribe','sign_up','login',
                           'request_access','pricing_cta','watchlist_toggle','label_generate',
                           'gate_hit','home_globe_select','scope_sync_cta')) AS intent_events
  FROM `{project}.{dataset}.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '{start}' AND '{end}'
  GROUP BY uid
),
-- Arrival bursts: several "new users" whose very first touch falls within seconds of each other is a
-- fleet, not a coincidence. A SLIDING window, not fixed buckets — the first burst this caught
-- (three uids spanning 4.5s) straddled a 5-second boundary and scored 2-and-1 instead of 3, which is
-- exactly how fixed bucketing hides the thing you're looking for.
scored AS (
  SELECT
    u.*,
    COUNT(*) OVER (
      ORDER BY u.first_touch
      RANGE BETWEEN 3000000 PRECEDING AND 3000000 FOLLOWING
    ) AS burst_size,
    (
      IF(IFNULL(u.engagement_ms, 0) = 0, 2, 0)
      -- Blank geo. A real IP almost always resolves to at least a country; datacenter and privacy-
      -- relay egress often resolves to nothing. This was the signal that separated the first
      -- confirmed fleet from the humans beside it in the same minute.
      + IF(u.country IS NULL OR u.country = '', 2, 0)
      + IF(u.city IN ({dc_cities}), 2, 0)
      + IF(u.browser = 'Mozilla Compatible Agent', 2, 0)
      + IF(u.browser = 'Chrome' AND u.os = 'Linux' AND IFNULL(u.engagement_ms, 0) = 0, 1, 0)
      + IF(u.sessions = 1 AND u.scrolls <= 1 AND u.intent_events = 0, 1, 0)
      + IF(COUNT(*) OVER (
            ORDER BY u.first_touch
            RANGE BETWEEN 3000000 PRECEDING AND 3000000 FOLLOWING
          ) >= 3, 2, 0)
    ) AS bot_score
  FROM users u
),
classified AS (
  SELECT
    *,
    bot_score >= 3 AS is_bot,
    ARRAY_TO_STRING(ARRAY(
      SELECT r FROM UNNEST([
        IF(IFNULL(engagement_ms,0)=0, 'zero-engagement', NULL),
        IF(country IS NULL OR country = '', 'blank-geo', NULL),
        IF(city IN ({dc_cities}), 'datacenter-geo', NULL),
        IF(browser='Mozilla Compatible Agent', 'non-standard-UA', NULL),
        IF(browser='Chrome' AND os='Linux' AND IFNULL(engagement_ms,0)=0, 'headless-chrome', NULL),
        IF(burst_size>=3, 'arrival-burst', NULL),
        IF(sessions=1 AND scrolls<=1 AND intent_events=0, 'no-interaction', NULL)
      ]) AS r WHERE r IS NOT NULL
    ), '+') AS reasons
  FROM scored
)
"""

REPORTS = {}


def _report(name):
    def wrap(fn):
        REPORTS[name] = fn
        return fn
    return wrap


@_report("bots")
def q_bots(_):
    """Who got excluded, why, and how much of the audience it is."""
    return """
    SELECT
      is_bot,
      COUNT(*) AS users,
      SUM(sessions) AS sessions,
      SUM(events) AS events,
      ROUND(SUM(IFNULL(engagement_ms,0))/1000) AS engagement_s,
      SUM(intent_events) AS intent_events,
      STRING_AGG(DISTINCT NULLIF(reasons,''), ', ' LIMIT 6) AS example_reasons
    FROM classified
    GROUP BY is_bot
    ORDER BY is_bot
    """


@_report("bots_detail")
def q_bots_detail(_):
    """The excluded users themselves — audit the classifier before trusting it."""
    return """
    SELECT country, city, browser, os, users, sessions, engagement_s, reasons
    FROM (
      SELECT
        country, city, browser, os,
        COUNT(*) AS users, SUM(sessions) AS sessions,
        ROUND(SUM(IFNULL(engagement_ms,0))/1000) AS engagement_s,
        STRING_AGG(DISTINCT NULLIF(reasons,''), ' | ' LIMIT 3) AS reasons
      FROM classified WHERE is_bot
      GROUP BY country, city, browser, os
    )
    ORDER BY users DESC
    LIMIT 40
    """


@_report("journeys")
def q_journeys(_):
    """Per-person event sequence — the actual "what did they do, in what order"."""
    return """
    , seq AS (
      SELECT
        e.user_pseudo_id AS uid,
        STRING_AGG(
          e.event_name || IFNULL(
            ' [' || REGEXP_REPLACE(
              (SELECT value.string_value FROM UNNEST(e.event_params) WHERE key='page_location'),
              r'^https?://[^/]+', '') || ']', ''),
          ' -> ' ORDER BY e.event_timestamp LIMIT 25
        ) AS journey
      FROM `{project}.{dataset}.events_*` e
      WHERE _TABLE_SUFFIX BETWEEN '{start}' AND '{end}'
        AND e.event_name NOT IN ('user_engagement')
      GROUP BY uid
    )
    SELECT
      c.uid, c.country, c.city, c.source, c.medium,
      c.max_session_no AS session_no, c.sessions, c.events,
      ROUND(IFNULL(c.engagement_ms,0)/1000) AS engagement_s,
      s.journey
    FROM classified c JOIN seq s USING (uid)
    WHERE {bot_filter}
    ORDER BY c.engagement_ms DESC NULLS LAST
    LIMIT 40
    """


@_report("returning")
def q_returning(_):
    """The returning cohort — the most engaged and least understood group on the site."""
    return """
    SELECT
      CASE
        WHEN max_session_no = 1 THEN '1 (first visit)'
        WHEN max_session_no BETWEEN 2 AND 3 THEN '2-3'
        WHEN max_session_no BETWEEN 4 AND 10 THEN '4-10'
        WHEN max_session_no BETWEEN 11 AND 30 THEN '11-30'
        ELSE '31+'
      END AS session_number_band,
      COUNT(*) AS users,
      SUM(sessions) AS sessions,
      ROUND(SUM(IFNULL(engagement_ms,0))/1000) AS engagement_s,
      ROUND(AVG(IFNULL(engagement_ms,0))/1000, 1) AS avg_engagement_s,
      SUM(intent_events) AS intent_events
    FROM classified
    WHERE {bot_filter}
    GROUP BY session_number_band
    ORDER BY MIN(max_session_no)
    """


@_report("paths")
def q_paths(_):
    """Entry page -> next page. Where people land and what they do next."""
    return """
    , pv AS (
      SELECT
        user_pseudo_id AS uid,
        (SELECT value.int_value FROM UNNEST(event_params) WHERE key='ga_session_id') AS sid,
        event_timestamp AS ts,
        REGEXP_REPLACE(
          (SELECT value.string_value FROM UNNEST(event_params) WHERE key='page_location'),
          r'^https?://[^/]+|\\?.*$', '') AS path
      FROM `{project}.{dataset}.events_*`
      WHERE _TABLE_SUFFIX BETWEEN '{start}' AND '{end}' AND event_name='page_view'
    ), steps AS (
      SELECT
        uid, path AS entry,
        LEAD(path) OVER (PARTITION BY uid, sid ORDER BY ts) AS next_path
      FROM pv
    )
    SELECT
      s.entry,
      IFNULL(s.next_path, '(exit)') AS next_path,
      COUNT(*) AS transitions,
      COUNT(DISTINCT s.uid) AS users
    FROM steps s JOIN classified c ON c.uid = s.uid
    WHERE {bot_filter}
    GROUP BY entry, next_path
    ORDER BY transitions DESC
    LIMIT 40
    """


@_report("funnel")
def q_funnel(_):
    """Key events by real users — the conversion spine, with bots stripped out."""
    return """
    , ev AS (
      SELECT user_pseudo_id AS uid, event_name
      FROM `{project}.{dataset}.events_*`
      WHERE _TABLE_SUFFIX BETWEEN '{start}' AND '{end}'
    )
    SELECT
      ev.event_name,
      COUNT(*) AS events,
      COUNT(DISTINCT ev.uid) AS users
    FROM ev JOIN classified c ON c.uid = ev.uid
    WHERE {bot_filter}
    GROUP BY ev.event_name
    ORDER BY users DESC, events DESC
    LIMIT 60
    """


def run_query(creds, sql):
    resp = requests.post(
        API.format(p=PROJECT),
        headers={"Authorization": f"Bearer {creds.token}"},
        json={"query": sql, "useLegacySql": False, "timeoutMs": 120000, "maxResults": 200},
        timeout=180,
    )
    if resp.status_code != 200:
        sys.exit(f"BigQuery HTTP {resp.status_code}:\n{resp.text[:900]}")
    payload = resp.json()
    if not payload.get("jobComplete"):
        sys.exit("Query did not complete within the timeout — narrow the date range and retry.")
    fields = [f["name"] for f in payload.get("schema", {}).get("fields", [])]
    rows = [[c.get("v") for c in r.get("f", [])] for r in payload.get("rows", [])]
    return fields, rows


def print_table(headers, rows):
    if not rows:
        print("(no rows — check the date range; the export is not backfilled, so days before you")
        print(" linked BigQuery simply do not exist)")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(str(c)))
    # Journeys are long; let the last column run rather than padding the terminal to death.
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(c).ljust(widths[i]) if i < len(row) - 1 else str(c)
                        for i, c in enumerate(row)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="bots", choices=sorted(REPORTS))
    ap.add_argument("--days", type=int, default=7, help="lookback window (ignored if --start given)")
    ap.add_argument("--start", help="YYYYMMDD table suffix")
    ap.add_argument("--end", help="YYYYMMDD table suffix")
    ap.add_argument("--include-bots", action="store_true",
                    help="don't filter probable bots (the raw, wrong-but-honest picture)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sql", action="store_true", help="print the SQL instead of running it")
    args = ap.parse_args()

    end = args.end or date.today().strftime("%Y%m%d")
    start = args.start or (date.today() - timedelta(days=args.days)).strftime("%Y%m%d")

    body = REPORTS[args.report](args)
    # The bots reports classify rather than filter, so they must see everything.
    bot_filter = "TRUE" if (args.include_bots or args.report.startswith("bots")) else "NOT c.is_bot"
    # `classified` is aliased `c` in most reports but bare in the aggregate ones.
    if args.report in ("returning",):
        bot_filter = "TRUE" if args.include_bots else "NOT is_bot"

    sql = ("WITH " + USERS_CTE + body).format(
        project=PROJECT, dataset=DATASET, start=start, end=end,
        dc_cities=DATACENTER_CITIES, bot_filter=bot_filter,
    )

    if args.sql:
        print(sql)
        return

    creds, _ = google_auth_default(scopes=SCOPES)
    creds.refresh(AuthRequest())
    fields, rows = run_query(creds, sql)

    if args.json:
        print(json.dumps({"report": args.report, "start": start, "end": end,
                          "bots_excluded": not args.include_bots,
                          "headers": fields, "rows": rows}, indent=2))
        return

    excluded = "raw (bots INCLUDED)" if args.include_bots else "bots excluded"
    print(f"GA4 export {PROJECT}.{DATASET} | {start}..{end} | {args.report} | {excluded}")
    print()
    print_table(fields, rows)
    print()
    print(f"{len(rows)} rows")


if __name__ == "__main__":
    main()
