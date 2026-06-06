"""Purge hand-curated seed rows (known_epr_laws.json) — replaced by OpenStates v3 sync

Revision ID: 005
Revises: 004
Create Date: 2026-06-05

The 54-row hand-curated seed (data/seed/known_epr_laws.json) was loaded via run_seed()
and several of its source_url values point to the wrong bill (e.g. WA HB 1131 linked to a
PDF report for SB 5284), producing broken "View Source" links on the dashboard. Seed rows
are not refreshed from any API, so they can never self-correct.

These rows are uniquely identifiable: a seed row has NO external id at all
(legiscan_bill_id IS NULL AND openstates_id IS NULL). Live OpenStates rows always carry an
openstates_id; LegiScan rows were already removed in migration 004. confidence_score = 1.0
is kept as a secondary guard. Rows that OpenStates later cross-referenced (and thus gained an
openstates_id) are NOT matched and survive. After this migration, a full OpenStates sync
repopulates the dataset with correct official source URLs.
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


# Seed rows: no external id of any kind, and confidence_score pinned to 1.0 by run_seed().
_SEED_PREDICATE = (
    "legiscan_bill_id IS NULL AND openstates_id IS NULL AND confidence_score = 1.0"
)


def upgrade() -> None:
    seed_ids = f"SELECT id FROM bills WHERE {_SEED_PREDICATE}"

    # Delete child rows first (FK constraints), mirroring migration 004's order.
    op.execute(f"DELETE FROM impact_score WHERE bill_id IN ({seed_ids})")
    op.execute(f"DELETE FROM bill_changes WHERE bill_id IN ({seed_ids})")
    op.execute(f"DELETE FROM compliance_deadlines WHERE bill_id IN ({seed_ids})")
    op.execute(f"DELETE FROM exposure_brief WHERE bill_id IN ({seed_ids})")

    # litigation_cases.related_law_id is a nullable FK — null it out rather than delete the case.
    op.execute(
        f"UPDATE litigation_cases SET related_law_id = NULL "
        f"WHERE related_law_id IN ({seed_ids})"
    )

    # Finally delete the seed bills themselves.
    op.execute(f"DELETE FROM bills WHERE {_SEED_PREDICATE}")


def downgrade() -> None:
    # Data deletion is not reversible.
    pass
