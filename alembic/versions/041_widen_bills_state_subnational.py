"""Widen bills.state for namespaced sub-national codes

Revision ID: 041
Revises: 040
Create Date: 2026-07-24

Foreign federations (Canada, Australia) legislate EPR at the province/state level, but every foreign
law is currently stored with state == region (e.g. an Ontario reg lands as region="CA", state="CA").
To break those out we carry a NAMESPACED sub-national code in `state` — "CA-BC", "AU-NSW" — never a
bare code (Western Australia "WA" would collide with Washington). Those don't fit the original
VARCHAR(2), so widen bills.state to VARCHAR(16) (headroom for future municipal codes like
"US-NY-NYC"). Widening a varchar is a metadata-only change in Postgres — no table rewrite, and the
idx_bills_state_status index is unaffected. See app/ingestion/foreign.py (ForeignSourceClient.
subnational) + scripts/backfill_subnational_state.py.
"""
from alembic import op
import sqlalchemy as sa

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "bills",
        "state",
        existing_type=sa.String(2),
        type_=sa.String(16),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Only safe once any namespaced (>2 char) codes have been reverted to their region code — a bare
    # VARCHAR(2) can't hold "CA-BC". Truncate defensively so the type change can't fail mid-downgrade.
    op.execute("UPDATE bills SET state = left(state, 2) WHERE length(state) > 2")
    op.alter_column(
        "bills",
        "state",
        existing_type=sa.String(16),
        type_=sa.String(2),
        existing_nullable=False,
    )
