"""List "request access / pricing" leads.

There is no admin UI for access requests — they live in the `access_requests` table (the
willingness-to-pay capture). This prints them so you can see who's asking for what tier, from which
org. Each new request also emails kenny@superfun.studio in real time; this is the historical view.

Local:
    venv/Scripts/python scripts/list_access_requests.py

Production (via Cloud SQL Auth Proxy):
    %USERPROFILE%\\cloud-sql-proxy.exe --gcloud-auth --port 5434 ce-bill-tracker:us-central1:signalscout-pg
    set DATABASE_URL=postgresql://signalscout:$DB_PASSWORD@127.0.0.1:5434/signalscout
    venv/Scripts/python scripts/list_access_requests.py

Remove the post-deploy verification rows once you've reviewed them:
    venv/Scripts/python scripts/list_access_requests.py --purge-test
"""
import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Source tag used by the post-deploy smoke tests; --purge-test removes exactly these.
_TEST_SOURCE = "deploy_test"


def main() -> int:
    parser = argparse.ArgumentParser(description="List access-request / pricing leads")
    parser.add_argument(
        "--purge-test",
        action="store_true",
        help=f"delete rows where source = '{_TEST_SOURCE}' (post-deploy verification rows)",
    )
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        return 1
    # psycopg2 speaks the sync driver; strip any +asyncpg suffix the app may use.
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        if args.purge_test:
            cur.execute("DELETE FROM access_requests WHERE source = %s", (_TEST_SOURCE,))
            conn.commit()
            print(f"Deleted {cur.rowcount} test row(s) (source = '{_TEST_SOURCE}').")
            return 0

        cur.execute(
            """
            SELECT created_at, email, name, organization, plan_interest, source, message
            FROM access_requests
            ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()

    if not rows:
        print("No access requests yet.")
        return 0

    print(f"{len(rows)} access request(s):\n")
    for created_at, email, name, org, plan, source, message in rows:
        when = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "?"
        who = " · ".join(p for p in (name, org) if p)
        tag = f"  [{source}]" if source else ""
        print(f"  {when}  {plan or '?':<16} {email}{tag}")
        if who:
            print(f"            {who}")
        if message:
            print(f"            “{message}”")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
