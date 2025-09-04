"""
Create Date: 2025-09-04 15:47:21.596407
"""

from alembic import op

revision = '0517_remove_broadcast_sequence'
down_revision = '0516_remove_broadcast_permission'


def upgrade():
    op.execute("drop sequence broadcast_provider_message_number_seq")


def downgrade():
    op.execute("create sequence broadcast_provider_message_number_seq")
