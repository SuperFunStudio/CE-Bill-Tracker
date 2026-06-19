"""Render the compliance-action view a state page (or a persona feed) would show:
each enacted law -> its next action, the entity to contact, the deadline, fee flag.

Usage:
  venv/Scripts/python scripts/show_compliance_pathways.py --state CA
  venv/Scripts/python scripts/show_compliance_pathways.py --state OR --material electronics
"""
import argparse

from sqlalchemy import create_engine, text

from app.config import settings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--material", default=None, help="filter to laws covering this material")
    ap.add_argument("--prod-dsn", default=None)
    args = ap.parse_args()
    engine = create_engine(args.prod_dsn or settings.database_url)

    where = "b.state=:st and b.ce_relevant and b.status='enacted'"
    params = {"st": args.state.upper()}
    if args.material:
        where += " and b.material_categories ? :mat"
        params["mat"] = args.material

    sql = text(f"""
        select b.bill_number, b.title, p.action_type, p.action_summary,
               e.name, p.registration_url, p.next_deadline_date, p.has_fee, p.management_model
        from bills b
        join compliance_pathway p on p.bill_id=b.id
        left join compliance_entity e on e.id=p.entity_id
        where {where}
        order by (p.next_deadline_date is null), p.next_deadline_date, b.bill_number
    """)
    with engine.connect() as c:
        rows = list(c.execute(sql, params))

    head = f"COMPLIANCE PATHWAYS — {args.state.upper()}"
    if args.material:
        head += f" · {args.material}"
    print(head)
    print("=" * len(head))
    if not rows:
        print("(no enacted laws match)")
        return
    for bn, title, action, summary, ent, reg, dl, fee, model in rows:
        print(f"\n{bn} — {(title or '')[:64]}")
        print(f"  model: {model}   action: {action}")
        print(f"  >> {summary}")
        if ent:
            print(f"  contact: {ent}")
        if reg:
            print(f"  link: {reg}")
        flags = []
        if dl:
            flags.append(f"next deadline {dl}")
        if fee:
            flags.append("fee applies")
        if flags:
            print(f"  {' · '.join(flags)}")


if __name__ == "__main__":
    main()
