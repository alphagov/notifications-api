"""

Revision ID: 0213_rename_service_contact_link
Revises: 0212_remove_caseworking
Create Date: 2018-08-13 11:05:52.413611

"""
from alembic import op
import sqlalchemy as sa


revision = '0213_rename_service_contact_link'
down_revision = '0212_remove_caseworking'


def upgrade():
    op.alter_column('services', 'contact_link', new_column_name='contact_details')
    op.alter_column('services_history', 'contact_link', new_column_name='contact_details')


def downgrade():
    op.alter_column('services', 'contact_details', new_column_name='contact_link')
    op.alter_column('services_history', 'contact_details', new_column_name='contact_link')
