"""

Revision ID: 0361_new_user_bcast_permissions
Revises: 0360_remove_sched_notifications
Create Date: 2021-06-30 11:42:32.780734

"""

from alembic import op

revision = "0361_new_user_bcast_permissions"
down_revision = "0360_remove_sched_notifications"


def upgrade():
    """
    Delete all permissions for broadcast service users and invited pending users, apart from 'view_activity'
    which they always have.
    """
    op.execute(
        "DELETE FROM permissions WHERE permission != 'view_activity' "
        "and service_id in (select id from services where organisation_id = '38e4bf69-93b0-445d-acee-53ea53fe02df')"
    )
    op.execute(
        "UPDATE invited_users SET permissions = 'view_activity' WHERE status = 'pending' "
        "and service_id in (select id from services where organisation_id = '38e4bf69-93b0-445d-acee-53ea53fe02df')"
    )


def downgrade():
    """
    This change cannot be downgraded since we no longer have access to the original permissions users had.
    """
