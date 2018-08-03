"""

Revision ID: 0209_add_cancelled_status
Revises: 84c3b6eb16b3
Create Date: 2018-07-31 13:34:00.018447

"""
from alembic import op

revision = '0209_add_cancelled_status'
down_revision = '84c3b6eb16b3'


def upgrade():
    op.execute("INSERT INTO notification_status_types (name) VALUES ('cancelled')")


def downgrade():
    pass
