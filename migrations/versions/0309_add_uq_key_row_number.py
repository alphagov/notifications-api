"""

Revision ID: 0309_add_uq_key_row_number
Revises: 0308_delete_loadtesting_provider
Create Date: 2019-11-05 10:12:03.627850

"""
from alembic import op

revision = '0309_add_uq_key_row_number'
down_revision = '0308_delete_loadtesting_provider'


def upgrade():
    op.create_unique_constraint('uq_notifications_job_row_number', 'notifications', ['job_id', 'job_row_number'])


def downgrade():
    op.drop_constraint('uq_notifications_job_row_number')
