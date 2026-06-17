"""Add trial_reminder_sent_for to entitlements — idempotency for the trial-ending reminder

Revision ID: 023
Revises: 022
Create Date: 2026-06-16

run_trial_reminder_cycle emails accounts whose no-card comp trial is about to lapse. This column holds
the expiry we last reminded for (== current_period_end after sending), so the daily cycle sends once
per trial; an extended/re-granted trial gets a fresh reminder. Nullable, no backfill.
"""
from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entitlements",
        sa.Column("trial_reminder_sent_for", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entitlements", "trial_reminder_sent_for")
