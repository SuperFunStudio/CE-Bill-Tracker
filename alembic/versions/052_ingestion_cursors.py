"""Add ingestion_cursors so rate-limited sources resume where they stopped

Revision ID: 052
Revises: 051
Create Date: 2026-10-18

The nightly OpenStates cycle searches 305 queries x 52 states but the free tier allows ~250 calls a
day, and every run restarted from query 1 — so only the first five queries were ever searched. This
table holds one JSON cursor per source (where the last run stopped, and when each query was last
swept) so the next run picks up from there. See app/ingestion/openstates_cursor.py.

New table only; nothing else touches it, so it is safe to apply under live load.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_cursors",
        sa.Column("source", sa.String(40), primary_key=True),
        sa.Column("cursor", JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ingestion_cursors")
