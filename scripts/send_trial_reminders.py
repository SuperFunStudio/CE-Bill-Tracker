"""Generate and (optionally) send trial-ending reminders.

Finds accounts on a no-card comp trial (7-day signup / 30-day referral) whose grant expires within the
lead window and builds a "keep your access" email anchored on the founding offer. See
app/alerts/trial_reminders.py.

Safe by default: with no flags it is a DRY RUN — it builds each reminder, writes the HTML to
tmp/trial_reminder_<email>.html, prints a summary, and marks NOTHING. Nothing is emailed and no
trial_reminder_sent_for is set until you pass --send.

Local (against whatever DATABASE_URL points at):
    venv/Scripts/python scripts/send_trial_reminders.py

Widen the window to catch more trials for a preview:
    venv/Scripts/python scripts/send_trial_reminders.py --lead-days 40

Send only to yourself first:
    venv/Scripts/python scripts/send_trial_reminders.py --email kenny@superfun.studio --send

Send to everyone with a lapsing trial (marks trial_reminder_sent_for on each):
    venv/Scripts/python scripts/send_trial_reminders.py --send
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
    from datetime import datetime, timezone

    from app.alerts.trial_reminders import (
        build_trial_reminders,
        render_trial_reminder_html,
        render_trial_reminder_subject,
    )
    from app.config import settings
    from app.database import AsyncSessionLocal

    if lead_days is None:
        lead_days = settings.trial_reminder_lead_days

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        items = await build_trial_reminders(db, now, lead_days)

        if only_email:
            items = [it for it in items if it.entitlement.email == only_email]

        if not items:
            print(f"No comp trials expiring inside the next {lead_days} days.")
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

        print(f"{'SENDING' if send else 'DRY RUN'} — {len(items)} reminder(s), lead {lead_days}d:\n")
        sent = 0
        for item in items:
            ent = item.entitlement
            subject = render_trial_reminder_subject(item)
            html = render_trial_reminder_html(item)
            summary = f"trial ends in {item.days_until}d"
            if send and sender is not None:
                ok = await sender.send_html(ent.email, subject, html)
                sent += 1 if ok else 0
                if ok:
                    ent.trial_reminder_sent_for = ent.current_period_end
                print(f"  {'[ok]' if ok else '[FAIL]'} {ent.email:<40} {summary}")
            else:
                path = os.path.join(out_dir, f"trial_reminder_{_slug(ent.email)}.html")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  {ent.email:<40} {summary}  -> {os.path.relpath(path)}")

        if send:
            if sent:
                await db.commit()
            print(f"\nSent {sent}/{len(items)} successfully; marked {sent} trial(s) reminded.")
        else:
            print(f"\nWrote {len(items)} preview file(s) to {os.path.relpath(out_dir)}/. "
                  "Open them in a browser, then re-run with --send.")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--lead-days", type=int, default=None,
                    help="Remind on trials expiring within this many days (default: settings value).")
    ap.add_argument("--email", default=None, help="Only process the account with this email.")
    ap.add_argument("--send", action="store_true",
                    help="Actually send and mark trial_reminder_sent_for (default is a dry run).")
    args = ap.parse_args()
    return await run(args.lead_days, args.email, args.send)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
