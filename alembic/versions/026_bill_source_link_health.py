"""Add per-bill source-link health to bills

Revision ID: 026
Revises: 025
Create Date: 2026-06-23

The "View Source" link on a bill points at bills.source_url — usually a state-legislature page that
rots or flakes (moves, 404s, throws an intermittent WAF/timeout). scripts/audit_bill_source_links.py
pings each one and records the verdict here, so the frontend can offer a fallback (the resolved URL
on a redirect, a LegiScan backup on a dead link) instead of dropping the user on a connection error.

  source_url_status      one of the link-health buckets: alive | redirected | dead | blocked
                         (see app/links/health.py). NULL = never checked.
  source_url_final       the URL after redirects, populated when status='redirected' so the UI can
                         link to where the page actually moved.
  source_url_checked_at  when the audit last ran for this row (so stale verdicts can be re-checked).

All nullable, no server_default: an unchecked bill is NULL, and NULL means "treat the original link
as fine" — we never degrade a link we haven't actually verified as broken.
"""
from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Each ADD COLUMN needs an ACCESS EXCLUSIVE lock on the hot `bills` table. The always-on API's
    # connection pool can leave a connection "idle in transaction" holding ACCESS SHARE on bills
    # indefinitely, which starves the lock and makes the deploy's 15s lock_timeout fail every retry
    # (observed on this migration's first deploy). Terminate only such abandoned transactions first —
    # they hold locks but do no work; the API simply reconnects. Active queries are left untouched.
    # Same guard as migration 025's rename.
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid()
          AND state = 'idle in transaction'
          AND xact_start < now() - interval '5 seconds'
        """
    )
    op.add_column("bills", sa.Column("source_url_status", sa.String(length=20), nullable=True))
    op.add_column("bills", sa.Column("source_url_final", sa.Text(), nullable=True))
    op.add_column(
        "bills",
        sa.Column("source_url_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bills", "source_url_checked_at")
    op.drop_column("bills", "source_url_final")
    op.drop_column("bills", "source_url_status")
