"""

Revision ID: 0440_new_sms_allowance_n_rate
Revises: 0439_intl_letters_jan_24
Create Date: 2023-03-06 11:32:20.588364

"""

import uuid

from alembic import op


revision = "0440_new_sms_allowance_n_rate"
down_revision = "0439_intl_letters_jan_24"

new_allowances = {
    "central": 30000,
    "nhs_central": 30000,
    "local": 10000,
    "nhs_local": 10000,
    "emergency_service": 10000,
    "school_or_college": 5000,
    "other": 5000,
    "nhs_gp": 0,
}


def upgrade():
    op.execute(
        "INSERT INTO rates(id, valid_from, rate, notification_type) "
        f"VALUES('{uuid.uuid4()}', '2024-03-31 23:00:00', 0.0227, 'sms')"
    )

    for org_type, allowance in new_allowances.items():
        op.execute(
            "INSERT INTO default_annual_allowance(id, valid_from_financial_year_start, organisation_type, allowance, notification_type) "
            f"VALUES('{uuid.uuid4()}', 2024, '{org_type}', {allowance}, 'sms')"
        )


def downgrade():
    op.execute(f"DELETE FROM rates WHERE valid_from = '2024-03-31 23:00:00' AND notification_type = 'sms'")

    op.execute("DELETE FROM default_annual_allowance WHERE valid_from_financial_year_start = 2024")
