"""

Revision ID: 0316_int_letters_permission
Revises: 0315_document_download_count
Create Date: 2020-09-13 28:17:17.110495

"""
from alembic import op
import sqlalchemy as sa


revision = '0316_int_letters_permission'
down_revision = '0315_document_download_count'


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('international_letters')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'international_letters'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'international_letters'")
