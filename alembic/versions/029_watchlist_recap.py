"""Add watchlist_recap_sent_at to alert_subscriptions — recurring watch-list "you added bills" recap

Revision ID: 029
Revises: 028
Create Date: 2026-06-26

The one-time onboarding email (027) fires on a user's FIRST star. This adds the high-water mark for a
RECURRING recap: when an already-onboarded user adds more bills, run_watchlist_recap_cycle batches a
30-min burst into one "you're now also tracking…" email and stamps the send time here, so each set of
adds is recapped exactly once. Nullable, no backfill (treated as "nothing recapped yet" — the cycle's
COALESCE falls back to onboarding_email_sent_at, so pre-existing watch lists won't get a retro blast).
"""
from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_subscriptions",
        sa.Column("watchlist_recap_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_subscriptions", "watchlist_recap_sent_at")
