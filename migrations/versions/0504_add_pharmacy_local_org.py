"""
Create Date: 2025-06-06T11:44:07.385360
"""

import uuid
from alembic import op


revision = "0504_add_pharmacy_local_org"
down_revision = "0503_remove_old_permissions"

GP_ORG_TYPE_NAME = "nhs_gp"


def upgrade():
    op.execute(
        "INSERT INTO organisation_types(name, is_crown) VALUES('pharmacy_local', false)"
    )
    op.execute(
        "INSERT INTO default_annual_allowance(id, valid_from_financial_year_start, organisation_type, allowance, notification_type) "
        f"VALUES('{uuid.uuid4()}', 2025, 'pharmacy_local', 0, 'sms')"
    )


def downgrade():
    op.execute("DELETE FROM default_annual_allowance WHERE valid_from_financial_year_start = 2025 AND organisation_type = 'pharmacy_local'")
    op.execute("DELETE FROM organisation_types WHERE name = 'pharmacy_local'")
