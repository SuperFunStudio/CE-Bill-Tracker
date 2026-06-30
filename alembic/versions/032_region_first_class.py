"""Make region a first-class dimension + region-keyed subscription scope

Revision ID: 032
Revises: 031
Create Date: 2026-06-28

Migration 031 added `region` to bills only (the lean EU spike). To support compliance-action and
notifications across regions (and flex to UK+), `region` becomes a first-class dimension on every
jurisdiction-bearing table, and alert subscriptions move from a flat `states` list to a region-keyed
`region_scope` (e.g. {"US": ["CA","OR"], "EU": ["*"]}). Everything backfills to 'US' so existing
behavior is unchanged. See plan serene-munching-brook + [[eu-integration]].
"""
from alembic import op
import sqlalchemy as sa

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None

# Tables that carry a jurisdiction and gain a `region` family column (Bill already has it from 031).
_REGION_TABLES = [
    "compliance_deadlines",
    "compliance_entity",
    "compliance_pathway",
    "company",
    "company_state_presence",
    "bill_outcome",
    "litigation_cases",
]


def upgrade() -> None:
    for table in _REGION_TABLES:
        # NOT NULL + server_default backfills every existing row to 'US' in one fast metadata op.
        op.add_column(
            table,
            sa.Column("region", sa.String(length=2), nullable=False, server_default="US"),
        )
        op.create_index(f"idx_{table}_region", table, ["region"])

    # Region-keyed subscription scope. Backfill from the flat `states` list: {"US": <states>}.
    # (The legacy `states` column is kept for back-compat but is no longer the source of truth — the
    # matcher reads region_scope.) Empty/{} region_scope means match-all (any region/jurisdiction).
    op.add_column(
        "alert_subscriptions",
        sa.Column(
            "region_scope",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(
        "UPDATE alert_subscriptions "
        "SET region_scope = jsonb_build_object('US', COALESCE(states, '[]'::jsonb)) "
        "WHERE states IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("alert_subscriptions", "region_scope")
    for table in _REGION_TABLES:
        op.drop_index(f"idx_{table}_region", table_name=table)
        op.drop_column(table, "region")
