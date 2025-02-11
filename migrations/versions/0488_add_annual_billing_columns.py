"""
Create Date: 2025-01-27 10:11:14.411859
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0488_add_annual_billing_columns"
down_revision = "0487_returned_letter_callback"


def upgrade():
    op.add_column("annual_billing", sa.Column("high_volume_service_last_year", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("annual_billing", sa.Column("has_custom_allowance", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("annual_billing", "has_custom_allowance")
    op.drop_column("annual_billing", "high_volume_service_last_year")
