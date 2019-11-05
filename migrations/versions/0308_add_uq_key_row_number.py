"""

Revision ID: 0308_add_uq_key_row_number
Revises: 0307_delete_dm_datetime
Create Date: 2019-11-05 10:12:03.627850

"""
from alembic import op

revision = '0308_add_uq_key_row_number'
down_revision = '0307_delete_dm_datetime'


def upgrade():
    op.create_unique_constraint('uq_notifications_job_row_number', 'notifications', ['job_id', 'job_row_number'])


def downgrade():
    op.drop_constraint('uq_notifications_job_row_number')
