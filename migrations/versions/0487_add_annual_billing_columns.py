"""
Create Date: 2025-01-27 10:11:14.411859
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0487_add_annual_billing_columns"
down_revision = "0486_letter_rates_feb_2025"


def upgrade():
    op.add_column("annual_billing", sa.Column("high_volume_service_last_year", sa.Boolean(), server_default=False))
    op.add_column("annual_billing", sa.Column("has_custom_allowance", sa.Boolean(), server_default=False))


def downgrade():
    op.drop_column("annual_billing", "has_custom_allowance")
    op.drop_column("annual_billing", "high_volume_service_last_year")
