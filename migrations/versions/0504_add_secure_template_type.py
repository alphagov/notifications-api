"""
Create Date: 2025-06-06 21:20:34.906866
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0504_add_secure_template_type'
down_revision = '0503_remove_old_permissions'


def upgrade():
    op.add_column('templates', sa.Column('secure_type', sa.Boolean(), nullable = True))


def downgrade():
    op.drop_column('templates', 'secure_type')