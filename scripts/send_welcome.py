"""Preview and (optionally) send the one-time welcome email.

The welcome email is the cumulative "state of play" a new subscriber gets on signup — enacted vs.
active bills across the topics + jurisdictions they picked, plus an optional championship-recap
paragraph. See app/alerts/welcome_email.py.

Safe by default: with no flags it is a DRY RUN over existing active subscribers — it builds each
welcome email, writes the HTML to tmp/welcome_<email>.html, and prints a summary. Nothing is emailed
until you pass --send.

Note: the LLM recap only renders if ENABLE_WELCOME_RECAP=true (and ANTHROPIC_API_KEY is set), even on
a dry run. Leave it off to preview the structured-stats layout alone.

Local (against whatever DATABASE_URL points at):
    venv/Scripts/python scripts/send_welcome.py

Production preview (via Cloud SQL Auth Proxy on 5434):
    set DATABASE_URL=postgresql://signalscout:Design4thefuture@127.0.0.1:5434/signalscout
    venv/Scripts/python scripts/send_welcome.py

Preview the recap voice too:
    set ENABLE_WELCOME_RECAP=true
    venv/Scripts/python scripts/send_welcome.py --email kenny@superfun.studio

Send only to yourself first:
    venv/Scripts/python scripts/send_welcome.py --email kenny@superfun.studio --send
"""
import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _slug(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", email)


async def run(only_email: str | None, send: bool) -> int:
    from sqlalchemy import func, select

    from app.alerts.welcome_email import (
        _as_of_label,
        build_state_of_play,
        render_recap_paragraph,
        render_welcome_html,
        render_welcome_subject,
    )
    from app.database import AsyncSessionLocal
    from app.models import AlertSubscription

    async with AsyncSessionLocal() as db:
        q = select(AlertSubscription).where(AlertSubscription.active.is_(True))
        if only_email:
            q = q.where(AlertSubscription.email == only_email)
        subs = [s for s in (await db.execute(q)).scalars().all() if s.email]

        if not subs:
            print("No matching active subscribers with an email.")
            return 0

        now = (await db.execute(select(func.now()))).scalar_one()
        as_of = _as_of_label(now)

        sender = None
        if send:
            from app.config import settings

            if not settings.sendgrid_api_key:
                print("ERROR: --send given but SENDGRID_API_KEY is not set.", file=sys.stderr)
                return 1
            from app.alerts.sendgrid_sender import SendGridSender

            sender = SendGridSender()

        out_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp"
        )
        if not send:
            os.makedirs(out_dir, exist_ok=True)

        print(f"{'SENDING' if send else 'DRY RUN'} — {len(subs)} welcome email(s), as of {as_of}:\n")
        sent = 0
        for sub in subs:
            sop = await build_state_of_play(db, sub)
            recap = await render_recap_paragraph(sub, sop)
            html = render_welcome_html(sub, sop, as_of, recap=recap)
            subject = render_welcome_subject(sub)
            summary = (
                f"{sop.total_bills} bills "
                f"({sop.enacted_total} enacted / {sop.active_total} active)"
                f"{' +recap' if recap else ''}"
            )
            if send and sender is not None:
                ok = await sender.send_html(sub.email, subject, html)
                sent += 1 if ok else 0
                print(f"  {'[ok]' if ok else '[FAIL]'} {sub.email:<40} {summary}")
            else:
                path = os.path.join(out_dir, f"welcome_{_slug(sub.email)}.html")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  {sub.email:<40} {summary}  -> {os.path.relpath(path)}")

    if send:
        print(f"\nSent {sent}/{len(subs)} successfully.")
    else:
        print(f"\nWrote {len(subs)} preview file(s) to {os.path.relpath(out_dir)}/. "
              "Open them in a browser, then re-run with --send.")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--email", default=None, help="Only process the subscriber with this email.")
    ap.add_argument("--send", action="store_true", help="Actually send (default is a dry run).")
    args = ap.parse_args()
    return await run(args.email, args.send)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
