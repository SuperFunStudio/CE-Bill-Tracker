"""Rename epr_relevant -> ce_relevant on bills and federal_actions

Revision ID: 025
Revises: 024
Create Date: 2026-06-18

The flag was always *circular-economy* relevance across the full instrument range we track (EPR,
deposit-return, right-to-repair, recycled-content, incentives, labeling, …), not Extended Producer
Responsibility specifically — "epr_relevant" was a legacy misnomer. Pure column rename; the
idx_bills_relevant index follows the renamed column automatically (its name is left unchanged).
"""
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The RENAME needs an ACCESS EXCLUSIVE lock on the hot `bills` table. The always-on API's
    # connection pool can leave a connection "idle in transaction" holding ACCESS SHARE on bills
    # indefinitely (observed: one abandoned ~16h), which starves the lock and makes the deploy's
    # 15s lock_timeout fail every retry. Terminate only such abandoned transactions first — they
    # hold locks but do no work; the API simply reconnects. Active queries are left untouched.
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
    op.alter_column("bills", "epr_relevant", new_column_name="ce_relevant")
    op.alter_column("federal_actions", "epr_relevant", new_column_name="ce_relevant")


def downgrade() -> None:
    op.alter_column("bills", "ce_relevant", new_column_name="epr_relevant")
    op.alter_column("federal_actions", "ce_relevant", new_column_name="epr_relevant")
