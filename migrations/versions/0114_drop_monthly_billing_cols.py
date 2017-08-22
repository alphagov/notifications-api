"""

Revision ID: 0014_drop_monthly_billing_cols
Revises: 0113_job_created_by_nullable
Create Date: 2017-07-27 13:36:37.304344

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0014_drop_monthly_billing_cols'
down_revision = '0113_job_created_by_nullable'


def upgrade():
    op.drop_index('uix_monthly_billing', table_name='monthly_billing')
    op.create_unique_constraint(
        'uix_monthly_billing', 'monthly_billing', ['service_id', 'start_date', 'notification_type']
    )
    op.drop_column('monthly_billing', 'year')
    op.drop_column('monthly_billing', 'month')


def downgrade():
    op.add_column('monthly_billing', sa.Column('month', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.add_column(
        'monthly_billing',
        sa.Column('year', postgresql.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True)
    )
    op.drop_constraint('uix_monthly_billing', 'monthly_billing', type_='unique')
    op.create_index(
        'uix_monthly_billing', 'monthly_billing', ['service_id', 'start_date', 'notification_type'], unique=True
    )
