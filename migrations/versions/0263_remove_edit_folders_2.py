"""

Revision ID: 0263_remove_edit_folders_2
Revises: 0262_remove_edit_folders
Create Date: 2019-02-15 14:38:13.823432

"""
from alembic import op
import sqlalchemy as sa


revision = '0263_remove_edit_folders_2'
down_revision = '0262_remove_edit_folders'


def upgrade():
    # run this again in case it got added between the 2 deploys
    op.execute("DELETE from service_permissions where permission = 'edit_folders'")
    op.execute("DELETE from service_permission_types where name = 'edit_folders'")


def downgrade():
    op.execute("INSERT INTO service_permission_types values('edit_folders')")
