"""Persist the scope anonymous visitors choose (states + materials), keyed by a client-generated id

Revision ID: 047
Revises: 046
Create Date: 2026-08-11

Personalization used to require an account: ScopeContext.openEditor prompted sign-in for signed-out
readers, so an anonymous visitor could not set a scope at all, and ScopeContext.persist early-returned
when there was no user. The result was that the single most engaged cohort in the property — 62
returning visitors averaging ten-minute sessions, against 23 email subscribers and 11 accounts — told
us nothing about themselves. The gate wasn't converting them either: it was hit 3 times by 1 user in
28 days.

This table is the anonymous half of user_settings.prefs['scope']. `client_id` is a UUID minted in the
browser and kept in localStorage — pseudonymous, no account, deliberately NOT derived from IP or user
agent so it can't re-identify anyone and a cleared browser genuinely starts over.

Deliberately NOT stored: IP, user agent, referrer, or anything free-text. The columns are the same
closed vocabularies the bill filters use (two-letter state codes, material_category slugs), which is
what makes this a product-interest signal rather than a tracking record.

One row per client_id (upsert), so a visitor refining their scope over several visits stays one row
and updated_at reads as "last time they touched it".
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anon_scope",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Browser-minted UUID. Unique so the endpoint can upsert without a read-modify-write.
        sa.Column("client_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("states", JSONB(), nullable=False, server_default="[]"),
        sa.Column("material_categories", JSONB(), nullable=False, server_default="[]"),
        # Mirrors the client flags: `configured` = been through onboarding (incl. an explicit skip),
        # `scoped` = the "Show everything" toggle is currently off. A configured row with an empty
        # scope is a real answer ("show me everything"), not a missing one — hence both booleans.
        sa.Column("configured", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("scoped", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("idx_anon_scope_client", "anon_scope", ["client_id"], unique=True)
    # Reporting reads this newest-first ("what have anonymous visitors asked for lately").
    op.create_index("idx_anon_scope_updated", "anon_scope", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_anon_scope_updated", table_name="anon_scope")
    op.drop_index("idx_anon_scope_client", table_name="anon_scope")
    op.drop_table("anon_scope")
