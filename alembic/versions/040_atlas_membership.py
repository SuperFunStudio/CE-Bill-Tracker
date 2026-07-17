"""Atlas Circular membership: temporary Pro preview window on entitlements

Revision ID: 040
Revises: 039
Create Date: 2026-07-17

The rebrand to Atlas Circular replaces the single free/Pro boolean with a 4-tier membership model
(Student / Research / Pro / Enterprise), gated per-capability in app/api/auth.py. The plan values live
in the existing `entitlements.plan` String(30) column — no schema change needed for them. This adds one
column: `preview_until`, the expiry of a temporary Pro *preview* granted to a Student/Research member
(they get Pro capabilities until then without their plan changing). See grant_pro_preview().
"""
from alembic import op
import sqlalchemy as sa

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entitlements",
        sa.Column("preview_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entitlements", "preview_until")
