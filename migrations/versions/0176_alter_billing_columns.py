"""

Revision ID: 0176_alter_billing_columns
Revises: 0175_drop_job_statistics_table
Create Date: 2018-03-12 16:54:30.663897

"""
from alembic import op
import sqlalchemy as sa

revision = '0176_alter_billing_columns'
down_revision = '0175_drop_job_statistics_table'


def upgrade():
    op.alter_column('dm_datetime', 'calendar_week', existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('dm_datetime', 'day', existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('dm_datetime', 'financial_year', existing_type=sa.INTEGER(), nullable=False)


def downgrade():
    op.alter_column('dm_datetime', 'financial_year', existing_type=sa.INTEGER(), nullable=True)
    op.alter_column('dm_datetime', 'day', existing_type=sa.INTEGER(), nullable=True)
    op.alter_column('dm_datetime', 'calendar_week', existing_type=sa.INTEGER(), nullable=True)
