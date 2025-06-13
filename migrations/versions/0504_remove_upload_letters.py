"""
Create Date: 2025-06-05 13:51:16.404831
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0504_remove_upload_letters'
down_revision = '0503_remove_old_permissions'


def upgrade():
    op.execute("DELETE from service_permissions where permission = 'upload_letters'")
    op.execute("DELETE from service_permission_types where name = 'upload_letters'")


def downgrade():
    op.execute("INSERT INTO service_permission_types values ('upload_letters')")
