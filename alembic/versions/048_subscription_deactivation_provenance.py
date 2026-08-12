"""Record WHY a subscription went inactive, not just that it did

Revision ID: 048
Revises: 047
Create Date: 2026-08-12

`alert_subscriptions.active` is written by two paths that leave identical traces:

  * an admin clicking Mute in /admin        (app/api/admin.py set_subscriber_active)
  * the recipient clicking unsubscribe      (app/api/alerts.py unsubscribe, signed token)

One is us deciding to stop emailing someone; the other is them asking us to. They are opposite
signals and the database could not tell them apart. That mattered the first time it was asked: three
of the highest-value corporate subscribers on the list (a packaging lead at a global electronics
manufacturer, a Dutch furniture maker, an engineering consultancy) showed as inactive, and there was
no way to know whether they had walked away from a bad alert or simply been muted during testing.
SendGrid could not settle it either — the app runs its own unsubscribe endpoint, which never writes
to SendGrid's suppression list.

Two columns:

  deactivated_at       when active last went false. NULL for rows that never went inactive.
  deactivation_source  'admin_mute' | 'self_unsubscribe' | 'self_prefs' | NULL

NULL source on an already-inactive row is deliberate and permanent: the information to distinguish
those six existing rows was never recorded, and inventing a plausible value would be worse than
admitting it. The UI reads NULL as "unknown (pre-048)" rather than defaulting it into either bucket
— the same principle migration 046 used for unscreened litigation.

Reactivating clears BOTH columns, so the pair always describes the CURRENT inactive spell rather
than accumulating a half-history that no query could interpret.
"""
from alembic import op
import sqlalchemy as sa

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_subscriptions",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alert_subscriptions",
        sa.Column("deactivation_source", sa.String(length=20), nullable=True),
    )
    # Churn questions are always "who left, and lately?" — an index on the timestamp keeps that a
    # range scan. Partial: the overwhelming majority of rows are active and NULL here.
    op.create_index(
        "idx_alert_sub_deactivated_at",
        "alert_subscriptions",
        ["deactivated_at"],
        unique=False,
        postgresql_where=sa.text("deactivated_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_alert_sub_deactivated_at", table_name="alert_subscriptions")
    op.drop_column("alert_subscriptions", "deactivation_source")
    op.drop_column("alert_subscriptions", "deactivated_at")
