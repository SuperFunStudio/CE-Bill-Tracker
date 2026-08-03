"""Add bills.adjacency scope-provenance tag (transboundary / toxics …)

Revision ID: 045
Revises: 044
Create Date: 2026-08-02

The binary `ce_relevant` can't express WHY an adjacent-but-included bill entered scope. Some bills are
core circular-economy law on their own merits; others ride in through a deliberately-opened net — e.g.
transboundary / cross-border movement of waste & scrap (the e-scrap recovery customer ask) or toxics /
chemical-restriction material rules. This adds one nullable scalar tag recording that provenance.

Design (docs/SCOPE_FACET_AND_MATERIAL_NAVIGATION.md §5-6, decision 2026-07-31):
  - NO default filter. adjacency-tagged rows are INCLUDED in the default corpus (the list query stays
    `ce_relevant = true` with no adjacency clause). The tag is provenance/analysis, not a gate.
  - One tag per bill (scalar, not JSONB). Slugs so far: 'transboundary', 'toxics'.
  - A bill that is core on its own merits keeps adjacency NULL — the inclusion nets only tag rows that
    would OTHERWISE be `ce_relevant = false` (see scripts/backfill_adjacency.py).

Column only; no backfill here. Populating it (and flipping the matched rows to `ce_relevant = true`) is
scripts/backfill_adjacency.py, run audit-logged against prod. Partial index because the column is NULL
for the overwhelming majority of rows (only the tagged minority is ever queried by tag).
"""
from alembic import op
import sqlalchemy as sa

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("adjacency", sa.String(length=24), nullable=True))
    op.create_index(
        "idx_bills_adjacency",
        "bills",
        ["adjacency"],
        unique=False,
        postgresql_where=sa.text("adjacency IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_bills_adjacency", table_name="bills")
    op.drop_column("bills", "adjacency")
