"""

Revision ID: 0281_non_null_folder_permissions
Revises: 0280_invited_user_folder_perms
Create Date: 2019-03-20 10:12:24.927129

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0281_non_null_folder_permissions'
down_revision = '0280_invited_user_folder_perms'


def upgrade():
    op.execute("UPDATE invited_users SET folder_permissions = '[]' WHERE folder_permissions IS null")
    op.alter_column('invited_users', 'folder_permissions',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               nullable=False)


def downgrade():
    op.alter_column('invited_users', 'folder_permissions',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               nullable=True)
