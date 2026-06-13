"""Add entitlements — the paid-seat record bridging Firebase Auth and Stripe

Revision ID: 013
Revises: 012
Create Date: 2026-06-12

One row per account, keyed by email (the identity shared across Firebase Auth and Stripe). The
billing webhook upserts plan/status/current_period_end on checkout + subscription changes; premium
routes treat an account as Pro when plan == "pro" AND status is active/trialing. Distinct from
access_requests, which only records willingness-to-pay interest. See gating-and-monetization-plan.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entitlements",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("firebase_uid", sa.String(length=128), nullable=True),
        sa.Column("plan", sa.String(length=30), nullable=False, server_default="free"),
        sa.Column("status", sa.String(length=30), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=64), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_entitlements_email"),
        sa.UniqueConstraint("firebase_uid", name="uq_entitlements_firebase_uid"),
    )
    op.create_index("idx_entitlements_email", "entitlements", ["email"])
    op.create_index("idx_entitlements_firebase_uid", "entitlements", ["firebase_uid"])
    op.create_index("idx_entitlements_stripe_customer", "entitlements", ["stripe_customer_id"])


def downgrade() -> None:
    op.drop_index("idx_entitlements_stripe_customer", table_name="entitlements")
    op.drop_index("idx_entitlements_firebase_uid", table_name="entitlements")
    op.drop_index("idx_entitlements_email", table_name="entitlements")
    op.drop_table("entitlements")
