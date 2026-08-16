"""Strip "deadline" from alert_on — it recorded the old default, not a choice

Revision ID: 051
Revises: 050
Create Date: 2026-08-16

The deadline-reminder email cycle (app/alerts/deadline_alerts.py) is about to be enabled in prod as
an OPT-IN channel. But every existing alert_subscriptions row carries "deadline" in alert_on, because
it sat in the column default from the day the column existed — while enable_deadline_alerts stayed
False, so no deadline email was ever sent. Presence of the key therefore says nothing about what the
subscriber wants: it is the fossil of a default, indistinguishable from a deliberate setting.

This migration removes "deadline" from every row so that, from here on, its presence always means
the user turned the pref on themselves (the model default no longer includes it either — see
AlertSubscription.alert_on in app/models.py). Flipping ENABLE_DEADLINE_ALERTS after this migration
mails nobody until they opt in.

Data-only; no schema change. Downgrade restores the key to every row, which reproduces the prior
universal state (it cannot distinguish rows that had since opted in, because before this migration
no such distinction existed).
"""
from alembic import op

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE alert_subscriptions SET alert_on = alert_on - 'deadline' "
        "WHERE alert_on ? 'deadline'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE alert_subscriptions SET alert_on = alert_on || '[\"deadline\"]'::jsonb "
        "WHERE NOT (alert_on ? 'deadline')"
    )
