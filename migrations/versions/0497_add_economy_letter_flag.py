"""
Create Date: 2025-04-14 12:14:22.768745
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0497_add_economy_letter_flag'
down_revision = '0496_update_inbound_callback'


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('economy_letter_sending')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'economy_letter_sending'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'economy_letter_sending'")
