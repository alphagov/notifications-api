"""

Revision ID: 0280_invited_user_folder_perms
Revises: 0279_remove_fk_to_users
Create Date: 2019-03-11 14:38:28.010082

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0280_invited_user_folder_perms'
down_revision = '0279_remove_fk_to_users'


def upgrade():
    op.add_column('invited_users', sa.Column('folder_permissions', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True))


def downgrade():
    op.drop_column('invited_users', 'folder_permissions')
