"""Add bill_texts — persisted full bill text + FTS index for Layer B full-text search

Revision ID: 028
Revises: 027
Create Date: 2026-06-25

Layer B of the full-text search plan (docs/V2_FULLTEXT_SEARCH_PLAN.md). The extracted bill text was
never stored — every text-based extraction re-fetched it per bill. This side table persists the
cleaned full text ONCE, kept OUT of the wide `bills` row and the snapshot-baked list query (which
must stay cheap and text-free), with a generated `english` tsvector + GIN index so the search
endpoint can run `text_tsv @@ websearch_to_tsquery('english', :q)` and return `ts_headline`
snippets. One row per bill (CASCADE on delete). `indexed_change_hash` lets the refresh job skip
bills whose `change_hash` is unchanged. pg_trgm (migration 002) is available if a substring/fuzzy
fallback index is later needed — deferred; FTS alone first.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bill_texts",
        sa.Column("bill_id", sa.Integer(),
                  sa.ForeignKey("bills.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("text", sa.Text(), nullable=True),
        # Generated, Postgres-maintained tsvector for the FTS index — never written by the app.
        sa.Column(
            "text_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', coalesce(text, ''))", persisted=True),
            nullable=True,
        ),
        sa.Column("char_len", sa.Integer(), nullable=True),
        # Which rung of the fetch ladder produced the text: source_url | openstates | legiscan.
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.Column("indexed_change_hash", sa.String(length=64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_bill_texts_tsv", "bill_texts", ["text_tsv"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("idx_bill_texts_tsv", table_name="bill_texts")
    op.drop_table("bill_texts")
