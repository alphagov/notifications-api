"""

Revision ID: 0264_add_folder_permissions_perm
Revises: 0263_remove_edit_folders_2
Create Date: 2019-02-14 11:23:26.694656

"""
from alembic import op


revision = '0264_add_folder_permissions_perm'
down_revision = '0263_remove_edit_folders_2'


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('edit_folder_permissions')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'edit_folder_permissions'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'edit_folder_permissions'")
