"""

Revision ID: 0351_unique_key_annual_billing
Revises: 0350_update_rates
Create Date: 2021-04-12 09:02:45.098875

"""
from alembic import op

revision = '0351_unique_key_annual_billing'
down_revision = '0350_update_rates'


def upgrade():
    op.create_unique_constraint(
        'uix_service_id_financial_year_start', 'annual_billing', ['service_id', 'financial_year_start']
    )


def downgrade():
    op.drop_constraint('uix_service_id_financial_year_start', 'annual_billing', type_='unique')

