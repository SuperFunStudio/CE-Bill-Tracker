"""Require a confirmed opt-in before a public sign-up can be emailed

Revision ID: 049
Revises: 048
Create Date: 2026-08-13

POST /subscriptions used to create an ACTIVE, immediately-mailable row from an anonymous request
body. Nothing tied the address in that body to the person typing it: anyone could enter anyone
else's address — or a spam-trap address — and we would start sending. That is the classic
list-bombing hole, and the cost lands on the sending domain rather than on the attacker. It is also
the one thing an ESP compliance review asks about that the consent statement on the form could not
answer: the form documented what a subscriber agreed to, but not that the subscriber was the one
who agreed.

  confirmed_at   when the recipient clicked the confirmation link. NULL = never confirmed.

The gate itself is `active`, not this column: every send path already filters
`active IS TRUE` (dispatcher, digest, deadline + new-bill alerts, welcome), so creating the row
inactive makes the whole fleet fail closed with no per-caller change. confirmed_at is what
distinguishes the three states `active=false` can now mean:

  active=false, confirmed_at NULL      never confirmed — pending, or abandoned
  active=false, confirmed_at set       confirmed once, then unsubscribed or muted (see 048)
  active=true,  confirmed_at set       live subscriber

Backfill: every pre-existing row is stamped confirmed_at = created_at, ACTIVE OR NOT. Not because
those addresses did double opt-in — they didn't — but because "confirmed_at IS NULL" has to mean
exactly one thing going forward: created under the new gate and not yet through it. Grandfathering
the existing list keeps that predicate clean and avoids silently unsubscribing every subscriber we
already have, which would be a far larger harm than the one this closes. Rows that already went
inactive keep their 048 provenance; the stamp says nothing about whether they left.

Only public filter-scope sign-ups carrying an email go through confirmation. A watchlist row is
created for an already-authenticated account whose address Firebase verified, and a Slack-webhook
row has no address to confirm — both stay active on creation, and are stamped confirmed here.
"""
from alembic import op
import sqlalchemy as sa

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_subscriptions",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Grandfather the existing list — see the module docstring on why this covers inactive rows too.
    op.execute(
        "UPDATE alert_subscriptions SET confirmed_at = created_at WHERE confirmed_at IS NULL"
    )
    # "Which sign-ups are still sitting unconfirmed?" is the one query this column exists to answer
    # (pending cleanup, and the abuse signal of a burst of them). Partial, because the steady state
    # is that almost every row is confirmed.
    op.create_index(
        "idx_alert_sub_unconfirmed",
        "alert_subscriptions",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("confirmed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_alert_sub_unconfirmed", table_name="alert_subscriptions")
    op.drop_column("alert_subscriptions", "confirmed_at")
