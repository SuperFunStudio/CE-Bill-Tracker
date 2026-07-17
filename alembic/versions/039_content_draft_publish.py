"""Publishable content drafts — self-hosted article permalink (off-Substack publishing)

Revision ID: 039
Revises: 038
Create Date: 2026-07-17

Give a ContentDraft its own public link so the edited ARTICLE (not the raw research thread) can be
shared on our domain, independent of Substack. `share_token` backs the instant /p/?token= reader page
(minted on publish, revocable). `slug` + `published_at` are laid down now so the later batch-published,
SEO-indexed /articles/<slug> library needs no further migration. See app/api/research.py.
"""
from alembic import op
import sqlalchemy as sa

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_drafts", sa.Column("share_token", sa.String(length=64), nullable=True))
    op.add_column("content_drafts", sa.Column("slug", sa.String(length=200), nullable=True))
    op.add_column("content_drafts", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_content_drafts_share_token", "content_drafts", ["share_token"])


def downgrade() -> None:
    op.drop_constraint("uq_content_drafts_share_token", "content_drafts", type_="unique")
    op.drop_column("content_drafts", "published_at")
    op.drop_column("content_drafts", "slug")
    op.drop_column("content_drafts", "share_token")
