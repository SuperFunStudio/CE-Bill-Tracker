"""Generate and (optionally) send the periodic subscriber digest.

The digest is a single periodic roundup per subscriber — bill status changes, newly tracked bills,
and relevant federal actions over a window — scoped to the topics + jurisdictions they signed up
for. See app/alerts/digest.py.

Safe by default: with no flags it is a DRY RUN — it builds each digest, writes the HTML to
tmp/digest_<email>.html, and prints a summary. Nothing is emailed until you pass --send.

Local (against whatever DATABASE_URL points at):
    venv/Scripts/python scripts/send_digest.py

Production preview (via Cloud SQL Auth Proxy on 5434):
    set DATABASE_URL=postgresql://signalscout:Design4thefuture@127.0.0.1:5434/signalscout
    venv/Scripts/python scripts/send_digest.py --window-days 30

Send only to yourself first:
    venv/Scripts/python scripts/send_digest.py --email kenny@superfun.studio --send

Send to all active subscribers:
    venv/Scripts/python scripts/send_digest.py --send
"""
import argparse
import asyncio
import os
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _slug(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", email)


async def run(window_days: int, only_email: str | None, send: bool) -> int:
    from sqlalchemy import func, select

    from app.alerts.digest import build_digests, render_digest_html, render_digest_subject
    from app.database import AsyncSessionLocal

    period_label = "monthly" if 25 <= window_days <= 35 else f"{window_days}-day"

    async with AsyncSessionLocal() as db:
        # Anchor the window to the DB clock so local/prod timezones don't matter.
        now = (await db.execute(select(func.now()))).scalar_one()
        since = now - timedelta(days=window_days)
        digests = await build_digests(db, since)

    if only_email:
        digests = [(s, c) for s, c in digests if s.email == only_email]

    if not digests:
        print(f"No subscribers with matching movement in the last {window_days} days.")
        return 0

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
    if not send:
        os.makedirs(out_dir, exist_ok=True)

    sender = None
    if send:
        from app.alerts.sendgrid_sender import SendGridSender
        from app.config import settings

        if not settings.sendgrid_api_key:
            print("ERROR: --send given but SENDGRID_API_KEY is not set.", file=sys.stderr)
            return 1
        sender = SendGridSender()

    print(f"{'SENDING' if send else 'DRY RUN'} — {len(digests)} digest(s), window {window_days}d:\n")
    sent = 0
    for sub, content in digests:
        subject = render_digest_subject(content, period_label)
        html = render_digest_html(sub, content, period_label)
        summary = (
            f"{len(content.status_changes)} status, "
            f"{len(content.new_bills)} new, "
            f"{len(content.federal_actions)} federal"
        )
        if send and sender is not None:
            ok = await sender.send_html(sub.email, subject, html)
            sent += 1 if ok else 0
            print(f"  {'[ok]' if ok else '[FAIL]'} {sub.email:<40} {summary}")
        else:
            path = os.path.join(out_dir, f"digest_{_slug(sub.email)}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  {sub.email:<40} {summary}  -> {os.path.relpath(path)}")

    if send:
        print(f"\nSent {sent}/{len(digests)} successfully.")
    else:
        print(f"\nWrote {len(digests)} preview file(s) to {os.path.relpath(out_dir)}/. "
              "Open them in a browser, then re-run with --send.")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--window-days", type=int, default=30, help="Look-back window (default 30).")
    ap.add_argument("--email", default=None, help="Only process the subscriber with this email.")
    ap.add_argument("--send", action="store_true", help="Actually send (default is a dry run).")
    args = ap.parse_args()
    return await run(args.window_days, args.email, args.send)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
