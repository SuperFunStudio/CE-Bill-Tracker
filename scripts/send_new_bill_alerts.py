"""Generate and (optionally) send event-triggered "new bill" alerts.

For each active subscriber, this finds newly-tracked relevant bills (created within the window) that
match their topics + jurisdictions and builds one consolidated alert email. See
app/alerts/new_bill_alerts.py.

Safe by default: with no flags it is a DRY RUN — it builds each alert, writes the HTML to
tmp/new_bill_alert_<email>.html, prints a summary, and marks NOTHING. Nothing is emailed and no
`new_bill_alert_sent` flag is set until you pass --send.

Local:
    venv/Scripts/python scripts/send_new_bill_alerts.py

Send only to yourself first:
    venv/Scripts/python scripts/send_new_bill_alerts.py --email kenny@superfun.studio --send

Send to all active subscribers (marks new_bill_alert_sent on every bill emailed):
    venv/Scripts/python scripts/send_new_bill_alerts.py --send
"""
import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _slug(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", email)


async def run(window_days: int | None, only_email: str | None, send: bool) -> int:
    from sqlalchemy import func, select, update

    from app.alerts.new_bill_alerts import (
        build_new_bill_alerts,
        render_new_bill_alert_html,
        render_new_bill_alert_subject,
    )
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models import Bill

    if window_days is None:
        window_days = settings.new_bill_alert_window_days

    async with AsyncSessionLocal() as db:
        today = (await db.execute(select(func.current_date()))).scalar_one()
        alerts = await build_new_bill_alerts(db, today, window_days)

        if only_email:
            alerts = [(s, c) for s, c in alerts if s.email == only_email]

        if not alerts:
            print(f"No subscribers with new matching bills in the last {window_days} days.")
            return 0

        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
        sender = None
        if send:
            from app.alerts.sendgrid_sender import SendGridSender

            if not settings.sendgrid_api_key:
                print("ERROR: --send given but SENDGRID_API_KEY is not set.", file=sys.stderr)
                return 1
            sender = SendGridSender()
        else:
            os.makedirs(out_dir, exist_ok=True)

        print(f"{'SENDING' if send else 'DRY RUN'} — {len(alerts)} alert(s), window {window_days}d:\n")
        sent = 0
        sent_bill_ids: set[int] = set()
        for sub, content in alerts:
            subject = render_new_bill_alert_subject(content)
            html = render_new_bill_alert_html(sub, content)
            summary = f"{content.total} new bill(s)"
            if send and sender is not None:
                ok = await sender.send_html(sub.email, subject, html)
                sent += 1 if ok else 0
                if ok:
                    sent_bill_ids.update(b.id for b in content.bills)
                print(f"  {'[ok]' if ok else '[FAIL]'} {sub.email:<40} {summary}")
            else:
                path = os.path.join(out_dir, f"new_bill_alert_{_slug(sub.email)}.html")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  {sub.email:<40} {summary}  -> {os.path.relpath(path)}")

        if send:
            if sent_bill_ids:
                await db.execute(
                    update(Bill).where(Bill.id.in_(sent_bill_ids)).values(new_bill_alert_sent=True)
                )
                await db.commit()
            print(f"\nSent {sent}/{len(alerts)} successfully; marked {len(sent_bill_ids)} bill(s) alerted.")
        else:
            print(f"\nWrote {len(alerts)} preview file(s) to {os.path.relpath(out_dir)}/. "
                  "Open them in a browser, then re-run with --send.")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--window-days", type=int, default=None,
                    help="Alert on bills created within this many days (default: settings value).")
    ap.add_argument("--email", default=None, help="Only process the subscriber with this email.")
    ap.add_argument("--send", action="store_true",
                    help="Actually send and mark new_bill_alert_sent (default is a dry run).")
    args = ap.parse_args()
    return await run(args.window_days, args.email, args.send)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
