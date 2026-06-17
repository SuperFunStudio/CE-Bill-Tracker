"""Add signup_trial_used to entitlements — guards the one-time 7-day signup trial

Revision ID: 022
Revises: 021
Create Date: 2026-06-16

The first rung of the value ladder: a new free account gets 7 days of comp Pro (POST /billing/signup-
trial). This flag marks the trial consumed so it can't be re-granted. Defaulted false, no backfill.
"""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entitlements",
        sa.Column("signup_trial_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("entitlements", "signup_trial_used")
