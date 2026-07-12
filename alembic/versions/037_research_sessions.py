"""Persisted research sessions + turns (Atlas Circular analysis layer)

Revision ID: 037
Revises: 036
Create Date: 2026-07-12

The persistence primitive behind save / share / follow-up (docs/PUBLIC_AFFAIRS_RESEARCH_DESIGN.md).
Tables only; /research/ask starts writing them in A1. Owned by Firebase uid (see
alert_subscriptions.firebase_uid). Not user-exposed until A2.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_uid", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="private"),
        sa.Column("share_token", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_research_sessions_share_token", "research_sessions", ["share_token"])
    op.create_index("idx_research_sessions_owner", "research_sessions", ["owner_uid"])

    op.create_table(
        "research_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column("facets", postgresql.JSONB(), nullable=True),
        sa.Column("strategy", sa.String(length=40), nullable=True),
        sa.Column("answer", postgresql.JSONB(), nullable=True),
        sa.Column("bill_ids", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("bill_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_research_turns_session", "research_turns", ["session_id", "seq"])


def downgrade() -> None:
    op.drop_index("idx_research_turns_session", table_name="research_turns")
    op.drop_table("research_turns")
    op.drop_index("idx_research_sessions_owner", table_name="research_sessions")
    op.drop_constraint("uq_research_sessions_share_token", "research_sessions", type_="unique")
    op.drop_table("research_sessions")
