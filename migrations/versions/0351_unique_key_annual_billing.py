"""

Revision ID: 0351_unique_key_annual_billing
Revises: 0350_update_rates
Create Date: 2021-04-12 09:02:45.098875

"""

import os

from alembic import op

revision = "0351_unique_key_annual_billing"
down_revision = "0350_update_rates"

environment = os.environ["NOTIFY_ENVIRONMENT"]


def upgrade():
    index = """
        CREATE UNIQUE INDEX CONCURRENTLY uix_service_id_financial_year_start
        ON annual_billing (service_id, financial_year_start)
    """
    constraint = """
        ALTER TABLE annual_BILLING add constraint uix_service_id_financial_year_start
         UNIQUE USING INDEX uix_service_id_financial_year_start
    """
    op.execute("COMMIT")
    op.execute(index)
    op.execute(constraint)


def downgrade():
    op.drop_constraint("uix_service_id_financial_year_start", "annual_billing", type_="unique")
