"""

Revision ID: 0363_add_index_key_type
Revises: 0362_broadcast_msg_event
Create Date: 2022-01-06 13:15:23.797332

"""
from alembic import op

revision = '0363_add_index_key_type'
down_revision = '0362_broadcast_msg_event'


def upgrade():
    conn = op.get_bind()
    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        ix_notifications_service_key_type_composite
        ON notifications
        (service_id, key_type, notification_type, created_at)
    """)


def downgrade():
    conn = op.get_bind()
    conn.execute("""
        DROP INDEX ix_notifications_service_key_type_composite
    """)
