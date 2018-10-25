"""

Revision ID: 0239_add_edit_folder_permission
Revises: 0238_add_validation_failed
Create Date: 2018-09-03 11:24:58.773824

"""
from alembic import op
import sqlalchemy as sa


revision = '0239_add_edit_folder_permission'
down_revision = '0238_add_validation_failed'


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('edit_folders')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'edit_folders'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'edit_folders'")
