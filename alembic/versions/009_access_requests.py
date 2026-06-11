"""Add access_requests lead-capture table

Revision ID: 009
Revises: 008
Create Date: 2026-06-10

Stores "request access / pricing" clicks (the willingness-to-pay field experiment) — who, from what
org, which tier — before any billing exists. Pure lead-capture log; no behavioural effect.
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("organization", sa.String(255), nullable=True),
        sa.Column("plan_interest", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_access_requests_created", "access_requests", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_access_requests_created", table_name="access_requests")
    op.drop_table("access_requests")
