"""

Create Date: 2026-03-30 09:51:23.222324
Revision ID: 0547_new_sms_allowance_n_rate
Revises: 0546_letter_rates_from_7_4_26

"""

import uuid

from alembic import op


revision = "0547_new_sms_allowance_n_rate"
down_revision = "0546_letter_rates_from_7_4_26"

new_allowances = {
    "central": 20_000,
    "nhs_central": 20_000,
    "local": 10_000,
    "nhs_local": 10_000,
    "emergency_service": 10_000,
    "school_or_college": 5_000,
    "other": 5_000,
    "nhs_gp": 0,
}


def upgrade():
    op.execute(
        "INSERT INTO rates(id, valid_from, rate, notification_type) "
        f"VALUES('{uuid.uuid4()}', '2026-03-31 23:00:00', 0.024, 'sms')"
    )

    for org_type, allowance in new_allowances.items():
        op.execute(
            "INSERT INTO default_annual_allowance"
            "(id, valid_from_financial_year_start, organisation_type, allowance, notification_type) "
            f"VALUES('{uuid.uuid4()}', 2026, '{org_type}', {allowance}, 'sms')"
        )


def downgrade():
    op.execute("DELETE FROM rates WHERE valid_from = '2026-03-31 23:00:00' AND notification_type = 'sms'")
    op.execute("DELETE FROM default_annual_allowance WHERE valid_from_financial_year_start = 2026")