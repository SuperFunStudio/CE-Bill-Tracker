"""List newsletter / alert subscribers.

There is no admin UI for subscriptions — they live in the `alert_subscriptions` table. This script
prints them so you can see who has signed up for free updates and what they follow.

Local:
    venv/Scripts/python scripts/list_subscribers.py

Production (via Cloud SQL Auth Proxy):
    %USERPROFILE%\\cloud-sql-proxy.exe --gcloud-auth --port 5434 ce-bill-tracker:us-central1:signalscout-pg
    set DATABASE_URL=postgresql://signalscout:$DB_PASSWORD@127.0.0.1:5434/signalscout
    venv/Scripts/python scripts/list_subscribers.py --all   # include deactivated rows
"""
import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description="List alert/newsletter subscribers")
    parser.add_argument("--all", action="store_true", help="include inactive (unsubscribed) rows")
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        return 1
    # psycopg2 speaks the sync driver; strip any +asyncpg suffix the app may use.
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    where = "" if args.all else "WHERE active = true"
    query = f"""
        SELECT created_at, email, organization, active, states, instrument_types
        FROM alert_subscriptions
        {where}
        ORDER BY created_at DESC
    """

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    if not rows:
        print("No subscribers found.")
        return 0

    print(f"{len(rows)} subscriber(s):\n")
    for created_at, email, org, active, states, instruments in rows:
        when = created_at.strftime("%Y-%m-%d") if created_at else "?"
        flag = "" if active else "  [unsubscribed]"
        org_str = f" · {org}" if org else ""
        topics = "all topics" if instruments in (["ALL"], None) else ", ".join(instruments)
        places = "all jurisdictions" if states in (["ALL"], None) else ", ".join(states)
        print(f"  {when}  {email or '(no email)'}{org_str}{flag}")
        print(f"            {topics}  |  {places}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
