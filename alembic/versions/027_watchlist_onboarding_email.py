"""Add onboarding_email_sent_at to alert_subscriptions — once-per-account watch-list onboarding

Revision ID: 027
Revises: 026
Create Date: 2026-06-24

When a Pro user stars their first bill we wait ~1h (so a burst of stars batches into one email) then
send a single watch-list onboarding email listing everything they follow. This column is the
idempotency stamp on the user's "watchlist"-scope subscription row: NULL = not yet onboarded; set to
the send time once the onboarding email goes out, so run_watchlist_onboarding_cycle sends exactly
once per account. Nullable, no backfill (existing watch lists are treated as already-onboarded by the
cycle's lookback guard).
"""
from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_subscriptions",
        sa.Column("onboarding_email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_subscriptions", "onboarding_email_sent_at")
