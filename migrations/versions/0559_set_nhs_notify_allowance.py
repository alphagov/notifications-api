"""
Create Date: 2026-07-31 10:11:51.069316
"""

import uuid

from alembic import op

revision = '0559_set_nhs_notify_allowance'
down_revision = '0558_add_nhs_notify_org_type'


def upgrade():
    """
    The free allowance is set from 2016 even though it's a new org type for consistency and to avoid
    potential bugs if trying to view historic usage
    """
    op.execute(
        "INSERT INTO default_annual_allowance"
        "(id, valid_from_financial_year_start, organisation_type, allowance, notification_type) "
        f"VALUES('{uuid.uuid4()}', 2016, 'nhs_notify', 0, 'sms')"
    )


def downgrade():
    op.execute(
        "DELETE FROM default_annual_allowance WHERE " \
        "valid_from_financial_year_start = 2016 AND organisation_type = 'nhs_notify'"
    )
