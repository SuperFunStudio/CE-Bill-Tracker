"""Generate and (optionally) send the recurring watch-list "you added bills" recap.

For each already-onboarded account that has added bills since its last recap (a 30-min burst batched
into one email), this builds the recap pointing to My Portfolio. See app/alerts/watchlist_recap.py.

Safe by default: with no flags it is a DRY RUN — it builds each recap, writes the HTML to
tmp/watchlist_recap_<email>.html, prints a summary, and stamps NOTHING. Nothing is emailed and no
watchlist_recap_sent_at is set until you pass --send.

Local preview (use --debounce-minutes 0 so just-added bills show without waiting 30 min):
    venv/Scripts/python scripts/send_watchlist_recap.py --debounce-minutes 0

Send only to yourself first:
    venv/Scripts/python scripts/send_watchlist_recap.py --email kenny@superfun.studio --send

Against prod (via Cloud SQL proxy):
    venv/Scripts/python scripts/send_watchlist_recap.py --dsn "postgresql://signalscout@127.0.0.1:5434/signalscout"
"""
import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _slug(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", email)


async def run(dsn: str | None, debounce_minutes: int | None, only_email: str | None, send: bool) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.alerts.watchlist_recap import (
        DEBOUNCE_MINUTES,
        build_watchlist_recap,
        render_recap_html,
        render_recap_subject,
    )
    from app.config import settings
    from app.database import AsyncSessionLocal

    if debounce_minutes is None:
        debounce_minutes = DEBOUNCE_MINUTES

    # Optional explicit DSN (prod via proxy); otherwise the app's configured DB.
    if dsn:
        for p in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
            if dsn.startswith(p):
                dsn = dsn if p == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(p):]
                break
        Session = async_sessionmaker(create_async_engine(dsn), expire_on_commit=False)
    else:
        Session = AsyncSessionLocal

    async with Session() as db:
        now = datetime.now(timezone.utc)
        recaps = await build_watchlist_recap(db, now, debounce_minutes=debounce_minutes)

        if only_email:
            recaps = [c for c in recaps if c.sub.email == only_email]

        if not recaps:
            print("No accounts with un-recapped watch-list adds (past the debounce window).")
            return 0

        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
        sender = None
        if send:
            from app.alerts.sendgrid_sender import SendGridSender
            from app.alerts.unsubscribe import unsubscribe_url

            if not settings.sendgrid_api_key:
                print("ERROR: --send given but SENDGRID_API_KEY is not set.", file=sys.stderr)
                return 1
            sender = SendGridSender()
        else:
            os.makedirs(out_dir, exist_ok=True)

        print(f"{'SENDING' if send else 'DRY RUN'} — {len(recaps)} recap(s), debounce {debounce_minutes}m:\n")
        sent = 0
        for content in recaps:
            subject = render_recap_subject(content)
            html = render_recap_html(content)
            summary = f"{len(content.new_bills)} new (+{content.new_overflow} overflow), {content.total_watched} total"
            if send and sender is not None:
                from app.alerts.unsubscribe import unsubscribe_url
                from app.alerts.watchlist_recap import render_recap_text

                ok = await sender.send_html(
                    content.sub.email, subject, html,
                    list_unsubscribe_url=unsubscribe_url(content.sub.id),
                    text=render_recap_text(content),
                )
                if ok:
                    sent += 1
                    content.sub.watchlist_recap_sent_at = now
                print(f"  {'[ok]' if ok else '[FAIL]'} {content.sub.email:<40} {summary}")
            else:
                path = os.path.join(out_dir, f"watchlist_recap_{_slug(content.sub.email)}.html")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  {content.sub.email:<40} {summary}  -> {os.path.relpath(path)}")

        if send:
            if sent:
                await db.commit()
            print(f"\nSent {sent}/{len(recaps)}; stamped watchlist_recap_sent_at on each.")
        else:
            print(f"\nWrote {len(recaps)} preview file(s) to {os.path.relpath(out_dir)}/. "
                  "Open them, then re-run with --send.")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--debounce-minutes", type=int, default=None,
                    help="Override the 30-min debounce (use 0 to preview just-added bills).")
    ap.add_argument("--email", default=None, help="Only process the account with this email.")
    ap.add_argument("--send", action="store_true",
                    help="Actually send and stamp watchlist_recap_sent_at (default is a dry run).")
    args = ap.parse_args()
    return await run(args.dsn, args.debounce_minutes, args.email, args.send)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
