"""

Revision ID: 0246_notifications_index
Revises: 0245_archived_flag_jobs
Create Date: 2018-12-12 12:00:09.770775

"""
from alembic import op

revision = '0246_notifications_index'
down_revision = '0245_archived_flag_jobs'


def upgrade():
    conn = op.get_bind()
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_service_created_at ON notifications (service_id, created_at)"
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        "DROP INDEX IF EXISTS ix_notifications_service_created_at"
    )

