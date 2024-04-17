"""

Revision ID: 0360_remove_sched_notifications
Revises: 0359_more_permissions
Create Date: 2021-06-07 09:09:06.376862

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0360_remove_sched_notifications"
down_revision = "0359_more_permissions"


def upgrade():
    # drop index concurrently will drop the index without locking out concurrent
    # selects, inserts, updates, and deletes on the index's table namely on notifications
    # First we need to issue a commit to clear the transaction block.
    op.execute("COMMIT")
    op.execute("DROP INDEX CONCURRENTLY ix_scheduled_notifications_notification_id")
    op.drop_table("scheduled_notifications")


def downgrade():
    # I've intentionally removed adding the index back from the downgrade method
    op.create_table(
        "scheduled_notifications",
        sa.Column("id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("notification_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("scheduled_for", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("pending", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], name="scheduled_notifications_notification_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="scheduled_notifications_pkey"),
    )
