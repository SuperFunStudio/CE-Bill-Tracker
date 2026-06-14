"""Unify the Pro watch list with the alert pipeline — account-owned, bill-scoped subscriptions

Revision ID: 016
Revises: 015
Create Date: 2026-06-13

alert_subscriptions gains two columns so one table can express both kinds of subscription:
  - firebase_uid: owner of an account subscription (NULL = today's anonymous public sub, untouched).
  - scope: 'filter' (existing states/topics/materials matching) or 'watchlist' (matches the explicit
    set of bills the owner follows in user_watchlist, ignoring the filter columns).

Existing rows backfill to scope='filter' via the server_default, so the anonymous subscribe flow is
unchanged. See app/alerts/digest.py (subscription_matches_bill) for the matching branch.
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_subscriptions",
        sa.Column("firebase_uid", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "alert_subscriptions",
        sa.Column(
            "scope", sa.String(length=20), nullable=False, server_default="filter"
        ),
    )
    op.create_index(
        "idx_alert_sub_uid_scope", "alert_subscriptions", ["firebase_uid", "scope"]
    )


def downgrade() -> None:
    op.drop_index("idx_alert_sub_uid_scope", table_name="alert_subscriptions")
    op.drop_column("alert_subscriptions", "scope")
    op.drop_column("alert_subscriptions", "firebase_uid")
