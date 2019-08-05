"""

Revision ID: 0301_upload_letters_permission
Revises: 0300_migrate_org_types
Create Date: 2019-08-05 10:49:27.467361

"""
from alembic import op
import sqlalchemy as sa


revision = '0301_upload_letters_permission'
down_revision = '0300_migrate_org_types'


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('upload_letters')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'upload_letters'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'upload_letters'")
