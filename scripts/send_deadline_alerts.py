"""Generate and (optionally) send event-triggered compliance-deadline reminders.

For each active subscriber, this finds the deadlines they follow that fall within the lead window
(default: max of settings.deadline_reminder_days) and builds one consolidated reminder email. See
app/alerts/deadline_alerts.py.

Safe by default: with no flags it is a DRY RUN — it builds each reminder, writes the HTML to
tmp/deadline_alert_<email>.html, prints a summary, and marks NOTHING. Nothing is emailed and no
`reminder_sent` flag is set until you pass --send.

Local (against whatever DATABASE_URL points at):
    venv/Scripts/python scripts/send_deadline_alerts.py

Production preview (via Cloud SQL Auth Proxy on 5434):
    set DATABASE_URL=postgresql://signalscout:$DB_PASSWORD@127.0.0.1:5434/signalscout
    venv/Scripts/python scripts/send_deadline_alerts.py --lead-days 30

Send only to yourself first:
    venv/Scripts/python scripts/send_deadline_alerts.py --email kenny@superfun.studio --send

Send to all active subscribers (marks reminder_sent on every deadline emailed):
    venv/Scripts/python scripts/send_deadline_alerts.py --send
"""
import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _slug(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", email)


async def run(lead_days: int | None, only_email: str | None, send: bool) -> int:
    from sqlalchemy import func, select, update

    from app.alerts.deadline_alerts import (
        build_deadline_alerts,
        render_deadline_alert_html,
        render_deadline_alert_subject,
    )
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models import ComplianceDeadline

    if lead_days is None:
        lead_days = max(settings.deadline_reminder_days) if settings.deadline_reminder_days else 30

    async with AsyncSessionLocal() as db:
        # Anchor "today" to the DB clock so local/prod timezones don't matter.
        today = (await db.execute(select(func.current_date()))).scalar_one()
        alerts = await build_deadline_alerts(db, today, lead_days)

        if only_email:
            alerts = [(s, c) for s, c in alerts if s.email == only_email]

        if not alerts:
            print(f"No subscribers with deadlines inside the next {lead_days} days.")
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

        print(f"{'SENDING' if send else 'DRY RUN'} — {len(alerts)} reminder(s), lead {lead_days}d:\n")
        sent = 0
        sent_deadline_ids: set[int] = set()
        for sub, content in alerts:
            subject = render_deadline_alert_subject(content)
            html = render_deadline_alert_html(sub, content)
            summary = f"{content.total} deadline(s), soonest in {min(it.days_until for it in content.items)}d"
            if send and sender is not None:
                ok = await sender.send_html(sub.email, subject, html)
                sent += 1 if ok else 0
                if ok:
                    sent_deadline_ids.update(it.deadline.id for it in content.items)
                print(f"  {'[ok]' if ok else '[FAIL]'} {sub.email:<40} {summary}")
            else:
                path = os.path.join(out_dir, f"deadline_alert_{_slug(sub.email)}.html")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  {sub.email:<40} {summary}  -> {os.path.relpath(path)}")

        if send:
            # Mark only deadlines that actually went out, so unmatched ones stay eligible.
            if sent_deadline_ids:
                await db.execute(
                    update(ComplianceDeadline)
                    .where(ComplianceDeadline.id.in_(sent_deadline_ids))
                    .values(reminder_sent=True)
                )
                await db.commit()
            print(f"\nSent {sent}/{len(alerts)} successfully; marked {len(sent_deadline_ids)} deadline(s) reminded.")
        else:
            print(f"\nWrote {len(alerts)} preview file(s) to {os.path.relpath(out_dir)}/. "
                  "Open them in a browser, then re-run with --send.")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--lead-days", type=int, default=None,
                    help="Remind on deadlines within this many days (default: max reminder threshold).")
    ap.add_argument("--email", default=None, help="Only process the subscriber with this email.")
    ap.add_argument("--send", action="store_true",
                    help="Actually send and mark reminder_sent (default is a dry run).")
    args = ap.parse_args()
    return await run(args.lead_days, args.email, args.send)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
