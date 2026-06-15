"""Add complimentary-grant columns to entitlements — admin-granted Pro without Stripe

Revision ID: 018
Revises: 017
Create Date: 2026-06-14

The hidden /admin console (app/api/admin.py) lets an admin grant a "comp" Pro seat to any email
without a Stripe subscription. `comp` marks such a row so is_pro() can (a) tell it apart from a paid
seat and (b) enforce its expiry itself — there's no Stripe webhook to flip a comp grant off when its
time runs out. current_period_end (already on the table) doubles as the expiry: NULL = indefinite.
comp_note / comp_granted_by / comp_granted_at are the audit trail (why, which admin, when).

All nullable / defaulted, no backfill — existing paid rows keep comp = false.
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entitlements",
        sa.Column("comp", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("entitlements", sa.Column("comp_note", sa.Text(), nullable=True))
    op.add_column("entitlements", sa.Column("comp_granted_by", sa.String(length=320), nullable=True))
    op.add_column(
        "entitlements",
        sa.Column("comp_granted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entitlements", "comp_granted_at")
    op.drop_column("entitlements", "comp_granted_by")
    op.drop_column("entitlements", "comp_note")
    op.drop_column("entitlements", "comp")
