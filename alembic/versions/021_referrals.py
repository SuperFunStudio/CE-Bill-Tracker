"""Share-to-unlock referrals — referral_code on entitlements + a referrals table

Revision ID: 021
Revises: 020
Create Date: 2026-06-16

A signed-in account gets a referral_code (generated lazily). When a NEW account signs up via that
code, we record a referrals row (unique per referred account) and grant the referrer a 30-day comp
Pro seat. See app/api/referrals.py.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entitlements",
        sa.Column("referral_code", sa.String(length=16), nullable=True),
    )
    op.create_unique_constraint("uq_entitlements_referral_code", "entitlements", ["referral_code"])

    op.create_table(
        "referrals",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("referrer_uid", sa.String(length=128), nullable=False),
        sa.Column("referred_uid", sa.String(length=128), nullable=False, unique=True),
        sa.Column("referred_email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_referrals_referrer_uid", "referrals", ["referrer_uid"])


def downgrade() -> None:
    op.drop_index("idx_referrals_referrer_uid", table_name="referrals")
    op.drop_table("referrals")
    op.drop_constraint("uq_entitlements_referral_code", "entitlements", type_="unique")
    op.drop_column("entitlements", "referral_code")
