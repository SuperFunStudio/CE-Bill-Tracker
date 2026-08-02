"""Add original-language title columns to bills

Revision ID: 044
Revises: 043
Create Date: 2026-08-02

Foreign bills are ingested with an ENGLISH `title` (e.g. Italy's Dlgs 116/2020 is stored as "Decree
transposing the Waste + Packaging Directives"); the original-language title isn't stored anywhere. The
public bill page (/bill/[id]/[slug]) wants to show the native title alongside the English one with the
correct `lang`/`dir` attributes — better UX and better SEO for non-English jurisdictions.

This migration only adds the storage. The column ships EMPTY; populating it is a separate native-title
backfill (an LLM/source job) deferred to a follow-up. The frontend renders the native title only when
present, so an empty column is a no-op. title_native_lang is a BCP-47 tag ("it","ja") for the lang attr.
"""
from alembic import op
import sqlalchemy as sa

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("title_native", sa.Text(), nullable=True))
    op.add_column("bills", sa.Column("title_native_lang", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "title_native_lang")
    op.drop_column("bills", "title_native")
