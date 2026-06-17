"""Copy the computed management_model classification (bills.compliance_details->'management')
from LOCAL to PROD, so the compliance pathway layer can be built on prod without re-running the
LLM extraction there. Match by openstates_id (deterministic, incl. hist: ids); fall back to
(state, bill_number) for null-id rows. Idempotent (merges the 'management' key, preserves the
rest of compliance_details). Reports match rate so a low overlap is visible, not silent.

After this, run:  venv/Scripts/python scripts/build_compliance_pathways.py --prod-dsn "<prod>"

Usage:
  venv/Scripts/python scripts/sync_management_to_prod.py --prod-dsn "postgresql://signalscout:***@localhost:5434/signalscout"
  add --apply to write (default is a dry run that only reports the match rate)
"""
import argparse
import json

from sqlalchemy import create_engine, text

from app.config import settings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod-dsn", required=True)
    ap.add_argument("--apply", action="store_true", help="write to prod (default: dry run)")
    args = ap.parse_args()

    local = create_engine(settings.database_url)
    prod = create_engine(args.prod_dsn)

    with local.connect() as c:
        rows = list(c.execute(text("""
            select state, bill_number, openstates_id, compliance_details->'management' as mgmt
            from bills
            where epr_relevant and state!='US' and status='enacted'
              and compliance_details->'management' is not null
        """)))
    print(f"local enacted laws with a management classification: {len(rows)}")

    matched = unmatched = 0
    updates = []  # (prod_bill_id, mgmt_json)
    with prod.connect() as pc:
        for state, bn, osid, mgmt in rows:
            pid = None
            if osid:
                pid = pc.execute(text("select id from bills where openstates_id=:o"),
                                 {"o": osid}).scalar()
            if pid is None and bn:
                pid = pc.execute(text(
                    "select id from bills where state=:s and bill_number=:b and status='enacted'"),
                    {"s": state, "b": bn}).scalar()
            if pid is None:
                unmatched += 1
                print(f"  UNMATCHED: {state} {bn} ({osid})")
                continue
            matched += 1
            updates.append((pid, json.dumps(mgmt)))

    print(f"\nmatched {matched} / {len(rows)} on prod  (unmatched {unmatched})")
    if not args.apply:
        print("\n(dry run — re-run with --apply to write)")
        return

    with prod.begin() as pc:
        for pid, mgmt_json in updates:
            pc.execute(text("""
                update bills set compliance_details =
                    coalesce(compliance_details, '{}'::jsonb)
                    || jsonb_build_object('management', cast(:m as jsonb))
                where id = :pid
            """), {"m": mgmt_json, "pid": pid})
    print(f"\napplied {len(updates)} management classifications to prod.")


if __name__ == "__main__":
    main()
