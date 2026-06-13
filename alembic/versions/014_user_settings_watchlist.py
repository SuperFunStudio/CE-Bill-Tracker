"""Add user_settings + user_watchlist — per-account prefs and the Pro watch list

Revision ID: 014
Revises: 013
Create Date: 2026-06-12

user_settings: per-account UI prefs (currently the saved scope) keyed by Firebase uid, prefs as JSONB
so new preferences don't need a migration. Free — any authenticated user.

user_watchlist: bills an account follows (the Pro watch list), keyed by (firebase_uid, bill_id) with
ON DELETE CASCADE. Pro-gated at the API. See gating-and-monetization-plan.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("firebase_uid", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("prefs", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("firebase_uid", name="uq_user_settings_firebase_uid"),
    )

    op.create_table(
        "user_watchlist",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("firebase_uid", sa.String(length=128), nullable=False),
        sa.Column(
            "bill_id", sa.Integer(),
            sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("firebase_uid", "bill_id", name="uq_watchlist_uid_bill"),
    )
    op.create_index("idx_watchlist_uid", "user_watchlist", ["firebase_uid"])


def downgrade() -> None:
    op.drop_index("idx_watchlist_uid", table_name="user_watchlist")
    op.drop_table("user_watchlist")
    op.drop_table("user_settings")
