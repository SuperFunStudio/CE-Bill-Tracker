"""Content staging area — editorial drafts distilled from research turns (the Substack pipeline)

Revision ID: 038
Revises: 037
Create Date: 2026-07-15

The holding pen between a raw "Ask the Bills" answer and a published article. An admin sends a
research turn (or a whole thread) through the linking + editorial pass; the result lands here as a
`content_drafts` row the admin edits, then copies out to Substack (no auto-publish). `body_markdown`
already has its [STATE BILL_NUMBER] citations rewritten to battleofbills.com/?bill=<id> deep links.
See app/api/research.py (drafts CRUD) and docs/PUBLIC_AFFAIRS_RESEARCH_DESIGN.md.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # The turn this was distilled from. Kept nullable + SET NULL so deleting the source research
        # thread never destroys an in-flight article draft.
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_seq", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("dek", sa.Text(), nullable=True),          # subtitle / standfirst
        sa.Column("body_markdown", sa.Text(), nullable=False),  # linked + edited article body
        # draft (just linked) | staged (editorial pass done, ready to review) | published (copied out)
        sa.Column("status", sa.String(length=16), nullable=False, server_default="staged"),
        sa.Column("created_by", sa.String(length=200), nullable=True),  # admin email
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_content_drafts_status", "content_drafts", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_content_drafts_status", table_name="content_drafts")
    op.drop_table("content_drafts")
